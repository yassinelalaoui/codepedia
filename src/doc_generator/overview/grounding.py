"""Deterministic acceptance of the narrator's reply. No model, ever.

Takes no LLM engine argument - see this package's docstring. Every rule below is
a row of 038 research Decision 6 and is exercised on hand-written replies in
`tests/unit/test_overview_grounding.py`, so each one is its own test rather than
something inferred from an end-to-end run.

A paragraph is accepted or rejected *whole*: a paragraph with one false name is
not repaired by deleting the name, because the sentence around it was written
to say something about the thing that does not exist.

Rendering is by construction rather than by trust. The model never writes
Markdown that reaches the page: text is escaped, names become code spans that
already resolved, and subsystem handles become links built here. So nothing a
reply contains can add a heading, a table, a link or an attribute list
(spec FR-004), and every link it produces points at a page that exists
(FR-011).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Mapping

from ..cross_references import SymbolLookup, resolve_reference
from ..markdown_render import _markdown_escape
from ..models import PageLink
from .evidence import MAX_SUBSYSTEM_PARAGRAPHS, OverviewEvidence

__all__ = [
    "BANNED_PROMOTIONAL_TERMS",
    "MAX_LEAD_PARAGRAPHS",
    "MAX_NARRATIVE_WORDS",
    "MAX_SUBSYSTEM_PARAGRAPHS",
    "MAX_SUBSYSTEM_SENTENCES",
    "GroundedNarrative",
    "GroundedParagraph",
    "Rejection",
    "Segment",
    "accept_description",
    "ground",
    "render_paragraph",
]

# Spec FR-005: the lead is at most four paragraphs.
MAX_LEAD_PARAGRAPHS = 4

# Spec FR-025: a subsystem paragraph is at most three sentences (G8).
MAX_SUBSYSTEM_SENTENCES = 3

# Spec FR-005a: all generated prose on the page stays *under* this.
MAX_NARRATIVE_WORDS = 600

# Spec FR-013's house style: the maintained list its examples illustrate.
# Word-bounded and case-insensitive. Evaluative words a reader cannot check
# ("powerful") are banned; descriptive ones that can be true ("simple") are not.
BANNED_PROMOTIONAL_TERMS = frozenset(
    {
        "powerful",
        "robust",
        "seamless",
        "seamlessly",
        "modern",
        "cutting-edge",
        "state-of-the-art",
        "state of the art",
        "best-in-class",
        "world-class",
        "blazing",
        "blazingly",
        "effortless",
        "effortlessly",
        "elegant",
        "innovative",
        "revolutionary",
        "next-generation",
        "high-performance",
        "enterprise-grade",
        "industry-leading",
        "leading-edge",
        "sleek",
        "stunning",
        "delightful",
        "game-changing",
    }
)

_SECOND_PERSON = re.compile(r"\b(you|your|yours|yourself|yourselves)\b", re.IGNORECASE)
_BANNED = re.compile(
    r"\b(" + "|".join(re.escape(term) for term in sorted(BANNED_PROMOTIONAL_TERMS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"`([^`\n]+)`|\[\[\s*(f\d+)\s*\]\]")
_WHITESPACE = re.compile(r"\s+")

# G5: shapes that only an identifier has. Prose words match none of them.
_FILE_EXTENSIONS = (
    "py|pyi|js|jsx|mjs|cjs|ts|tsx|java|kt|kts|go|rs|rb|cs|cpp|cc|cxx|c|h|hpp|php|swift|scala|"
    "md|rst|toml|json|ya?ml|sql|sh|ps1|html|css|scss|vue|svelte"
)
_PATH_LIKE = re.compile(r"[\w.\-]+(?:/[\w.\-]+)+")
_FILE_LIKE = re.compile(rf"\b[\w\-]+\.(?:{_FILE_EXTENSIONS})\b")
_SNAKE_LIKE = re.compile(r"\b[A-Za-z0-9]*[A-Za-z][A-Za-z0-9]*_\w*\b|\b_\w*[A-Za-z]\w*\b")
_DOTTED_LIKE = re.compile(r"\b[a-z_][a-z0-9_]+(?:\.[a-z_][a-z0-9_]+)+\b")
_CALL_LIKE = re.compile(r"\b(\w+)\(\)")
_CAMEL_LIKE = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]*)+\b|\b[a-z]+[A-Z][A-Za-z0-9]*\b")

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z`\[])")
# G8 counts sentences, so a full stop that ends no sentence must not count: one
# inside a code span (`pkg.module`, `Child.run`) - masked before splitting - or
# one closing an abbreviation that a capital may follow.
_CODE_SPAN = re.compile(r"`[^`\n]*`")
_ABBREVIATION_END = re.compile(r"\b(?:e\.g|i\.e|etc|vs|cf|approx|incl|resp)\.$", re.IGNORECASE)

RejectionRule = Literal["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10"]
Section = Literal["lead", "subsystem"]


@dataclass(frozen=True, slots=True)
class Segment:
    kind: Literal["text", "code", "feature"]
    value: str
    featureKey: str = ""


@dataclass(frozen=True, slots=True)
class GroundedParagraph:
    segments: tuple[Segment, ...]
    wordCount: int
    sentenceCount: int


@dataclass(frozen=True, slots=True)
class Rejection:
    section: Section
    index: int
    rule: RejectionRule
    token: str = ""


@dataclass(frozen=True, slots=True)
class GroundedNarrative:
    lead: tuple[GroundedParagraph, ...] = ()
    subsystems: tuple[tuple[str, GroundedParagraph], ...] = ()
    rejected: tuple[Rejection, ...] = ()
    leadWithheld: bool = False
    isStale: bool = False
    #: How many paragraphs the reply offered, for "k of n" in the notice.
    offeredCount: int = 0

    @property
    def paragraphCount(self) -> int:
        return len(self.lead) + len(self.subsystems)


@dataclass(slots=True)
class _Context:
    evidence: OverviewEvidence
    lookup: SymbolLookup
    handle_map: Mapping[str, str]
    titles: dict[str, str] = field(default_factory=dict)
    allowed_camel: frozenset[str] = frozenset()


def ground(
    reply,
    evidence: OverviewEvidence,
    lookup: SymbolLookup,
    *,
    handle_map: Mapping[str, str],
    is_stale: bool = False,
) -> GroundedNarrative:
    """Accept or reject each paragraph of `reply` against the repository as it is.

    `reply` is a `narrator.NarrativeReply` or `None`. `None` - no provider, an
    unreadable answer, a skipped narration - gives the same empty value a reply
    whose every paragraph failed does, which is what lets the template treat
    "no prose" as one case.
    """
    if reply is None:
        return GroundedNarrative(isStale=is_stale)

    context = _Context(
        evidence=evidence,
        lookup=lookup,
        handle_map=handle_map,
        titles=evidence.feature_title_by_key(),
        allowed_camel=_allowed_camel_words(evidence),
    )

    rejected: list[Rejection] = []
    lead: list[tuple[int, GroundedParagraph]] = []
    offered = list(reply.lead)
    opening_failed = False
    for index, text in enumerate(offered):
        outcome = _check(text, "lead", index, context)
        if isinstance(outcome, Rejection):
            rejected.append(outcome)
            opening_failed = opening_failed or index == 0
        else:
            lead.append((index, outcome))

    # G9: at most four lead paragraphs, in reply order.
    for index, _ in lead[MAX_LEAD_PARAGRAPHS:]:
        rejected.append(Rejection("lead", index, "G9"))
    lead = lead[:MAX_LEAD_PARAGRAPHS]

    subsystems, offered_subsystems = _ground_subsystems(getattr(reply, "subsystems", None) or {}, context, rejected)

    # G9: the whole page's generated prose stays under the word budget, trimmed
    # from the end - subsystem paragraphs first (last in table order), then the
    # lead.
    def total_words() -> int:
        return sum(p.wordCount for _, p in lead) + sum(p.wordCount for _, _, p in subsystems)

    while subsystems and total_words() >= MAX_NARRATIVE_WORDS:
        index, _, _ = subsystems.pop()
        rejected.append(Rejection("subsystem", index, "G9"))
    while lead and total_words() >= MAX_NARRATIVE_WORDS:
        index, _ = lead.pop()
        rejected.append(Rejection("lead", index, "G9"))
        opening_failed = opening_failed or index == 0

    # G10: the opening paragraph carries the rest. Without it, withhold the lead
    # rather than publish one that starts mid-explanation (spec FR-010a).
    # Subsystem paragraphs stand on their own and are unaffected.
    lead_withheld = bool(offered) and opening_failed
    if lead_withheld:
        for index, _ in lead:
            rejected.append(Rejection("lead", index, "G10"))
        lead = []

    return GroundedNarrative(
        lead=tuple(paragraph for _, paragraph in lead),
        subsystems=tuple((key, paragraph) for _, key, paragraph in subsystems),
        rejected=tuple(sorted(rejected, key=lambda item: (item.section, item.index))),
        leadWithheld=lead_withheld,
        isStale=is_stale,
        offeredCount=len(offered) + offered_subsystems,
    )


def _ground_subsystems(
    offered: Mapping[str, object], context: _Context, rejected: list[Rejection]
) -> tuple[list[tuple[int, str, GroundedParagraph]], int]:
    """The per-subsystem paragraphs that survive, in table order (G11).

    Each is accepted or withheld on its own (spec FR-025a): one bad paragraph
    never costs the others, and never its subsystem's table row. The `int` in
    each entry is the paragraph's position in the reply, for the notice.
    """
    majors = context.evidence.majorFeatureKeys
    kept: dict[str, tuple[int, GroundedParagraph]] = {}
    for index, (handle, text) in enumerate(offered.items()):
        # G3: a handle this prompt issued, for a feature that still exists.
        feature_key = context.handle_map.get(str(handle))
        if not feature_key or feature_key not in context.titles:
            rejected.append(Rejection("subsystem", index, "G3", str(handle)))
            continue
        # G9: paragraphs are asked for, and kept for, major subsystems only -
        # at most `MAX_SUBSYSTEM_PARAGRAPHS` of them - and one each.
        if feature_key not in majors or feature_key in kept:
            rejected.append(Rejection("subsystem", index, "G9", str(handle)))
            continue
        outcome = _check(text, "subsystem", index, context)
        if isinstance(outcome, Rejection):
            rejected.append(outcome)
            continue
        # G8: at most three sentences.
        if outcome.sentenceCount > MAX_SUBSYSTEM_SENTENCES:
            rejected.append(Rejection("subsystem", index, "G8"))
            continue
        kept[feature_key] = (index, outcome)

    ordered = [(kept[key][0], key, kept[key][1]) for key in majors if key in kept]
    return ordered[:MAX_SUBSYSTEM_PARAGRAPHS], len(offered)


def accept_description(text: str, evidence: OverviewEvidence, lookup: SymbolLookup) -> str | None:
    """A planned subsystem description fit for the table, rendered, or `None`.

    G1, G2, G4, G5 and G6 only (038 research Decision 6): the shape rules G3 and
    G7-G9 are for narrative paragraphs, not a one-line cell. `None` renders as
    a dash, exactly like a subsystem with no description (spec FR-021).
    """
    context = _Context(
        evidence=evidence,
        lookup=lookup,
        handle_map={},
        titles=evidence.feature_title_by_key(),
        allowed_camel=_allowed_camel_words(evidence),
    )
    collapsed = _WHITESPACE.sub(" ", text or "").strip()
    if not collapsed:
        return None
    segments = _segments(collapsed)
    if segments is None:
        return None
    parts: list[str] = []
    for segment in segments:
        if segment.kind == "feature":
            # A description is not a narrative: it may not link a subsystem.
            return None
        if segment.kind == "code":
            if segment.value != evidence.repositoryName and resolve_reference(lookup, segment.value) is None:
                return None
            parts.append(f"`{segment.value}`")
            continue
        if _unresolved_identifier(segment.value, context) is not None:
            return None
        if _SECOND_PERSON.search(segment.value) or _BANNED.search(segment.value):
            return None
        parts.append(_markdown_escape(segment.value))
    return "".join(parts).strip()


def render_paragraph(paragraph: GroundedParagraph, feature_links: Mapping[str, PageLink]) -> str:
    """One Markdown line. The template adds the `{: .ai-generated }` marker."""
    parts: list[str] = []
    for segment in paragraph.segments:
        if segment.kind == "text":
            parts.append(_markdown_escape(segment.value))
        elif segment.kind == "code":
            parts.append(f"`{segment.value}`")
        else:
            link = feature_links.get(segment.featureKey)
            label = link.label if link is not None else segment.value
            parts.append(f"[{_markdown_escape(label)}]({link.relativePath})" if link is not None else _markdown_escape(label))
    return "".join(parts).strip()


def _check(text: object, section: Section, index: int, context: _Context) -> GroundedParagraph | Rejection:
    if not isinstance(text, str):
        return Rejection(section, index, "G1")
    collapsed = _WHITESPACE.sub(" ", text).strip()
    if not collapsed:
        return Rejection(section, index, "G1")

    segments = _segments(collapsed)
    if segments is None:
        return Rejection(section, index, "G2", collapsed[:40])

    resolved: list[Segment] = []
    has_citation = False
    for segment in segments:
        if segment.kind == "feature":
            # G3: a handle this prompt issued, naming a feature that still exists.
            feature_key = context.handle_map.get(segment.value)
            if not feature_key or feature_key not in context.titles:
                return Rejection(section, index, "G3", segment.value)
            resolved.append(Segment("feature", context.titles[feature_key], feature_key))
        elif segment.kind == "code":
            # The repository's own name is real but is not a source fragment:
            # accepted, rendered as code, and not counted as a citation (G7).
            if segment.value == context.evidence.repositoryName:
                resolved.append(segment)
                continue
            # G4: a backticked name resolves to exactly one symbol or file - the
            # same predicate that turns it into a link on the page.
            if resolve_reference(context.lookup, segment.value) is None:
                return Rejection(section, index, "G4", segment.value)
            has_citation = True
            resolved.append(segment)
        else:
            unresolved = _unresolved_identifier(segment.value, context)
            if unresolved is not None:
                return Rejection(section, index, "G5", unresolved)
            # G6: house style, on prose only - a code name may legitimately
            # contain "your" or "modern".
            style = _SECOND_PERSON.search(segment.value) or _BANNED.search(segment.value)
            if style is not None:
                return Rejection(section, index, "G6", style.group(0))
            resolved.append(segment)

    # G7: every paragraph cites a real source fragment (constitution §2.4). A
    # subsystem link names a page, not a fragment, so it does not count.
    if not has_citation:
        return Rejection(section, index, "G7")

    rendered_words = sum(
        len(segment.value.split()) if segment.kind != "code" else 1 for segment in resolved
    )
    return GroundedParagraph(
        segments=tuple(resolved),
        wordCount=rendered_words,
        sentenceCount=_sentence_count(collapsed),
    )


def _segments(collapsed: str) -> list[Segment] | None:
    """Text, code and handle segments, or `None` when markup is left unbalanced (G2)."""
    segments: list[Segment] = []
    cursor = 0
    for match in _TOKEN.finditer(collapsed):
        if match.start() > cursor:
            segments.append(Segment("text", collapsed[cursor : match.start()]))
        if match.group(1) is not None:
            segments.append(Segment("code", match.group(1).strip()))
        else:
            segments.append(Segment("feature", match.group(2)))
        cursor = match.end()
    if cursor < len(collapsed):
        segments.append(Segment("text", collapsed[cursor:]))

    # G2: whatever the tokenizer did not consume must not still look like markup
    # it was meant to - a lone backtick, or brackets that are not a handle.
    for segment in segments:
        if segment.kind == "text" and ("`" in segment.value or "[[" in segment.value or "]]" in segment.value):
            return None
    return segments


def _sentence_count(collapsed: str) -> int:
    """G8's count: code spans masked, abbreviation stops not counted."""
    pieces = _SENTENCE_BREAK.split(_CODE_SPAN.sub("CODE", collapsed))
    count = 1
    for previous in pieces[:-1]:
        if not _ABBREVIATION_END.search(previous):
            count += 1
    return count


