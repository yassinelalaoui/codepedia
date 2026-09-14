"""The single model call that writes the Overview's narrative.

The **only** module in this package that takes an LLM engine. Evidence and
grounding refuse one by signature, so "this stage works with no model" is
checkable by reading the imports rather than by trusting a comment.

Failure here is never fatal and never partial. An unavailable engine, a refused
call and an unparseable reply are outcomes, not exceptions, and every one of
them ends at `grounding.ground`, which turns "no reply" into "no prose" - the
same value a reply whose every paragraph failed produces. That is what makes a
page built with no provider navigate identically to one built with a working
key, differing only in the paragraphs at the top.

One call, or none. Never two, and never a retry - see 038 research Decision 2
for why one call for the whole page beats one per section on this budget.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Protocol

from local_llm import PromptEnvelope

from ..plain_text import excerpt
from . import CHARS_PER_TOKEN, PROVIDER_TOKEN_BUDGET  # noqa: F401 - the budget this module is sized against
from .evidence import (
    MAX_PROMPTED_ENTRY_FLOWS,
    MAX_PROMPTED_FEATURES,
    MAX_README_LEAD_CHARS,
    ENTRY_KINDS,
    EntryFlow,
    FeatureBrief,
    OverviewEvidence,
)

# Bumped whenever the reply's shape changes, so a cached reply to the old
# question is never read as an answer to the new one.
NARRATIVE_FORMAT_VERSION = "2"

# Worst-case sizes of each prompt part. Constants rather than measurements of
# the live strings, because the budget assertion in `test_overview_narrator.py`
# has to bound what the prompt *could* be, not what one example happens to be.
# Every part is hard-truncated to its constant when the prompt is built.
# 1400 until the entry/uncalled distinction was spelled out (038 research
# Decisions 15 and 16), 1600 until User Story 2 asked for subsystem paragraphs,
# 1900 until paragraph 1 was asked to name every kind of entry (Decision 19);
# each step is under 100 tokens on the worst case.
SYSTEM_PROMPT_CHARS = 2050
# Repository name, languages, the subsystem count, and the one line that says
# how to read the entry lines below.
HEADER_CHARS = 300
FEATURE_BLOCK_CHARS = 710
ENTRY_FLOW_CHARS = 240

# The lead's 600-word ceiling is ~800 tokens of English; JSON keys, quotes,
# `[[fN]]` handles and backticked names add ~150. The rest is margin, so a
# `finish_reason: length` truncation - which parses as nothing - stays unlikely.
MAX_NARRATIVE_RESPONSE_TOKENS = 1400

SYSTEM_PROMPT = (
    "You write the opening of a repository's documentation page, using only the evidence given. "
    'Reply with only a JSON object {"lead": ["...", "..."], "subsystems": {"fN": "..."}}, '
    "under 550 words in all. The lead holds two to four paragraphs.\n"
    "Paragraph 1 opens by saying what the repository is and does. Then, if lines are marked entry, it "
    "names each kind of entry with its files as where work enters (api-route as routes, cli-command as commands, "
    "main as the main function); if none is, it claims no entry point and names a subsystem's start file.\n"
    "Paragraph 2 follows one line: name its function and file, then the subsystems its calls reach. "
    "Only a line marked entry is an entry point; one marked uncalled is just a function nothing calls. "
    "Call order is not data flow: list what it reaches without then, next or finally.\n"
    "Paragraph 3, only if a subsystem's description or start-file summary says it stores, sends or "
    "returns data, names every such subsystem as a place results can go and cites one of their start files; "
    "never a single file as the only destination.\n"
    '"subsystems" holds a paragraph for each subsystem marked paragraph and for no other, keyed by its handle: '
    "at most three sentences on what it does, naming its start file in backticks, "
    "with every other subsystem written as its handle.\n"
    "Rules:\n"
    "- Write full sentences; no arrows.\n"
    "- Write a subsystem only as its handle in double brackets, like [[f2]]; never f2 alone, never its title.\n"
    "- Every paragraph names at least one file or function in backticks, copied exactly from the "
    "evidence, like `src/app/main.py` or `Service.run`. Files only, never directories.\n"
    "- Name nothing that is absent from the evidence.\n"
    "- Declarative present tense. Never address the reader or write you.\n"
    "- No promotional adjectives such as powerful, robust, seamless or modern.\n"
    "- No headings, lists, tables, links or other markup.\n"
    "Example: Work enters through routes in `src/app/api.py` and commands in `src/app/cli.py`. "
    "The `run` command in `src/app/cli.py` is part of [[f0]]; its calls reach [[f1]] and [[f3]]."
)

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")

NarrationStatus = Literal[
    "cached", "generated", "stale", "previous-prompt", "unavailable", "failed", "unparseable", "skipped"
]


class OverviewNarrativeCache(Protocol):
    """Persistence for one raw reply per repository, keyed by its exact prompt."""

    def load_overview_narrative(self, repository_id: str, narrative_key: str) -> tuple[str, dict[str, str]] | None: ...

    def load_latest_overview_narrative(self, repository_id: str) -> tuple[str, dict[str, str], str] | None: ...

    def save_overview_narrative(
        self,
        repository_id: str,
        narrative_key: str,
        reply_text: str,
        handle_map: Mapping[str, str],
        *,
        repository_fingerprint: str = "",
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class NarrativeReply:
    """The model's answer, parsed but not yet trusted - `grounding` decides."""

    lead: tuple[str, ...] = ()
    subsystems: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NarrationOutcome:
    status: NarrationStatus
    reply: NarrativeReply | None = None
    handleMap: Mapping[str, str] = field(default_factory=dict)
    #: For `stale` and `previous-prompt`: the failure (`unavailable`, `failed`,
    #: `unparseable`) that made the earlier reply the best available one.
    staleReason: str = ""
    #: For `skipped` only: `structure-pass` (silent) or `no-features` (reported).
    skipReason: str = ""


