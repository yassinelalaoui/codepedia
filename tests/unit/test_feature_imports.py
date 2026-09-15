"""`features.imports`: Java and JS/TS import names resolved to repository modules.

No model anywhere - the module takes no engine. The fixture is indexed through
the same parser and dependency graph a real run uses, because the names this
module resolves are the graph's import nodes (039 research Decision 2), and a
hand-written graph could drift from what the parser actually records.
"""

from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "integration"))

from _doc_generator_support import index_repo  # noqa: E402

from doc_generator.features.imports import resolve_repository_imports  # noqa: E402

SOURCES = {
    "backend/com/acme/web/WalletController.java": (
        "package com.acme.web;\n\n"
        "import com.acme.service.WalletService;\n"
        "import com.acme.dto.*;\n"
        "import static com.acme.util.Money.round;\n"
        "import java.util.List;\n\n"
        "public class WalletController {\n"
        "    public List<String> list() { return null; }\n"
        "}\n"
    ),
    "backend/com/acme/service/WalletService.java": (
        "package com.acme.service;\n\n"
        "import com.acme.util.Money.Currency;\n\n"
        "public class WalletService {\n    public void pay() {}\n}\n"
    ),
    "backend/com/acme/dto/ADto.java": (
        "package com.acme.dto;\n\n"
        "public class ADto {\n    public BDto next() { return BDto.make(); }\n}\n"
    ),
    "backend/com/acme/dto/BDto.java": (
        "package com.acme.dto;\n\n"
        "public class BDto {\n    public static BDto make() { return new BDto(); }\n}\n"
    ),
    "backend/com/acme/dto/CDto.java": "package com.acme.dto;\n\npublic class CDto {\n}\n",
    "backend/com/acme/util/Money.java": (
        "package com.acme.util;\n\n"
        "import org.other.dto.ADto;\n\n"
        "public class Money {\n"
        "    public static long round(long v) { return v; }\n"
        "    public static class Currency {}\n"
        "}\n"
    ),
    "frontend/app/wallets.component.ts": (
        "import { Component } from '@angular/core';\n"
        "import { WalletService } from './wallet.service';\n"
        "import { legacy } from './legacy.js';\n"
        "import { shared } from '../shared';\n\n"
        "export class WalletsComponent {\n  show() { return shared + legacy; }\n}\n"
    ),
    "frontend/app/wallet.service.ts": (
        "import { shared } from '../shared/index';\n"
        "import { gone } from './missing';\n\n"
        "export class WalletService {\n  load() { return shared; }\n}\n"
    ),
    "frontend/app/legacy.js": "export const legacy = 1;\n",
    "frontend/shared/index.ts": "export const shared = 1;\n",
}


def _resolved(tmp_path: Path):
    root = tmp_path / "poly"
    files = []
    for relative, text in SOURCES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        files.append(path)
    store, graph = index_repo(tmp_path, root, files, "poly.sqlite")
    bundle = store.load_repository(root)
    key = {
        Path(file_bundle.module.filePath).resolve().relative_to(root.resolve()).as_posix(): file_bundle.module.sourceFileId
        for file_bundle in bundle.files
    }
    edges = resolve_repository_imports(bundle, graph, repository_root=root)
    return edges, key, (bundle, graph, root)


def _neighbors(edges, key, path) -> set[str]:
    by_key = {value: name for name, value in key.items()}
    return {by_key[neighbor] for neighbor in edges.get(key[path], {})}


CONTROLLER = "backend/com/acme/web/WalletController.java"
SERVICE = "backend/com/acme/service/WalletService.java"
MONEY = "backend/com/acme/util/Money.java"
DTOS = ("backend/com/acme/dto/ADto.java", "backend/com/acme/dto/BDto.java", "backend/com/acme/dto/CDto.java")
COMPONENT = "frontend/app/wallets.component.ts"
TS_SERVICE = "frontend/app/wallet.service.ts"
LEGACY = "frontend/app/legacy.js"
SHARED = "frontend/shared/index.ts"


