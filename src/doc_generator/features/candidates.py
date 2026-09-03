from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from .evidence import FeatureEvidence, RepositoryEvidence
from .fallback import build_fallback_groups, default_group_title, lead_module_key

# How far a seed's claim is allowed to travel, in undirected import hops - one
# propagation sweep per hop.
#
# **Two, not four.** Measured on this repository (139 modules, average degree
# 8.99): a seed reaches 10.4 modules at one hop, 132 of 139 at two, and all of
# them at three. Past two hops the relation "this seed reaches this module"
# carries no information, because it is true of very nearly every pair.
#
# Not a tuning nicety. Run at four, this stage produced one 64-module candidate
# and 41 singletons out of 52 - a grouping worse than the directory clustering
# it replaces. See specs/033-feature-navigation/research.md Decision 2.
MAX_ATTACH_DISTANCE = 2

# A one-module candidate is navigation noise rather than a capability, and it
# spends a prompt line saying so.
MIN_CANDIDATE_MODULES = 2

# The dominant term in the planner's token budget: 32 x 540 chars of prompt.
# Raising this raises the prompt, which is why `test_feature_planner.py`
# computes the ceiling from this constant rather than restating the answer.
MAX_PROMPTED_CANDIDATES = 32


@dataclass(frozen=True, slots=True)
class Candidate:
    """A provisional group of modules, seeded by one entry-point module.

    **This is the unit the planner organises and the unit repair operates on.**
    Assigning candidates rather than individual modules is what makes an
    orphaned module structurally impossible: every module belongs to exactly one
    candidate, and a candidate is indivisible, so no answer the model can give
    and no repair rule can leave a module belonging to no feature.
    """

    seedModuleKey: str
    seedTitle: str
    memberKeys: tuple[str, ...] = ()
    exposedEntryPointCount: int = 0
    #: Assigned by position at prompt-construction time, in `planner.py`. Not
    #: part of a candidate's identity: it never reaches storage and never
    #: appears in a page id, so two runs may number the same candidate
    #: differently with no consequence - a handle only ever lives inside one
    #: call.
    handle: str = ""


def build_candidates(
    evidence: RepositoryEvidence,
    adjacency: Mapping[str, Mapping[str, int]],
) -> tuple[Candidate, ...]:
    """Group every module into exactly one candidate, with no model call.

    The post-condition is the whole contract: the union of every candidate's
    `memberKeys` is the full set of module keys, and no two candidates
    intersect. Every downstream guarantee - the repair table, the "no orphaned
    module" property, the navigation's completeness - rests on it holding here.

    Four steps, all deterministic:

    1. seed one candidate per distinct entry-point module;
    2. attach every reachable module to its nearest seed;
    3. group whatever no seed reached by structural clustering (`fallback`);
    4. consolidate: fold the too-small, cap the survivors.
    """
    evidence_by_key = evidence.by_module_key()
    if not evidence_by_key:
        return ()

    name_by_key = {key: item.moduleName for key, item in evidence_by_key.items()}
    seeds = tuple(key for key in evidence.entryPointModuleKeys if key in evidence_by_key)

    owner_by_module = _assign_by_coupling(seeds, evidence_by_key, adjacency)

    grouped: dict[str, list[str]] = {}
    for module_key, seed in owner_by_module.items():
        grouped.setdefault(seed, []).append(module_key)

    candidates = [
        _build_candidate(seed, member_keys, evidence, adjacency, name_by_key)
        for seed, member_keys in grouped.items()
    ]

    # Everything no seed reached. Not a rare branch: `identify_entry_points`
    # skips prose files, so on a real run every README and every document in the
    # analysed repository arrives here.
    unreached = [
        evidence_by_key[key] for key in sorted(evidence_by_key) if key not in owner_by_module
    ]
    for group in build_fallback_groups(unreached, adjacency):
        lead_name = name_by_key.get(group.leadModuleKey, group.leadModuleKey)
        candidates.append(
            Candidate(
                seedModuleKey=group.leadModuleKey,
                seedTitle=default_group_title(group.directoryPath, lead_name, split=False),
                memberKeys=group.memberKeys,
                exposedEntryPointCount=0,
            )
        )

    return _consolidate(candidates, adjacency, name_by_key)