def worst_case_prompt_tokens() -> int:
    """The largest prompt these constants permit, in tokens.

    Computed from the constants rather than measured from an example, so that
    raising any cap moves this number and fails the assertion in
    `test_overview_narrator.py`. A test that restated the answer could not
    catch that.
    """
    total_chars = (
        SYSTEM_PROMPT_CHARS
        + HEADER_CHARS
        + MAX_README_LEAD_CHARS
        + MAX_PROMPTED_FEATURES * FEATURE_BLOCK_CHARS
        + MAX_PROMPTED_ENTRY_FLOWS * ENTRY_FLOW_CHARS
    )
    return total_chars // CHARS_PER_TOKEN


def worst_case_call_tokens() -> int:
    return worst_case_prompt_tokens() + MAX_NARRATIVE_RESPONSE_TOKENS


def build_overview_prompt(evidence: OverviewEvidence) -> PromptEnvelope:
    """The whole prompt, every part truncated to the constant that bounds it.

    Truncation leaves one character per part for the newline that joins it, so
    the joined text never exceeds the sum `worst_case_prompt_tokens` assumes.
    """
    parts: list[str] = []

    listed = len(evidence.features)
    omitted = f", {evidence.omittedFeatureCount} more not listed" if evidence.omittedFeatureCount else ""
    header = (
        f"Repository: {evidence.repositoryName}.\n"
        f"Languages: {', '.join(evidence.languages) or 'unknown'}.\n"
        f"Subsystems: {listed} listed below as fN{omitted}.\n"
        "Call lines: a function, its file, the subsystem it is part of, then the subsystems its calls reach, nearest first."
    )
    parts.append(_fit(header, HEADER_CHARS))

    # The README's opening paragraph, not its bullet list. The bullets are the
    # planner's evidence - headings and directory names, measured on the
    # sample repository - and a model copies directory names into citations
    # that grounding then has to reject.
    if evidence.readmeLead:
        label = "What its README says first:\n"
        lead = excerpt(evidence.readmeLead, max_chars=MAX_README_LEAD_CHARS - len(label) - 1)
        parts.append(label + lead)

    majors = set(evidence.majorFeatureKeys)
    parts.extend(
        _fit(_feature_block(brief, paragraph=brief.featureKey in majors), FEATURE_BLOCK_CHARS)
        for brief in evidence.features
    )
    parts.extend(_fit(_flow_line(flow), ENTRY_FLOW_CHARS) for flow in evidence.entryFlows)

    return PromptEnvelope(
        promptText="\n".join(parts) + "\n",
        systemPrompt=SYSTEM_PROMPT,
        context=(f"featureCount={listed}", f"formatVersion={NARRATIVE_FORMAT_VERSION}"),
        options={
            "max_tokens": MAX_NARRATIVE_RESPONSE_TOKENS,
            # Suppress the reasoning channel, for the reason the planner does
            # (features/planner.py): left at its default, reasoning tokens count
            # against the same window and can consume the whole answer.
            "reasoning_effort": "low",
        },
    )


