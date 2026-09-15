from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Mapping, Sequence

from .evidence import FeatureEvidence, RepositoryEvidence
from .fallback import Weight, build_fallback_groups, default_group_title, lead_module_key

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

# Where modules land when nothing else can hold them: 033 FR-014's bucket.
# Constructed explicitly rather than left to emerge from any other rule, because
# two rules that could both produce the last-resort bucket is how one of them
# silently stops running. Grouping builds it for modules left alone (039
# research Decision 6 step 5); repair joins its own leftovers to it. Defined here
# rather than in `validate`, which imports this module and re-exports the name.
TERMINAL_FEATURE_TITLE = "Support & Utilities"

# The terminal candidate's seed. Deliberately not a module key: the bucket has no
# seed module, and a placeholder that could collide with a real key would give
# two candidates one identity in repair.
TERMINAL_SEED_KEY = "features::terminal"


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
    adjacency: Mapping[str, Mapping[str, Weight]],
) -> tuple[Candidate, ...]:
    """Group every module into exactly one candidate, with no model call.

    The post-condition is the whole contract: the union of every candidate's
    `memberKeys` is the full set of module keys, and no two candidates
    intersect. Every downstream guarantee - the repair table, the "no orphaned
    module" property, the navigation's completeness - rests on it holding here.

    Six steps, all deterministic:

    1. seed one candidate per non-test module holding an entry point;
    2. attach every reachable production module to its nearest seed;
    3. group whatever no seed reached by structural clustering (`fallback`);
    4. fold: by coupling, then by directory, never into the largest group, and
       never an entry module into a group without one (`_Folding`);
    5. place each test file with the production code it exercises;
    6. count each candidate's entry points from its members (039 FR-007).

    Steps 1 to 4 see production modules only (039 FR-008). A test imports what
    it tests, so it is the best-connected module there is: seeding groups, it
    decided where production code was shown - on the sample repository 5 of 26
    seeds were tests, one titled "Tests (Test Fines)" holding the fine
    calculator. Placed last, a test can never move a production module.
    """
    evidence_by_key = evidence.by_module_key()
    if not evidence_by_key:
        return ()

    name_by_key = {key: item.moduleName for key, item in evidence_by_key.items()}
    directory_by_key = {key: item.directoryPath for key, item in evidence_by_key.items()}
    test_keys = frozenset(key for key in evidence.testModuleKeys if key in evidence_by_key)
    production = {key: item for key, item in evidence_by_key.items() if key not in test_keys}
    production_adjacency = {
        key: {neighbor: weight for neighbor, weight in adjacency.get(key, {}).items() if neighbor in production}
        for key in production
    }
    seeds = tuple(key for key in evidence.seedModuleKeys if key in production)

    owner_by_module = _assign_by_coupling(seeds, production, production_adjacency)

    grouped: dict[str, list[str]] = {}
    for module_key, seed in owner_by_module.items():
        grouped.setdefault(seed, []).append(module_key)

    groups = [
        _Group(seed=seed, title=_seed_title(seed, directory_by_key, name_by_key), members=set(member_keys))
        for seed, member_keys in grouped.items()
    ]

    # Everything no seed reached. Not a rare branch: `identify_entry_points`
    # skips prose files, so on a real run every README and every document in the
    # analysed repository arrives here.
    unreached = [production[key] for key in sorted(production) if key not in owner_by_module]
    for fallback_group in build_fallback_groups(unreached, production_adjacency):
        lead_name = name_by_key.get(fallback_group.leadModuleKey, fallback_group.leadModuleKey)
        groups.append(
            _Group(
                seed=fallback_group.leadModuleKey,
                title=default_group_title(fallback_group.directoryPath, lead_name, split=False),
                members=set(fallback_group.memberKeys),
            )
        )

    folding = _Folding(
        groups,
        entry_keys=frozenset(evidence.entryModuleKeys),
        directory_by_key=directory_by_key,
        name_by_key=name_by_key,
        adjacency=production_adjacency,
    )
    folding.run()
    folding.place_tests(sorted(test_keys), adjacency)
    folded = folding.result()

    candidates = [
        Candidate(
            seedModuleKey=group.seed,
            seedTitle=group.title,
            memberKeys=tuple(sorted(group.members, key=lambda key: (name_by_key.get(key, key), key))),
            # From the members, excluding tests, however they arrived: 033 summed
            # only the surviving candidates' own counts, so every fold dropped the
            # absorbed ones' and every `nextgen-wealth-ledger` feature showed 0.
            exposedEntryPointCount=sum(
                len(evidence.entryPointKeysByModuleKey.get(key, ()))
                for key in group.members
                if key not in test_keys
            ),
        )
        for group in folded
    ]
    return tuple(sorted(candidates, key=lambda candidate: (-len(candidate.memberKeys), candidate.seedModuleKey)))


