"""Deterministic repair of a planned feature set. No model, ever.

Takes no LLM engine argument - see this package's docstring. Every rule below is
exercised on hand-written input, which is what makes each row of the repair table
its own test rather than something inferred from an end-to-end run.

The reason repair is *safe* lives one module away, in `candidates`: every module
belongs to exactly one candidate, and a candidate is indivisible. So no answer
the model can give and no rule here can leave a module belonging to no feature.
That failure mode is designed out rather than repaired, and `repair`'s
post-condition asserts the design held.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Mapping, Sequence

from .candidates import TERMINAL_FEATURE_TITLE, Candidate, anchor_for
from .fallback import Weight
from .evidence import RepositoryEvidence

FeatureKind = Literal["overview", "capability", "subsystem", "tooling"]

# General to specific. The sidebar reads top to bottom, so the entry describing
# the whole comes before the entries describing its parts, and incidental
# tooling comes last rather than being interleaved alphabetically.
KIND_RANK: Mapping[str, int] = {"overview": 0, "capability": 1, "subsystem": 2, "tooling": 3}

# What a feature is called when the plan named a kind nobody recognises. A
# *default*, not a rejection: `kind` only affects ordering, so discarding an
# otherwise good title and description over a misspelled enum would be the worse
# outcome for the reader.
DEFAULT_FEATURE_KIND: FeatureKind = "subsystem"

# A feature's name is navigation chrome - it sits in the sidebar on every page
# and has to stay on one line. Inherited unchanged from `section_narrator`.
MAX_TITLE_CHARACTERS = 60

# One feature holding the whole repository is not navigation. Below this, the
# plan is discarded in favour of the deterministic candidates.
MIN_PLANNED_FEATURES = 2

# Where candidates land when no feature claimed them and none could be built
# from them alone. `TERMINAL_FEATURE_TITLE` is imported from `candidates`, which
# builds the same bucket for modules grouping left alone (039 research
# Decision 6 step 5); there is still exactly one bucket, and it is tooling.
TERMINAL_FEATURE_KIND: FeatureKind = "tooling"


@dataclass(frozen=True, slots=True)
class FeatureMember:
    """One module inside a feature, keyed by the same stable ``sourceFileId``
    the module's own page is keyed by."""

    moduleKey: str
    name: str
    filePath: str
    docstring: str = ""
    generatedSummary: str = ""


@dataclass(frozen=True, slots=True)
class Feature:
    """A published capability of the repository.

    ``key`` **is** the anchor module's key - one identifier, not a composite.
    That is what lets `links.feature_slug` take a single argument, and what makes
    the alias table's job small enough to be correct.
    """

    key: str
    title: str
    description: str = ""
    kind: FeatureKind = DEFAULT_FEATURE_KIND
    members: tuple[FeatureMember, ...] = ()
    internalEdges: tuple[tuple[str, str], ...] = ()
    neighborKeys: tuple[str, ...] = ()
    exposedEntryPointCount: int = 0
    #: Whether a model named this feature. Only a planned feature's description
    #: can become the Overview's responsibility cell; a feature that fell back to
    #: its deterministic title has no model-written description to show.
    isPlanned: bool = False

    @property
    def anchorModuleKey(self) -> str:
        return self.key

    @property
    def moduleKeys(self) -> tuple[str, ...]:
        return tuple(member.moduleKey for member in self.members)


@dataclass(frozen=True, slots=True)
class PlannedFeature:
    """One entry of the model's answer, before any of it is trusted."""

    title: str
    description: str = ""
    kind: str = ""
    memberCandidateIds: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FeaturePlan:
    features: tuple[PlannedFeature, ...] = ()


def repair(
    plan: FeaturePlan | None,
    candidates: Sequence[Candidate],
    *,
    evidence: RepositoryEvidence,
    adjacency: Mapping[str, Mapping[str, Weight]],
) -> tuple[Feature, ...]:
    """Turn a plan - or no plan at all - into a usable feature set.

    `plan=None` is not an error path bolted on afterwards: it is the same code
    path as an unreachable model, a refused call and an unparseable answer, and
    it produces one feature per candidate under its deterministic title. That
    equivalence is what makes the no-model wiki navigate identically.
    """
    if not candidates:
        return ()

    grouped = _grouped_candidates(plan, candidates)
    if len(grouped) < MIN_PLANNED_FEATURES:
        # A "plan" that collapses the repository into one entry is not
        # navigation. Discard the whole answer rather than publish it.
        grouped = [
            (candidate.seedTitle, "", _unplanned_kind(candidate.seedTitle), [candidate], False)
            for candidate in candidates
        ]

    return _build_features(grouped, evidence=evidence, adjacency=adjacency)