def _unresolved_identifier(text: str, context: _Context) -> str | None:
    """G5: the first identifier-shaped token in prose that names nothing real."""
    candidates: list[tuple[str, bool]] = []
    for match in _PATH_LIKE.finditer(text):
        token = match.group(0).rstrip(".")
        # "and/or", "read/write", "I/O" are prose. A path has an extension, an
        # underscore, or more than one separator.
        if "." in token.split("/")[-1] or "_" in token or token.count("/") >= 2:
            candidates.append((token, False))
    candidates += [(match.group(0), False) for match in _FILE_LIKE.finditer(text)]
    candidates += [(match.group(0), False) for match in _SNAKE_LIKE.finditer(text)]
    candidates += [(match.group(0), False) for match in _DOTTED_LIKE.finditer(text)]
    candidates += [(match.group(1), False) for match in _CALL_LIKE.finditer(text)]
    candidates += [(match.group(0), True) for match in _CAMEL_LIKE.finditer(text)]

    for token, is_camel in candidates:
        if is_camel and token in context.allowed_camel:
            continue
        if _resolves(token, context.lookup):
            continue
        return token
    return None


def _resolves(token: str, lookup: SymbolLookup) -> bool:
    if resolve_reference(lookup, token) is not None:
        return True
    # A dotted Python module path names a file: `pkg.module` is `pkg/module.py`
    # or `pkg/module/__init__.py`.
    if re.fullmatch(r"[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)+", token):
        as_path = token.replace(".", "/")
        return any(
            resolve_reference(lookup, candidate) is not None
            for candidate in (f"{as_path}.py", f"{as_path}/__init__.py")
        )
    return False


def _allowed_camel_words(evidence: OverviewEvidence) -> frozenset[str]:
    """CamelCase words the model did not invent.

    Languages ("TypeScript"), the repository's own name, and every word of the
    text the prompt carried from the repository itself - subsystem titles and
    descriptions, anchor summaries, the README's opening. "FastAPI" in an
    anchor summary is the repository describing its own stack; the model
    repeating it is not a fabrication. Anything else in CamelCase must resolve,
    because an un-backticked class name the evidence never mentions is exactly
    what a fabrication looks like.
    """
    words: set[str] = set(evidence.languages)
    words.add(evidence.repositoryName)
    texts = [evidence.repositoryName, evidence.readmeLead]
    texts += [title for _, title in evidence.featureTitles]
    for brief in evidence.features:
        texts += [brief.description, brief.anchorSummary]
    for text in texts:
        words.update(re.findall(r"[A-Za-z0-9]+", text))
    return frozenset(words)