def test_a_fully_qualified_java_import_couples_its_modules(tmp_path):
    edges, key, _ = _resolved(tmp_path)

    assert edges[key[CONTROLLER]][key[SERVICE]] == 1


def test_a_static_import_couples_to_its_class(tmp_path):
    """`import static com.acme.util.Money.round` names a method; its class is the module."""
    edges, key, _ = _resolved(tmp_path)

    assert edges[key[CONTROLLER]][key[MONEY]] == 1


def test_a_nested_class_import_couples_to_its_outer_class(tmp_path):
    edges, key, _ = _resolved(tmp_path)

    assert edges[key[SERVICE]][key[MONEY]] == 1


def test_a_wildcard_import_splits_one_import_across_the_package(tmp_path):
    """FR-003: one `import com.acme.dto.*` weighs, in total, what one direct import does."""
    edges, key, _ = _resolved(tmp_path)

    weights = [edges[key[CONTROLLER]][key[dto]] for dto in DTOS]
    assert weights == [Fraction(1, 3)] * 3
    assert sum(weights) == 1


def test_an_external_java_import_adds_nothing(tmp_path):
    """`java.util.List` names no repository module, so the controller gains no other neighbour."""
    edges, key, _ = _resolved(tmp_path)

    assert _neighbors(edges, key, CONTROLLER) == {SERVICE, MONEY, *DTOS}


def test_a_same_named_class_in_another_package_is_not_matched(tmp_path):
    """FR-002: `org.other.dto.ADto` is not `com/acme/dto/ADto`, however alike the tails."""
    edges, key, _ = _resolved(tmp_path)

    assert key[DTOS[0]] not in edges.get(key[MONEY], {})
    assert _neighbors(edges, key, MONEY) == {CONTROLLER, SERVICE}


def test_a_call_without_an_import_adds_no_coupling(tmp_path):
    """FR-004: `ADto` calls `BDto` in the same package, with no import between them."""
    edges, key, _ = _resolved(tmp_path)

    assert key[DTOS[1]] not in edges.get(key[DTOS[0]], {})


def test_a_relative_ts_import_resolves_with_or_without_extension(tmp_path):
    edges, key, _ = _resolved(tmp_path)

    assert edges[key[COMPONENT]][key[TS_SERVICE]] == 1, "`./wallet.service` resolves to `.ts`"
    assert edges[key[COMPONENT]][key[LEGACY]] == 1, "`./legacy.js` resolves as given"


def test_a_directory_import_resolves_to_its_index_file(tmp_path):
    edges, key, _ = _resolved(tmp_path)

    assert edges[key[COMPONENT]][key[SHARED]] == 1, "`../shared` is the directory's `index.ts`"
    assert edges[key[TS_SERVICE]][key[SHARED]] == 1, "`../shared/index` names it directly"


def test_a_package_import_adds_nothing(tmp_path):
    """`@angular/core` is a package, not a path: nothing in the repository."""
    edges, key, _ = _resolved(tmp_path)

    assert _neighbors(edges, key, COMPONENT) == {TS_SERVICE, LEGACY, SHARED}


def test_a_missing_relative_target_adds_nothing(tmp_path):
    edges, key, _ = _resolved(tmp_path)

    assert _neighbors(edges, key, TS_SERVICE) == {COMPONENT, SHARED}


def test_edges_are_symmetric_without_self_loops(tmp_path):
    edges, _key, _ = _resolved(tmp_path)

    assert edges
    for source, row in edges.items():
        for target, weight in row.items():
            assert source != target
            assert edges[target][source] == weight


def test_resolution_is_identical_across_runs(tmp_path):
    edges, _key, (bundle, graph, root) = _resolved(tmp_path)

    assert resolve_repository_imports(bundle, graph, repository_root=root) == edges
