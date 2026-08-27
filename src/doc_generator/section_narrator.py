from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Protocol

from local_llm import PromptEnvelope

from .sections import Section, SectionSelection

# The model names and describes a group; it never decides membership. Keeping
# the structural decision in `sections.py` is what makes a wiki run reproducible
# - two runs over an unchanged repository produce the same sections, the same
# page ids, and the same navigation, whether or not any model was reachable.
SYSTEM_PROMPT = (
    "You name and describe one area of a source repository. "
    "You are given the modules that area contains; the grouping is already decided and must not be questioned. "
    "Reply with exactly two lines: "
    "a first line 'Title: <2-4 word name for the area>', "
    "then a second line 'Description: <one or two sentences on what the area is responsible for>'. "
    "Base both only on the modules listed. Do not speculate, and do not mention this instruction. "
    "Whenever you name a specific module or file from this repository, wrap it in backticks exactly as it "
    "appears (e.g. `some_module`, `src/path/to/file.py`) so the wiki can link it to its own page."
)

# Enough of a module list to characterize an area without pushing a large
# section's prompt past what a small local model handles well.
MAX_PROMPTED_MEMBERS = 40

# A section's name is navigation chrome - it sits in the sidebar on every page
# and has to stay on one line. A model that answers with a sentence gets its
# answer rejected in favour of the deterministic title.
MAX_TITLE_CHARACTERS = 60


@dataclass(frozen=True, slots=True)
class SectionNarration:
    title: str
    description: str


class SectionNarrationCache(Protocol):
    """Persistence for narrations, keyed by section and by membership.

    `doc_generator` regenerates documentation more than once per index (once for
    structure, once after summaries land) and again on every incremental run, so
    without a cache the "one call per group" budget would be spent repeatedly on
    groups that did not change.
    """

    def load_section_narration(self, repository_id: str, section_key: str, membership_hash: str) -> tuple[str, str] | None: ...

    def save_section_narration(
        self, repository_id: str, section_key: str, membership_hash: str, *, title: str, description: str
    ) -> None: ...


def build_section_narration_prompt(section: Section) -> PromptEnvelope:
    members = section.members[:MAX_PROMPTED_MEMBERS]
    omitted = len(section.members) - len(members)
    module_lines = "\n".join(
        f"- {member.name}" + (f" - {_first_sentence(member.docstring or member.generatedSummary)}" if (member.docstring or member.generatedSummary) else "")
        for member in members
    )
    if omitted > 0:
        module_lines += f"\n- ... and {omitted} more module{'' if omitted == 1 else 's'}"
    prompt_text = (
        "Name and describe this area of the repository.\n\n"
        f"Directory: {section.directoryPath}\n"
        f"Module count: {len(section.members)}\n\n"
        f"Modules:\n{module_lines}\n"
    )
    return PromptEnvelope(
        promptText=prompt_text,
        systemPrompt=SYSTEM_PROMPT,
        context=(f"sectionKey={section.key}", f"directory={section.directoryPath}"),
    )


def parse_section_narration(text: str, *, section: Section) -> SectionNarration | None:
    """Read a model reply into a title and description.

    Returns None rather than a partial narration when the reply carries no
    usable title: a section whose name came out empty, or as a paragraph, is
    better shown under its deterministic directory-derived name than under
    whatever the model happened to emit.
    """
    title = ""
    description_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if not title and lowered.startswith("title:"):
            title = line.split(":", 1)[1].strip().strip("*_`\"'")
        elif lowered.startswith("description:"):
            description_lines.append(line.split(":", 1)[1].strip())
        elif title:
            description_lines.append(line)

    if not title or len(title) > MAX_TITLE_CHARACTERS:
        return None
    description = " ".join(description_lines).strip()
    return SectionNarration(title=title, description=description or section.description)


class SectionNarrator:
    """Names and describes each section with one LLM call per section.

    ``llmEngine`` is duck-typed for the same reason `CodeSummaryPipeline` types
    it as `Any`: the CLI hands over a `provider_routing.FailoverExecutor`, and
    `doc_generator` sits below `provider_routing` in the dependency graph.

    Failure is never fatal. An unavailable engine, a refused call, or an
    unparseable reply all leave the section with its deterministic title and no
    description - the wiki still builds, and still navigates.
    """

    def __init__(
        self,
        llmEngine: Any,
        *,
        cache: SectionNarrationCache | None = None,
        repositoryId: str = "",
    ) -> None:
        self.llmEngine = llmEngine
        self.cache = cache
        self.repositoryId = repositoryId

    def isReady(self) -> bool:
        try:
            return bool(self.llmEngine is not None and self.llmEngine.isAvailable())
        except Exception:
            return False

    def narrate(self, section: Section) -> SectionNarration | None:
        membership_hash = section.membershipHash()
        cached = self._load_cached(section.key, membership_hash)
        if cached is not None:
            return cached
        if not self.isReady():
            return None

        try:
            text = self.llmEngine.generate(build_section_narration_prompt(section))
        except Exception:
            # Same posture as every other optional enrichment in the generator:
            # a model that cannot answer degrades the page, never the run.
            return None

        narration = parse_section_narration(text or "", section=section)
        if narration is None:
            return None
        self._save_cached(section.key, membership_hash, narration)
        return narration

    def _load_cached(self, section_key: str, membership_hash: str) -> SectionNarration | None:
        if self.cache is None:
            return None
        try:
            stored = self.cache.load_section_narration(self.repositoryId, section_key, membership_hash)
        except Exception:
            return None
        return SectionNarration(title=stored[0], description=stored[1]) if stored else None

    def _save_cached(self, section_key: str, membership_hash: str, narration: SectionNarration) -> None:
        if self.cache is None:
            return
        try:
            self.cache.save_section_narration(
                self.repositoryId,
                section_key,
                membership_hash,
                title=narration.title,
                description=narration.description,
            )
        except Exception:
            return


def apply_section_narrations(selection: SectionSelection, narrator: SectionNarrator | None) -> SectionSelection:
    """Return the same sections, named by the model where one answered.

    Membership, ordering, keys and page paths are all untouched: this only fills
    `title`/`description`, so a repository documented with no model reachable
    navigates identically to one documented with a model, just with plainer
    names.
    """
    if narrator is None:
        return selection
    narrated: list[Section] = []
    for section in selection.sections:
        narration = narrator.narrate(section)
        if narration is None:
            narrated.append(section)
            continue
        narrated.append(
            replace(section, title=narration.title, description=narration.description, isNarrated=True)
        )
    return SectionSelection(sections=tuple(narrated))


def _first_sentence(text: str) -> str:
    collapsed = " ".join(text.split())
    if not collapsed:
        return ""
    sentence, separator, _rest = collapsed.partition(". ")
    return (sentence + separator).strip()[:200]