def narrative_cache_key(envelope: PromptEnvelope) -> str:
    """Identifies exactly what the model was shown - nothing more, nothing less.

    The summary ledger's principle (`summary_context.context_hash`): the same
    input makes the same answer reusable. Anything that changes the prompt -
    a feature renamed, an anchor's docstring edited, the README rewritten, the
    format version bumped - changes the key; nothing else does.
    """
    digest = hashlib.sha1()
    for part in (
        NARRATIVE_FORMAT_VERSION,
        envelope.systemPrompt or "",
        envelope.promptText,
        str(envelope.options.get("max_tokens", "")),
    ):
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def parse_narrative_reply(text: str) -> NarrativeReply | None:
    """Read a model reply, or `None` if it cannot be read.

    `None` and a reply with nothing usable in it are the same outcome to the
    caller, so a partly readable answer is never half-applied.
    """
    if not text or not text.strip():
        return None
    match = _JSON_OBJECT.search(text)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None

    raw_lead = payload.get("lead")
    # A model sometimes returns several paragraphs in one string, separated by
    # a blank line. They are still paragraphs - each is grounded on its own.
    lead = (
        tuple(
            part.strip()
            for item in raw_lead
            if isinstance(item, str)
            for part in _PARAGRAPH_BREAK.split(item)
            if part.strip()
        )
        if isinstance(raw_lead, list)
        else ()
    )
    raw_subsystems = payload.get("subsystems")
    subsystems = (
        {str(key): value for key, value in raw_subsystems.items() if isinstance(value, str)}
        if isinstance(raw_subsystems, dict)
        else {}
    )
    if not lead and not subsystems:
        return None
    return NarrativeReply(lead=lead, subsystems=subsystems)