def _seed_title(seed: str, directory_by_key: Mapping[str, str], name_by_key: Mapping[str, str]) -> str:
    # Qualified by the seed's package, never the bare module name. This
    # repository has eleven modules called `models` and eighteen called
    # `__init__`, so bare names would give four candidates the title
    # "models" - and `validate.py` rejects duplicate titles, so with no model
    # reachable three of those four features would be thrown away and
    # reassigned. The title a candidate carries when nothing named it has to
    # be usable on its own.
    return default_group_title(directory_by_key.get(seed, "."), name_by_key.get(seed, seed), split=True)


def _assign_by_coupling(
    seeds: Sequence[str],
    evidence_by_key: Mapping[str, FeatureEvidence],
    adjacency: Mapping[str, Mapping[str, Weight]],
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


@dataclass(slots=True)
class _Group:
    """A candidate while folding is still deciding its members."""

    seed: str
    title: str
    members: set[str] = field(default_factory=set)


class _Folding:
    """Fold groups too small to stand alone, then enforce the cap (039 research Decision 6).

    033 folded a group coupled to nothing into the *largest* survivor. With no
    Java or TypeScript coupling that put 93 of `nextgen-wealth-ledger`'s 109
    modules into one feature. Here nothing is ever chosen for its size:

    1. a small group folds into the survivor it is most coupled to;
    2. an **entry group** - one holding a command, a route or `main` - survives at
       any size and folds only into another entry group, by coupling or by
       directory (039 FR-006a), so a CLI is never absorbed into a script group;
    3. a small group coupled to nothing joins the survivor holding the most
       modules *directly* in its directory, then its parent's, stopping at the
       top-level directory: never climbing into the root from below, which is
       how an unconnected frontend and backend would meet (039 FR-006);
    4. small groups still unplaced combine per directory;
    5. what is still alone goes to the one terminal candidate;
    6. past `MAX_PROMPTED_CANDIDATES`, the smallest groups fold by the same
       rules, entry groups last and only into entry groups; one with no coupled
       target and none found by directory joins the group sharing the longest
       leading directory path with it.

    Every tie breaks on the seed key, and groups are visited smallest first, so
    the outcome is identical on every run. Folding moves members and never drops
    them, which is what keeps the partition total.

    When no group can stand alone - none reaches `MIN_CANDIDATE_MODULES` and
    none holds an entry module - steps 1 to 5 are skipped and the groups stay
    as they are, as in 033: there is nothing to fold into, and combining them
    all by directory would publish one feature holding the whole repository,
    which `validate` itself rejects as "not navigation" (owner decision,
    2026-09-15).
    """

    def __init__(
        self,
        groups: Sequence[_Group],
        *,
        entry_keys: frozenset[str],
        directory_by_key: Mapping[str, str],
        name_by_key: Mapping[str, str],
        adjacency: Mapping[str, Mapping[str, Weight]],
    ) -> None:
        self.groups = {group.seed: group for group in groups}
        self.entry_keys = entry_keys
        self.directory_by_key = directory_by_key
        self.name_by_key = name_by_key
        self.adjacency = adjacency
        # Placed test files; never counted when a directory is weighed.
        self.test_keys: frozenset[str] = frozenset()

    def run(self) -> None:
        if any(not self._is_small(group) or self._is_entry(group) for group in self.groups.values()):
            self._fold_small()
            self._combine_leftovers()
        self._enforce_cap()

    def result(self) -> list[_Group]:
        return sorted(self.groups.values(), key=lambda group: group.seed)

    # -- tests, once production grouping is final (039 FR-009) -------------

    def place_tests(self, test_keys: Sequence[str], adjacency: Mapping[str, Mapping[str, Weight]]) -> None:
        """Each test joins the group holding most of the production code it imports.

        Measured by summed import weight to production members, ties to the
        smaller seed key. A test importing no production code - fixtures - is
        placed by the directory walk, counting production modules only. Tests
        still unplaced combine per directory, while the cap allows a new group;
        a test left alone goes to the terminal candidate (research Decision 5).
        """
        self.test_keys = frozenset(test_keys)
        unplaced: list[str] = []
        for test in test_keys:
            scored = []
            for group in self.groups.values():
                weight = sum(
                    weight
                    for neighbor, weight in adjacency.get(test, {}).items()
                    if neighbor in group.members and neighbor not in self.test_keys
                )
                if weight > 0:
                    scored.append((-weight, group.seed))
            if scored:
                self.groups[min(scored)[1]].members.add(test)
            else:
                unplaced.append(test)

        leftovers: dict[str, list[str]] = {}
        for test in unplaced:
            probe = _Group(seed=test, title="", members={test})
            targets = [group for group in self.groups.values() if group.seed != TERMINAL_SEED_KEY]
            target = self._directory_target(probe, targets)
            if target is not None:
                self.groups[target].members.add(test)
            else:
                leftovers.setdefault(self.directory_by_key.get(test, "."), []).append(test)

        alone: set[str] = set()
        for directory, sharing in sorted(leftovers.items()):
            if len(sharing) < 2 or len(self.groups) >= MAX_PROMPTED_CANDIDATES:
                alone.update(sharing)
                continue
            lead = lead_module_key(tuple(sharing), adjacency, self.name_by_key)
            self.groups[lead] = _Group(
                seed=lead,
                title=default_group_title(directory, self.name_by_key.get(lead, lead), split=False),
                members=set(sharing),
            )
        if alone:
            self._add_to_terminal(alone)

    # -- steps 1 to 3 -------------------------------------------------------

    def _fold_small(self) -> None:
        """One small group at a time, smallest first: coupling, then directory.

        After every fold the order is taken again, because a fold changes which
        groups are coupled to what. Measured on the sample repository (039 T020),
        running every coupling fold before any directory placement instead let
        the data-seeding script - an entry module importing nearly everything -
        absorb the CLI and two route modules one small group at a time, the
        "Scripts" group this spec set out to remove. Placed group by group, the
        package `__init__` reaches the CLI through its directory first, and the
        grouping is the one research Decisions 1, 6 and 7 measured.
        """
        moved = True
        while moved:
            moved = False
            for group in self._smallest_first():
                if not self._is_small(group):
                    continue
                targets = self._survivors(excluding=group, entry_only=self._is_entry(group))
                target = self._coupled_target(group, targets) or self._directory_target(group, targets)
                if target is not None:
                    self._merge(group, into=target)
                    moved = True
                    break

    # -- steps 4 and 5 ------------------------------------------------------

    def _combine_leftovers(self) -> None:
        leftovers = [
            group
            for group in self._smallest_first()
            if self._is_small(group) and not self._is_entry(group)
        ]
        by_directory: dict[str, list[_Group]] = {}
        for group in leftovers:
            by_directory.setdefault(self._directory_of(group), []).append(group)

        alone: set[str] = set()
        for directory, sharing in sorted(by_directory.items()):
            members = {key for group in sharing for key in group.members}
            for group in sharing:
                del self.groups[group.seed]
            if len(sharing) < 2:
                alone |= members
                continue
            lead = lead_module_key(tuple(members), self.adjacency, self.name_by_key)
            lead_name = self.name_by_key.get(lead, lead)
            self.groups[lead] = _Group(
                seed=lead, title=default_group_title(directory, lead_name, split=False), members=members
            )

        if alone:
            self._add_to_terminal(alone)

    def _add_to_terminal(self, keys: set[str]) -> None:
        terminal = self.groups.setdefault(
            TERMINAL_SEED_KEY, _Group(seed=TERMINAL_SEED_KEY, title=TERMINAL_FEATURE_TITLE)
        )
        terminal.members |= keys

    # -- step 6 -------------------------------------------------------------

    def _enforce_cap(self) -> None:
        while len(self.groups) > MAX_PROMPTED_CANDIDATES:
            foldable = [group for group in self._smallest_first() if group.seed != TERMINAL_SEED_KEY]
            ordinary = [group for group in foldable if not self._is_entry(group)]
            group = (ordinary or foldable or [None])[0]
            if group is None:
                return
            entry_only = self._is_entry(group)
            targets = [
                other
                for other in self.groups.values()
                if other is not group
                and other.seed != TERMINAL_SEED_KEY
                and (not entry_only or self._is_entry(other))
            ]
            if not targets:
                return
            target = (
                self._coupled_target(group, targets)
                or self._directory_target(group, targets)
                or self._shared_path_target(group, targets)
            )
            self._merge(group, into=target)

    # -- targets ------------------------------------------------------------

    def _coupled_target(self, group: _Group, targets: Sequence[_Group]) -> str | None:
        scored = []
        for target in targets:
            weight = sum(
                weight
                for key in group.members
                for neighbor, weight in self.adjacency.get(key, {}).items()
                if neighbor in target.members
            )
            if weight > 0:
                scored.append((-weight, target.seed))
        return min(scored)[1] if scored else None

    def _directory_target(self, group: _Group, targets: Sequence[_Group]) -> str | None:
        """The target holding the most modules directly in the group's directory, then its parent's.

        A directory counts only its direct modules, never its subtree: counted
        by subtree, every root-level file would go to the group with the most
        modules anywhere below it, which is the largest group again.
        """
        for level in _directory_walk(self._directory_of(group)):
            scored = []
            for target in targets:
                held = sum(
                    1
                    for key in target.members
                    if key not in self.test_keys and self.directory_by_key.get(key) == level
                )
                if held:
                    scored.append((-held, target.seed))
            if scored:
                return min(scored)[1]
        return None

    def _shared_path_target(self, group: _Group, targets: Sequence[_Group]) -> str:
        own = _path_parts(self._directory_of(group))

        def shared(target: _Group) -> int:
            return max(
                _common_prefix_length(own, _path_parts(self.directory_by_key.get(key, ".")))
                for key in target.members
            )

        return min(targets, key=lambda target: (-shared(target), target.seed)).seed

    # -- helpers ------------------------------------------------------------

    def _smallest_first(self) -> list[_Group]:
        return sorted(self.groups.values(), key=lambda group: (len(group.members), group.seed))

    def _survivors(self, *, excluding: _Group, entry_only: bool) -> list[_Group]:
        return [
            group
            for group in self.groups.values()
            if group is not excluding
            and (not self._is_small(group) or self._is_entry(group))
            and (not entry_only or self._is_entry(group))
        ]

    def _is_small(self, group: _Group) -> bool:
        return len(group.members) < MIN_CANDIDATE_MODULES

    def _is_entry(self, group: _Group) -> bool:
        return not self.entry_keys.isdisjoint(group.members)

    def _directory_of(self, group: _Group) -> str:
        if group.seed in group.members:
            return self.directory_by_key.get(group.seed, ".")
        counts = Counter(self.directory_by_key.get(key, ".") for key in group.members)
        return min(counts.items(), key=lambda item: (-item[1], item[0]))[0]

    def _merge(self, group: _Group, *, into: str) -> None:
        self.groups[into].members |= group.members
        del self.groups[group.seed]


def _directory_walk(directory: str) -> list[str]:
    """`a/b/c`, `a/b`, `a`: the group's directory and its ancestors below the root.

    A group whose own directory is the root is placed by the root's modules; a
    group in a subdirectory never climbs into the root (039 FR-006).
    """
    parts = _path_parts(directory)
    if not parts:
        return ["."]
    return ["/".join(parts[:depth]) for depth in range(len(parts), 0, -1)]


def _path_parts(directory: str) -> tuple[str, ...]:
    return () if directory in ("", ".") else PurePosixPath(directory).parts


def _common_prefix_length(left: Sequence[str], right: Sequence[str]) -> int:
    length = 0
    for a, b in zip(left, right):
        if a != b:
            break
        length += 1
    return length


def anchor_module_key(
    member_keys: Sequence[str],
    adjacency: Mapping[str, Mapping[str, Weight]],
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