def _build_candidate(
    seed: str,
    member_keys: Sequence[str],
    evidence: RepositoryEvidence,
    adjacency: Mapping[str, Mapping[str, int]],
    name_by_key: Mapping[str, str],
) -> Candidate:
    ordered = tuple(sorted(member_keys, key=lambda key: (name_by_key.get(key, key), key)))
    exposed = sum(
        len(evidence.entryPointKeysByModuleKey.get(member_key, ())) for member_key in ordered
    )
    seed_evidence = evidence.by_module_key().get(seed)
    return Candidate(
        seedModuleKey=seed,
        # Qualified by the seed's package, never the bare module name. This
        # repository has eleven modules called `models` and eighteen called
        # `__init__`, so bare names would give four candidates the title
        # "models" - and `validate.py` rejects duplicate titles, so with no model
        # reachable three of those four features would be thrown away and
        # reassigned. The title a candidate carries when nothing named it has to
        # be usable on its own.
        seedTitle=default_group_title(
            seed_evidence.directoryPath if seed_evidence else ".",
            name_by_key.get(seed, seed),
            split=True,
        ),
        memberKeys=ordered,
        exposedEntryPointCount=exposed,
    )


def _assign_by_coupling(
    seeds: Sequence[str],
    evidence_by_key: Mapping[str, FeatureEvidence],
    adjacency: Mapping[str, Mapping[str, int]],
) -> dict[str, str]:
    """Assign each module to the seed its imports are most coupled to.

    **Coupling, not hop distance** - and that distinction was forced by
    measurement, not chosen for elegance.

    Scoring by `1/(1+d)` and breaking ties on the seed key put 109 of this
    repository's 139 modules into a single candidate. The cause is that hop
    distance is not a coupling measure on a graph with hubs: `src/chat/models.py`
    has degree 102 and `src/chat/budget.py` has degree 131, so nearly every
    module sits two hops from nearly every seed. 62 of 139 modules tied at their
    minimum distance - some across seven seeds at once - and the tie-break then
    decided the whole grouping. `models` won not because it is central to those
    modules but because its key sorts first.

    So this is seeded label propagation instead, weighted by summed import
    weight: the rule `fallback._coupling_target` and `fallback._label_propagation`
    already use, reused rather than reinvented. A module with three edges into
    one group and one into another goes to the first, whatever the hop counts
    are, and a hub contributes one edge's worth to each neighbour rather than
    dragging every module within two hops along with it.

    Determinism comes from the two places label propagation is normally random:
    modules are swept in sorted key order, never a set's order, and the
    strongest-label tie breaks on the label string. Seeds are frozen - an
    entry-point module defines its own candidate and never migrates.

    One sweep propagates one hop, so `MAX_ATTACH_DISTANCE` bounds the distance a
    seed's claim can travel exactly as its name says (FR-006).
    """
    labels: dict[str, str] = {seed: seed for seed in seeds}
    if not labels:
        return {}

    seed_set = set(seeds)
    sweep_order = sorted(key for key in evidence_by_key if key not in seed_set)

    for _sweep in range(MAX_ATTACH_DISTANCE):
        changed = False
        # Read from the previous sweep's labels rather than from the map being
        # written, so a module's assignment cannot depend on how far through the
        # sweep its neighbours happen to be.
        settled = dict(labels)
        for module_key in sweep_order:
            weights: Counter[str] = Counter()
            for neighbor_key, weight in adjacency.get(module_key, {}).items():
                label = settled.get(neighbor_key)
                if label is not None:
                    weights[label] += weight
            if not weights:
                continue
            best = min(weights.items(), key=lambda item: (-item[1], item[0]))[0]
            if labels.get(module_key) != best:
                labels[module_key] = best
                changed = True
        if not changed:
            break

    return {key: label for key, label in labels.items() if key in evidence_by_key}