class OverviewNarrator:
    """Writes the Overview's narrative with **one** LLM call, cached.

    ``llmEngine`` is duck-typed for the same reason `FeaturePlanner` types it
    as `Any`: the CLI hands over a `provider_routing.FailoverExecutor`, and
    `doc_generator` sits below `provider_routing` in the dependency graph.
    """

    def __init__(
        self,
        llmEngine: Any,
        *,
        cache: OverviewNarrativeCache | None = None,
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

    def narrate(self, evidence: OverviewEvidence) -> NarrationOutcome:
        """One call, or none. Returns an outcome for every provider behaviour."""
        if not evidence.features:
            return NarrationOutcome("skipped", skipReason="no-features")

        envelope = build_overview_prompt(evidence)
        key = narrative_cache_key(envelope)
        handle_map = evidence.handle_map()

        # Before availability, deliberately: an already-narrated repository
        # renders the same page whether or not a provider is reachable now.
        cached = self._load(key)
        if cached is not None:
            reply, stored_map = cached
            return NarrationOutcome("cached", reply=reply, handleMap=stored_map or handle_map)

        failure: NarrationStatus
        if not self.isReady():
            failure = "unavailable"
        else:
            try:
                # Through `run`, never `generate`: the CLI hands over a
                # `FailoverExecutor`, which exposes the chain and not the
                # engine's own methods.
                result = self.llmEngine.run(lambda engine: engine.generate(envelope))
            except RuntimeError:
                # Every provider failure is a `RuntimeError`. Deliberately *not*
                # `Exception`: an `AttributeError` here is a wiring bug and must
                # stay loud rather than masquerade as an unreachable provider.
                failure = "failed"
            else:
                text = getattr(result, "value", "") or ""
                reply = parse_narrative_reply(text if isinstance(text, str) else str(text))
                if reply is not None:
                    self._save(key, text, handle_map, evidence.repositoryFingerprint)
                    return NarrationOutcome("generated", reply=reply, handleMap=handle_map)
                failure = "unparseable"

        # Spec FR-017a: no answer for this prompt, so the repository's most
        # recent narrative - re-grounded against the repository as it is now.
        # Never overwritten here.
        latest = self._load_latest()
        if latest is not None:
            reply, stored_map, fingerprint = latest
            # Only the prompt changed - a format version, a reworded rule - and
            # the repository is byte for byte the one this narrative described.
            # It is not "an earlier version", so the page carries no caveat
            # (038 analyze finding I2). An unknown fingerprint stays stale.
            status: NarrationStatus = (
                "previous-prompt"
                if fingerprint and fingerprint == evidence.repositoryFingerprint
                else "stale"
            )
            return NarrationOutcome(status, reply=reply, handleMap=stored_map, staleReason=failure)
        return NarrationOutcome(failure)

    def _load(self, key: str) -> tuple[NarrativeReply, dict[str, str]] | None:
        if self.cache is None:
            return None
        try:
            row = self.cache.load_overview_narrative(self.repositoryId, key)
        except Exception:
            # A cache that cannot be read costs one call, never the run.
            return None
        return _parsed(row)

    def _load_latest(self) -> tuple[NarrativeReply, dict[str, str], str] | None:
        if self.cache is None:
            return None
        try:
            row = self.cache.load_latest_overview_narrative(self.repositoryId)
        except Exception:
            return None
        if row is None:
            return None
        parsed = _parsed(row[:2])
        return (*parsed, row[2]) if parsed is not None else None

    def _save(self, key: str, text: str, handle_map: Mapping[str, str], fingerprint: str) -> None:
        if self.cache is None:
            return
        try:
            self.cache.save_overview_narrative(
                self.repositoryId, key, text, handle_map, repository_fingerprint=fingerprint
            )
        except Exception:
            return


def _parsed(row: tuple[str, dict[str, str]] | None) -> tuple[NarrativeReply, dict[str, str]] | None:
    if row is None:
        return None
    reply = parse_narrative_reply(row[0])
    return (reply, dict(row[1])) if reply is not None else None


def _fit(text: str, limit: int) -> str:
    """`text` shortened to fewer than `limit` characters, leaving room for a newline.

    Cuts at a line boundary first, then at a word, and never leaves an unpaired
    backtick: a half-quoted path in the prompt is one the model might copy back,
    and grounding would then reject the paragraph that cited it.
    """
    if len(text) < limit:
        return text
    cut = text[: limit - 1]
    newline = cut.rfind("\n")
    if newline > 0:
        cut = cut[:newline]
    else:
        space = cut.rfind(" ")
        if space > 0:
            cut = cut[:space]
    if cut.count("`") % 2:
        cut = cut[: cut.rfind("`")].rstrip()
    return cut


def _feature_block(brief: FeatureBrief, *, paragraph: bool = False) -> str:
    # A major subsystem is marked in its own block rather than listed in the
    # header, so asking for its paragraph costs a word, not a line the header's
    # truncation could drop (User Story 2).
    marker = ", paragraph" if paragraph else ""
    lines = [f"{brief.handle}: {brief.title} ({brief.kind}, {brief.entryPointCount} entry points{marker})"]
    if brief.description:
        lines[0] += f" - {brief.description}"
    if brief.anchorPath:
        start = f"  start: `{brief.anchorPath}`"
        if brief.anchorSummary:
            start += f" - {brief.anchorSummary}"
        lines.append(start)
    if brief.memberNames:
        lines.append("  also: " + ", ".join(f"`{name}`" for name in brief.memberNames))
    return "\n".join(lines)


def _flow_line(flow: EntryFlow) -> str:
    # The owning subsystem is spelled "part of", not placed first in an arrow
    # chain: written as `file [[f3]] -> [[f5]]`, a model read `main` as
    # "invoking" the subsystem its own file belongs to (research Decision 16).
    owner = f" (part of [[{flow.featureHandle}]])" if flow.featureHandle else ""
    reached = ", ".join(f"[[{handle}]]" for handle in flow.reachedHandles)
    tail = f"; its calls reach {reached}" if reached else ""
    # Only a command, a route or `main` is called an entry. Labelling the rest
    # "entry (function)" is what let the model present a service implementation
    # as the repository's entry point (evidence.ENTRY_KINDS).
    label = f"entry ({flow.kind})" if flow.kind in ENTRY_KINDS else "uncalled"
    return f"{label}: `{flow.qualifiedName}` in `{flow.modulePath}`{owner}{tail}"
