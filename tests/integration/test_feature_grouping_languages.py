"""Spec 039 end to end: a Java backend and a TypeScript frontend grouped by their imports.

Before 039 neither language had coupling at all (spec Background): every group
of this repository would have been a lone seed, folded into whichever survivor
was largest. Run with no planner, exactly as the generator's `_ensure_features`
runs when no model is reachable, so what is asserted is the grouping itself.
"""

from __future__ import annotations

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
}


def _indexed(tmp_path: Path):
    root = tmp_path / "wealth"
    files = []
    for relative, text in SOURCES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        files.append(path)
    store, graph = index_repo(tmp_path, root, files, "wealth.sqlite")
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