def _consolidate(
    candidates: Sequence[Candidate],
    adjacency: Mapping[str, Mapping[str, int]],
    name_by_key: Mapping[str, str],
) -> tuple[Candidate, ...]:
    """Fold the too-small, then cap the survivors, folding the remainder too.

    Both passes fold rather than drop, which is what keeps the partition total:
    a candidate that disappears here must have handed its members to another
    one, never released them.
    """
    if not candidates:
        return ()

    ranked = sorted(candidates, key=lambda c: (-len(c.memberKeys), c.seedModuleKey))
    survivors = [c for c in ranked if len(c.memberKeys) >= MIN_CANDIDATE_MODULES]
    if not survivors:
        # Nothing meets the minimum - a repository of entry points that share no
        # helpers. The largest candidates still have to be the targets, because
        # *something* must absorb the rest: an empty survivor list here used to
        # fall through to a plain truncation, which silently dropped every module
        # past the cap and broke the partition at the one step meant to tidy it.
        survivors = ranked[:MAX_PROMPTED_CANDIDATES]

    if len(survivors) > MAX_PROMPTED_CANDIDATES:
        survivors = survivors[:MAX_PROMPTED_CANDIDATES]

    surviving_seeds = {candidate.seedModuleKey for candidate in survivors}
    absorbed = [c for c in ranked if c.seedModuleKey not in surviving_seeds]

    members_by_seed = {c.seedModuleKey: list(c.memberKeys) for c in survivors}
    for candidate in absorbed:
        target = _best_absorption_target(candidate, survivors, adjacency)
        members_by_seed[target].extend(candidate.memberKeys)

    return tuple(
        sorted(
            (
                replace(
                    candidate,
                    memberKeys=tuple(
                        sorted(
                            set(members_by_seed[candidate.seedModuleKey]),
                            key=lambda key: (name_by_key.get(key, key), key),
                        )
                    ),
                )
                for candidate in survivors
            ),
            key=lambda candidate: (-len(candidate.memberKeys), candidate.seedModuleKey),
        )
    )


def _best_absorption_target(
    candidate: Candidate,
    survivors: Sequence[Candidate],
    adjacency: Mapping[str, Mapping[str, int]],
) -> str:
    """The surviving candidate most coupled to this one's members.

    Ties break on the target's seed key, and a candidate coupled to nothing goes
    to the largest survivor - an arbitrary but *stated* answer, rather than
    whichever one a dict happened to yield first.
    """
    orphan_keys = set(candidate.memberKeys)
    scored: list[tuple[int, str]] = []
    for survivor in survivors:
        survivor_keys = set(survivor.memberKeys)
        weight = sum(
            weight
            for key in orphan_keys
            for neighbor, weight in adjacency.get(key, {}).items()
            if neighbor in survivor_keys
        )
        scored.append((weight, survivor.seedModuleKey))
    best_weight, best_seed = min(scored, key=lambda item: (-item[0], item[1]))
    if best_weight > 0:
        return best_seed
    return survivors[0].seedModuleKey


def anchor_module_key(
    member_keys: Sequence[str],
    adjacency: Mapping[str, Mapping[str, int]],
    name_by_key: Mapping[str, str],
) -> str:
    """A feature's anchor: its most internally connected member.

    The same rule `fallback.lead_module_key` uses to name a cluster, reused
    deliberately rather than reimplemented - the module that best names a group
    and the module that addresses its page must be the same one, or the page has
    two identities.
    """
    return lead_module_key(member_keys, adjacency, name_by_key)


def evidence_for(evidence: RepositoryEvidence, member_keys: Sequence[str]) -> list[FeatureEvidence]:
    by_key = evidence.by_module_key()
    return [by_key[key] for key in member_keys if key in by_key]
