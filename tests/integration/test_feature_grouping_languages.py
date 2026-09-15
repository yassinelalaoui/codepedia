"""Spec 039 end to end: a Java backend and a TypeScript frontend grouped by their imports.

Before 039 neither language had coupling at all (spec Background): every group
of this repository would have been a lone seed, folded into whichever survivor
was largest. Run with no planner, exactly as the generator's `_ensure_features`
runs when no model is reachable, so what is asserted is the grouping itself.
"""

from __future__ import annotations

import json
from pathlib import Path

from doc_generator.features.candidates import build_candidates
from doc_generator.features.evidence import build_repository_evidence
from doc_generator.features.fallback import build_import_adjacency
from doc_generator.features.validate import repair

from ._doc_generator_support import index_repo

JAVA = "backend/src/main/java/com/acme"


def _java_class(package: str, name: str, imports: tuple[str, ...] = (), body: str = "") -> str:
    lines = [f"package {package};", ""]
    lines += [f"import {target};" for target in imports]
    return "\n".join(lines + ["", f"public class {name} {{", body, "}", ""])


SOURCES = {
    f"{JAVA}/Application.java": _java_class(
        "com.acme", "Application", body="    public static void main(String[] args) {}"
    ),
    **{
        f"{JAVA}/web/{area}Controller.java": _java_class(
            "com.acme.web",
            f"{area}Controller",
            (f"com.acme.service.{area}Service", f"com.acme.dto.{area.lower()}.*", *extra),
            body="    public String list() { return \"\"; }",
        )
        for area, extra in (
            ("Wallet", ("com.acme.exceptions.WalletException",)),
            ("Auth", ("com.acme.exceptions.AuthException",)),
            ("Client", ()),
        )
    },
    **{
        f"{JAVA}/service/{area}Service.java": _java_class(
            "com.acme.service", f"{area}Service", body="    public void run() {}"
        )
        for area in ("Wallet", "Auth", "Client")
    },
    **{
        f"{JAVA}/dto/{area}/{name}.java": _java_class(f"com.acme.dto.{area}", name, body="    private String value;")
        for area, name in (
            ("wallet", "WalletDto"),
            ("wallet", "TransferDto"),
            ("wallet", "BalanceDto"),
            ("auth", "LoginDto"),
            ("auth", "TokenDto"),
            ("client", "ClientDto"),
        )
    },
    **{
        f"{JAVA}/exceptions/{name}.java": _java_class("com.acme.exceptions", name)
        for name in ("WalletException", "AuthException")
    },
    "frontend/src/app/wallets/wallets.component.ts": (
        "import { Component } from '@angular/core';\n"
        "import { WalletsService } from './wallets.service';\n"
        "import { shared } from '../shared';\n\n"
        "export class WalletsComponent {\n  show() { return shared; }\n}\n"
    ),
    "frontend/src/app/wallets/wallets.service.ts": "export class WalletsService {\n  load() { return 1; }\n}\n",
    "frontend/src/app/shared/index.ts": "export const shared = 1;\n",
    "frontend/src/app/auth/login.component.ts": (
        "import { AuthService } from './auth.service';\n\n"
        "export class LoginComponent {\n  submit() { return 1; }\n}\n"
    ),
    "frontend/src/app/auth/auth.service.ts": "export class AuthService {\n  login() { return 1; }\n}\n",
    "frontend/src/app/clients/clients.component.ts": (
        "import { ClientsService } from './clients.service';\n\n"
        "export class ClientsComponent {\n  open() { return 1; }\n}\n"
    ),
    "frontend/src/app/clients/clients.service.ts": "export class ClientsService {\n  all() { return 1; }\n}\n",
    # No functions, so no entry points and no seed: a group formed by directory.
    "frontend/src/app/theme/colors.ts": "export const primary = '#004';\n",
    "frontend/src/app/theme/palette.ts": "import { primary } from './colors';\n\nexport const palette = [primary];\n",
}


def _write_sources(tmp_path: Path) -> Path:
    root = tmp_path / "wealth"
    for relative, text in SOURCES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _index(tmp_path: Path, root: Path, db_name: str):
    return index_repo(tmp_path, root, [root / relative for relative in SOURCES], db_name)


def _indexed(tmp_path: Path):
    root = _write_sources(tmp_path)
    store, graph = _index(tmp_path, root, "wealth.sqlite")
    return root, store.load_repository(root), graph


def _features(root: Path, bundle, graph):
    evidence = build_repository_evidence(bundle, graph, repository_root=root)
    adjacency = build_import_adjacency(bundle, graph, repository_root=root)
    return repair(None, build_candidates(evidence, adjacency), evidence=evidence, adjacency=adjacency)


def _paths(root: Path, bundle) -> dict[str, str]:
    return {
        fb.module.sourceFileId: Path(fb.module.filePath).resolve().relative_to(root.resolve()).as_posix()
        for fb in bundle.files
    }


def _feature_of(features, path_by_key: dict[str, str]) -> dict[str, int]:
    return {path_by_key[key]: index for index, feature in enumerate(features) for key in feature.moduleKeys}