def _grouped_candidates(
    plan: FeaturePlan | None, candidates: Sequence[Candidate]
) -> list[tuple[str, str, str, list[Candidate], bool]]:
    """Apply the repair table, returning (title, description, kind, members, planned)."""
    by_handle = {f"c{index}": candidate for index, candidate in enumerate(candidates)}
    claimed: set[str] = set()
    used_titles: set[str] = set()
    grouped: list[tuple[str, str, str, list[Candidate], bool]] = []

    for planned in plan.features if plan is not None else ():
        members: list[Candidate] = []
        for handle in planned.memberCandidateIds:
            candidate = by_handle.get(handle)
            if candidate is None:
                # A handle naming no known candidate. Silently ignored: the
                # model inventing an identifier says nothing about the
                # candidates that do exist.
                continue
            if candidate.seedModuleKey in claimed:
                # Named by an earlier feature already. Kept in the first, removed
                # from the rest - "first" so the outcome does not depend on which
                # feature the model happened to list last.
                continue
            members.append(candidate)
            claimed.add(candidate.seedModuleKey)

        if not members:
            # Empty after repair. Dropping it is right: a feature with no modules
            # is a title with nothing behind it.
            continue

        title = " ".join(planned.title.split()).strip()
        if not title or len(title) > MAX_TITLE_CHARACTERS or title.casefold() in used_titles:
            # Rejected, and its candidates released back to the unplaced pool
            # below rather than published under a title the sidebar cannot show.
            for candidate in members:
                claimed.discard(candidate.seedModuleKey)
            continue

        used_titles.add(title.casefold())
        kind = planned.kind.strip().lower()
        if kind not in KIND_RANK:
            kind = DEFAULT_FEATURE_KIND
        grouped.append((title, " ".join(planned.description.split()).strip(), kind, members, True))

    unplaced = [c for c in candidates if c.seedModuleKey not in claimed]
    if unplaced:
        grouped.extend(_place_remainder(unplaced, used_titles, has_plan=bool(grouped)))
    return _one_terminal_feature(grouped)


def _one_terminal_feature(
    grouped: list[tuple[str, str, str, list[Candidate], bool]],
) -> list[tuple[str, str, str, list[Candidate], bool]]:
    """At most one feature carries `TERMINAL_FEATURE_TITLE` (039 FR-006, analyze I2).

    Since 039, grouping builds a terminal candidate of its own, so repair's
    bucket can meet a feature already titled like it - the terminal candidate
    placed under its own title, or a planned feature the model named so. The
    bucket joins that feature rather than publishing a second one with the
    same name.
    """
    first: int | None = None
    kept: list[tuple[str, str, str, list[Candidate], bool]] = []
    for entry in grouped:
        if entry[0].casefold() != TERMINAL_FEATURE_TITLE.casefold():
            kept.append(entry)
            continue
        if first is None:
            first = len(kept)
            kept.append(entry)
            continue
        title, description, kind, members, planned = kept[first]
        kept[first] = (title, description, kind, [*members, *entry[3]], planned)
    return kept


def _unplanned_kind(title: str) -> str:
    """A feature no model named is a subsystem, unless it is the terminal bucket."""
    if title.casefold() == TERMINAL_FEATURE_TITLE.casefold():
        return TERMINAL_FEATURE_KIND
    return DEFAULT_FEATURE_KIND


def _place_remainder(
    unplaced: Sequence[Candidate], used_titles: set[str], *, has_plan: bool
) -> list[tuple[str, str, str, list[Candidate], bool]]:
    """Candidates no surviving feature claimed.

    Each becomes its own feature under its deterministic seed title. Only those
    whose seed title is unusable - empty, over-long, or already taken by a
    planned feature - fall through to the terminal bucket, which is built once,
    explicitly, at the end.
    """
    placed: list[tuple[str, str, str, list[Candidate], bool]] = []
    terminal: list[Candidate] = []

    for candidate in unplaced:
        title = " ".join(candidate.seedTitle.split()).strip()
        if not title or len(title) > MAX_TITLE_CHARACTERS or title.casefold() in used_titles:
            terminal.append(candidate)
            continue
        used_titles.add(title.casefold())
        placed.append((title, "", _unplanned_kind(title), [candidate], False))

    if terminal:
        placed.append((TERMINAL_FEATURE_TITLE, "", TERMINAL_FEATURE_KIND, terminal, False))
    return placed


