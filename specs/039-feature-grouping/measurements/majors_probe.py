"""Per subsystem: kind, members split into prose/test/code, and whether it is a major today.

Usage: python majors_probe.py <repo-root>   (read-only; no provider)
"""

from __future__ import annotations

import sys
from pathlib import Path

from cli import paths
from dependency_graph import DependencyGraph
from doc_generator import DocGenerator, FeaturePlanner, open_doc_manifest_store
from doc_generator.overview.evidence import _relative_path, build_overview_evidence, is_test_path
from doc_generator.prose import is_prose_file
from repository_metadata import RepositoryMetadataStore
from repository_metadata.sqlite_store import stable_repository_id


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    state = paths.repo_state_dir(root)
    store = RepositoryMetadataStore(paths.metadata_db_path(state))
    graph = DependencyGraph.load(paths.graph_db_path(state), graph_id=stable_repository_id(root))
    manifest = open_doc_manifest_store(paths.doc_manifest_db_path(state))
    generator = DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest,
        outputRoot=state / "probe-unused",
        repositoryRoot=root,
        featurePlanner=FeaturePlanner(None, cache=manifest),
    )
    features = generator._ensure_features()
    evidence = build_overview_evidence(features, generator._ensure_bundle(), graph, repository_root=root)
    majors = set(evidence.majorFeatureKeys)
    for index, feature in enumerate(features):
        rels = [_relative_path(m.filePath, root) for m in feature.members]
        prose = sum(1 for r in rels if is_prose_file(r))
        tests = sum(1 for r in rels if not is_prose_file(r) and is_test_path(r))
        code = len(rels) - prose - tests
        tag = "MAJOR" if feature.key in majors else "     "
        print(f"{index:2} {tag} {feature.kind:10} code={code:3} test={tests:2} prose={prose:2} eps={feature.exposedEntryPointCount:2}  {feature.title}")
        if len(rels) <= 6:
            print("        " + ", ".join(rels))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