def test_java_and_typescript_modules_are_grouped_by_their_imports(tmp_path):
    root, bundle, graph = _indexed(tmp_path)
    path_by_key = _paths(root, bundle)

    features = _features(root, bundle, graph)
    feature_of = _feature_of(features, path_by_key)

    claimed = [key for feature in features for key in feature.moduleKeys]
    assert len(claimed) == len(set(claimed)) == len(bundle.files), "every module in exactly one feature"

    largest = max(len(feature.members) for feature in features)
    assert largest <= 0.3 * len(bundle.files), f"no feature over 30% (SC-001); largest is {largest}"

    for area, dtos in (("Wallet", ("wallet/WalletDto", "wallet/TransferDto", "wallet/BalanceDto")), ("Auth", ("auth/LoginDto", "auth/TokenDto"))):
        slice_ = {
            f"{JAVA}/web/{area}Controller.java",
            f"{JAVA}/service/{area}Service.java",
            *(f"{JAVA}/dto/{dto}.java" for dto in dtos),
        }
        assert len({feature_of[path] for path in slice_}) == 1, f"the {area} controller, its service and its DTOs"

    for component, service in (
        ("wallets/wallets.component.ts", "wallets/wallets.service.ts"),
        ("auth/login.component.ts", "auth/auth.service.ts"),
        ("clients/clients.component.ts", "clients/clients.service.ts"),
    ):
        assert feature_of[f"frontend/src/app/{component}"] == feature_of[f"frontend/src/app/{service}"]

    for feature in features:
        suffixes = {Path(path_by_key[key]).suffix for key in feature.moduleKeys}
        assert not ({".java"} <= suffixes and {".ts"} <= suffixes), (
            f"{feature.title} mixes the backend and the frontend (edge case 'Unconnected halves')"
        )


def test_a_second_run_yields_identical_features(tmp_path):
    root, bundle, graph = _indexed(tmp_path)

    first = _features(root, bundle, graph)
    second = _features(root, bundle, graph)

    assert [(f.key, f.title, f.moduleKeys, f.exposedEntryPointCount) for f in first] == [
        (f.key, f.title, f.moduleKeys, f.exposedEntryPointCount) for f in second
    ]


def test_features_are_anchored_where_their_work_starts(tmp_path):
    """039 FR-010: a seed anchors its feature; a directory group keeps 033's rule."""
    root, bundle, graph = _indexed(tmp_path)
    path_by_key = _paths(root, bundle)

    features = _features(root, bundle, graph)
    anchor_of = {path_by_key[key]: path_by_key[feature.key] for feature in features for key in feature.moduleKeys}

    # Controller and service each hold one uncalled method: equal seeds, so the name decides.
    assert anchor_of[f"{JAVA}/dto/wallet/WalletDto.java"] == f"{JAVA}/web/WalletController.java"
    # `colors` and `palette` hold no entry point and are equally connected.
    assert anchor_of["frontend/src/app/theme/palette.ts"] == "frontend/src/app/theme/colors.ts"
    theme = next(f for f in features if path_by_key[f.key] == "frontend/src/app/theme/colors.ts")
    assert theme.title == "theme", "a group formed by directory keeps its directory title"
    wallet = next(f for f in features if path_by_key[f.key] == f"{JAVA}/web/WalletController.java")
    assert wallet.title == "web - WalletController", "a seeded group is titled after its anchor"


class _CountingPlanner:
    """A `FailoverExecutor`-shaped engine that counts calls and names two groups.

    The answer must parse, or it is never cached and every run would ask again
    whatever the grouping - which is not what this test is about.
    """

    def __init__(self) -> None:
        self.calls = 0

    def isAvailable(self) -> bool:
        return True

    def run(self, call):
        outer = self

        class _Inner:
            def generate(self, prompt):
                outer.calls += 1
                return json.dumps(
                    [
                        {"title": "Wallets", "description": "Wallets.", "kind": "capability", "memberCandidateIds": ["c0"]},
                        {"title": "Access", "description": "Access.", "kind": "subsystem", "memberCandidateIds": ["c1"]},
                    ]
                )

        class _Result:
            value = call(_Inner())

        return _Result()


def test_a_body_only_java_edit_keeps_the_grouping(tmp_path):
    """FR-019 and constitution 2.5: an ordinary edit stays incremental.

    With Java coupling live, an import edit can reshape the grouping and force a
    full pass. A change inside one method body must not: same candidates, same
    plan key, no planner call, and far fewer pages than a full run.
    """
    from doc_generator import DocGenerator, FeaturePlanner, open_doc_manifest_store
    from doc_generator.features.planner import plan_cache_key

    root = _write_sources(tmp_path)
    store, graph = _index(tmp_path, root, "run1.sqlite")
    engine = _CountingPlanner()
    manifest_store = open_doc_manifest_store(tmp_path / "manifest.sqlite")
    generator = DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=tmp_path / "docs",
        repositoryRoot=root,
        featurePlanner=FeaturePlanner(engine, cache=manifest_store),
    )
    first = generator.generateRepositoryDocumentation(root, incremental=False)
    assert engine.calls == 1

    def grouping(store_, graph_):
        bundle = store_.load_repository(root)
        evidence = build_repository_evidence(bundle, graph_, repository_root=root)
        adjacency = build_import_adjacency(bundle, graph_, repository_root=root)
        candidates = build_candidates(evidence, adjacency)
        return [set(candidate.memberKeys) for candidate in candidates], plan_cache_key(evidence, candidates)

    before = grouping(store, graph)

    service = root / JAVA / "service" / "WalletService.java"
    service.write_text(
        service.read_text(encoding="utf-8").replace("public void run() {}", "public void run() { int total = 1; }"),
        encoding="utf-8",
    )
    store2, graph2 = _index(tmp_path, root, "run2.sqlite")
    assert grouping(store2, graph2) == before, "a body-only edit must not regroup"

    generator.metadataStore, generator.dependencyGraph = store2, graph2
    second = generator.generateRepositoryDocumentation(root, incremental=True, changedPaths=[str(service)])

    assert engine.calls == 1, "an unchanged grouping reuses the cached plan: no model call"
    assert 0 < len(second.pages) < len(first.pages) / 2, (
        f"{len(second.pages)} of {len(first.pages)} pages regenerated: a full pass was forced"
    )
