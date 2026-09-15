"""Grouping diagnosis: seeds, candidates, the planner prompt, the cached plan, the repaired features.

Read-only; no provider. Usage: python planner_probe.py <repo-root>

Written for 033 (its outputs are `probe-*.033.txt`), extended for 039: the seeds
section reports 039's evidence roles, and a metrics section measures SC-001 to
SC-004 with no model. From 039 T006b the plan cache key covers the grouping, so
a plan cached for another grouping is not found and the repaired features are
the no-model ones.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path, PurePosixPath

from cli import paths
from dependency_graph import DependencyGraph
from doc_generator import open_doc_manifest_store
from doc_generator.features import imports as feature_imports
from doc_generator.features.candidates import build_candidates
from doc_generator.features.evidence import build_repository_evidence
from doc_generator.features.fallback import build_import_adjacency
from doc_generator.features.planner import (
    FeaturePlanner,
    assign_handles,
    build_feature_plan_prompt,
    plan_cache_key,
)
from doc_generator.features.validate import repair
from repository_metadata import RepositoryMetadataStore
from repository_metadata.sqlite_store import stable_repository_id

JS = feature_imports.JS_RESOLVE_EXTENSIONS


def rel(path: str, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        return path


def _language(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".java":
        return "Java"
    if suffix in (".ts", ".tsx"):
        return "TypeScript"
    if suffix in (".js", ".jsx", ".mjs", ".cjs"):
        return "JavaScript"
    return suffix or "(none)"


def _import_recognition(bundle, graph, root: Path, path_of: dict[str, str]):
    """SC-002, per import and per language, as the spec defines an in-repository import.

    Java: in the repository when it resolves, or when its package - the name
    without its class (and without the member, for a static import) - is the
    dotted form of a directory holding the repository's Java files.
    JS/TS: in the repository when relative.
    """
    key_by_path = {path: key for key, path in path_of.items()}
    java = feature_imports._JavaIndex(path_of)
    java_directories = {
        "/".join(parts[start:])
        for path in path_of.values()
        if path.endswith(".java")
        for parts in [PurePosixPath(path).parent.parts]
        for start in range(len(parts))
    }
    stats: Counter[tuple[str, str]] = Counter()
    for file_bundle in bundle.files:
        key = file_bundle.module.sourceFileId
        path = path_of[key]
        language = _language(path)
        if language not in ("Java", "TypeScript", "JavaScript"):
            continue
        for name in feature_imports._unresolved_import_names(graph, file_bundle.module.filePath):
            if language == "Java":
                resolved = java.resolve(name, importer=key) is not None
                bare = name.removeprefix("static ").strip()
                segments = bare.removesuffix(".*").split(".")
                drop = 0 if bare.endswith(".*") else (2 if name.startswith("static ") else 1)
                package = "/".join(segments[: len(segments) - drop])
                in_repo = resolved or package in java_directories
            else:
                resolved = feature_imports._resolve_relative(name, path, key_by_path) is not None
                in_repo = name.startswith(".")
            if in_repo:
                stats[(language, "in-repo")] += 1
                stats[(language, "resolved")] += int(resolved)
            else:
                stats[(language, "external")] += 1
    return stats


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    state = paths.repo_state_dir(root)
    store = RepositoryMetadataStore(paths.metadata_db_path(state))
    graph = DependencyGraph.load(paths.graph_db_path(state), graph_id=stable_repository_id(root))
    manifest = open_doc_manifest_store(paths.doc_manifest_db_path(state))
    bundle = store.load_repository(root)
    evidence = build_repository_evidence(bundle, graph, repository_root=root)
    adjacency = build_import_adjacency(bundle, graph, repository_root=root)
    by_key = evidence.by_module_key()
    path_of = {k: rel(v.filePath, root) for k, v in by_key.items()}
    eps = evidence.entryPointKeysByModuleKey

    print(
        f"== {root.name}: {len(evidence.modules)} modules, {len(evidence.seedModuleKeys)} seeds, "
        f"{len(evidence.entryModuleKeys)} entry modules, {len(evidence.testModuleKeys)} test modules"
    )
    for key in evidence.seedModuleKeys:
        role = "entry" if key in evidence.entryModuleKeys else "seed "
        print(f"   {role} {path_of.get(key, key)}  ({len(eps.get(key, ()))} entry points)")
    for key in sorted(evidence.testModuleKeys, key=lambda k: path_of.get(k, k)):
        print(f"   test  {path_of.get(key, key)}  ({len(eps.get(key, ()))} entry points)")

    candidates = build_candidates(evidence, adjacency)
    handled = assign_handles(candidates)
    print(f"\n-- {len(candidates)} candidates")
    for c in handled:
        members = [path_of.get(k, k) for k in c.memberKeys]
        shown = ", ".join(members[:6]) + (f", ... (+{len(members) - 6})" if len(members) > 6 else "")
        print(f"   {c.handle}: '{c.seedTitle}' seed={path_of.get(c.seedModuleKey, c.seedModuleKey)} n={len(members)} eps={c.exposedEntryPointCount}")
        print(f"       {shown}")

    print("\n-- planner prompt (what the model saw)")
    print(build_feature_plan_prompt(handled, evidence).promptText)

    planner = FeaturePlanner(None, cache=manifest, repositoryId=stable_repository_id(root))
    # 039 T006b: the key covers the grouping, so a plan cached for 033's groups
    # no longer matches and the repaired features below are the no-model ones.
    plan = planner._load_cached(plan_cache_key(evidence, candidates))
    print("-- cached plan:", "none" if plan is None else f"{len(plan.features)} features")
    for f in (plan.features if plan else ()):
        print(f"   [{f.kind}] {f.title} <- {list(f.memberCandidateIds)} :: {f.description}")

    features = repair(plan, candidates, evidence=evidence, adjacency=adjacency)
    print("\n-- repaired features (sidebar order)")
    for feature in features:
        print(f"   [{feature.kind}] {feature.title}  anchor={path_of.get(feature.key)} n={len(feature.members)} eps={feature.exposedEntryPointCount} planned={feature.isPlanned}")

    total = len(evidence.modules)
    non_test_eps = sum(len(v) for k, v in eps.items() if k not in evidence.testModuleKeys)
    largest = max(features, key=lambda f: len(f.members))
    by_language = Counter(_language(p) for p in path_of.values())
    coupled = Counter(_language(path_of[k]) for k, row in adjacency.items() if row)
    recognition = _import_recognition(bundle, graph, root, path_of)
    print("\n-- metrics (no model)")
    print(f"   SC-001 largest feature: {largest.title} {len(largest.members)}/{total} = {100 * len(largest.members) / total:.0f}%")
    for language in ("Java", "TypeScript", "JavaScript"):
        if by_language[language]:
            in_repo, resolved = recognition[(language, "in-repo")], recognition[(language, "resolved")]
            share = f"{100 * resolved / in_repo:.0f}%" if in_repo else "n/a"
            print(
                f"   SC-002 {language}: {resolved}/{in_repo} in-repository imports resolved ({share}), "
                f"{recognition[(language, 'external')]} external; modules coupled {coupled[language]}/{by_language[language]}"
            )
    print(f"   SC-003 groups seeded by a test file: {sum(1 for c in candidates if c.seedModuleKey in evidence.testModuleKeys)}")
    print(
        f"   SC-004 entry points: candidates {sum(c.exposedEntryPointCount for c in candidates)}, "
        f"features {sum(f.exposedEntryPointCount for f in features)}, non-test total {non_test_eps}"
    )
    feature_of = {k: f.title for f in features for k in f.moduleKeys}
    for key in evidence.entryModuleKeys:
        print(f"   entry module {path_of[key]} -> {feature_of.get(key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