def _build_features(
    grouped: Sequence[tuple[str, str, str, list[Candidate], bool]],
    *,
    evidence: RepositoryEvidence,
    adjacency: Mapping[str, Mapping[str, Weight]],
) -> tuple[Feature, ...]:
    evidence_by_key = evidence.by_module_key()
    name_by_key = {key: item.moduleName for key, item in evidence_by_key.items()}

    features: list[Feature] = []
    for title, description, kind, members, planned in grouped:
        member_keys = sorted(
            {key for candidate in members for key in candidate.memberKeys},
            key=lambda key: (name_by_key.get(key, key), key),
        )
        if not member_keys:
            continue
        # Entry module, then seed, then most connected (039 FR-010). Computed
        # here, after the model's merges, so a merge keeps the anchor a reader
        # should open rather than whichever helper connects the merged parts.
        anchor = anchor_for(member_keys, evidence, adjacency, name_by_key)
        member_set = set(member_keys)
        internal_edges = sorted(
            {
                (min(key, neighbor), max(key, neighbor))
                for key in member_keys
                for neighbor in adjacency.get(key, {})
                if neighbor in member_set
            }
        )
        features.append(
            Feature(
                key=anchor,
                title=title,
                description=description,
                kind=kind,  # type: ignore[arg-type]
                members=tuple(
                    _member(evidence_by_key.get(key), key) for key in member_keys
                ),
                internalEdges=tuple(internal_edges),
                # From the members, not the candidates' own counts, so a model's
                # merge can drop none of them, and tests never count (039 FR-007).
                exposedEntryPointCount=sum(
                    len(evidence.entryPointKeysByModuleKey.get(key, ()))
                    for key in member_keys
                    if key not in evidence.testModuleKeys
                ),
                isPlanned=planned,
            )
        )

    features = _resolve_anchor_collisions(features, name_by_key)
    return _with_neighbors(tuple(features), adjacency)


def _resolve_anchor_collisions(
    features: Sequence[Feature], name_by_key: Mapping[str, str]
) -> list[Feature]:
    """Two features must never share a key, because a key *is* a page address.

    Cannot happen while candidates partition the repository - two features hold
    disjoint modules, and an anchor is always a member. It is asserted
    anyway because the cost of being wrong is two features overwriting each
    other's page, which would look like one of them silently disappearing.
    """
    seen: dict[str, Feature] = {}
    resolved: list[Feature] = []
    for feature in features:
        if feature.key not in seen:
            seen[feature.key] = feature
            resolved.append(feature)
            continue
        fallback = next(
            (key for key in feature.moduleKeys if key not in seen), feature.moduleKeys[0]
        )
        seen[fallback] = feature
        resolved.append(replace(feature, key=fallback))
    return resolved


def _with_neighbors(
    features: tuple[Feature, ...], adjacency: Mapping[str, Mapping[str, Weight]]
) -> tuple[Feature, ...]:
    feature_key_by_module = {
        member.moduleKey: feature.key for feature in features for member in feature.members
    }
    resolved: list[Feature] = []
    for feature in features:
        neighbor_keys: set[str] = set()
        for member in feature.members:
            for neighbor in adjacency.get(member.moduleKey, {}):
                other = feature_key_by_module.get(neighbor)
                if other is not None and other != feature.key:
                    neighbor_keys.add(other)
        resolved.append(replace(feature, neighborKeys=tuple(sorted(neighbor_keys))))
    return tuple(sorted(resolved, key=feature_sort_key))


def feature_sort_key(feature: Feature) -> tuple[int, int, str]:
    """General to specific, then by how much of the repository a feature exposes.

    Today's navigation sorts alphabetically by directory path, which cannot
    express "overview before detail". This can.
    """
    return (KIND_RANK.get(feature.kind, KIND_RANK[DEFAULT_FEATURE_KIND]), -feature.exposedEntryPointCount, feature.title)


def _member(item, module_key: str) -> FeatureMember:
    if item is None:
        return FeatureMember(moduleKey=module_key, name=module_key, filePath="")
    return FeatureMember(
        moduleKey=item.moduleKey,
        name=item.moduleName,
        filePath=item.filePath,
        docstring=item.docstring,
        generatedSummary=item.generatedSummary,
    )
