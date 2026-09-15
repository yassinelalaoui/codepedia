"""039 prototype: the spec's grouping rules, measured read-only on a real indexed state.

Usage: python grouping_proto.py <repo-root> [all|entry] [--verbose]
  all   = every non-test module with an entry point seeds (spec assumption)
  entry = only entry modules (command / route / main) seed

Nothing here is imported by src/. It re-implements the 039 rules on top of 033's
public pieces, to answer the plan's deferred question with numbers.
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path, PurePosixPath

from cli import paths
from dependency_graph import DependencyGraph
from doc_generator.entry_point_diagram import identify_entry_points
from doc_generator.features.evidence import build_repository_evidence
from doc_generator.features.fallback import build_fallback_groups, build_import_adjacency, lead_module_key
from doc_generator.overview.evidence import is_test_path
from doc_generator.prose import is_prose_file
from repository_metadata import RepositoryMetadataStore
from repository_metadata.sqlite_store import stable_repository_id

JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_FROM = re.compile(r"""(?:from\s+|import\s+|require\()\s*['"]([^'"]+)['"]""")
_JAVA = re.compile(r"^\s*import\s+(static\s+)?([\w.]+(?:\.\*)?)\s*;")
MIN_GROUP = 2


def rel(path: str, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        return Path(path).as_posix()


def resolve_imports(bundle, root: Path, python_adjacency):
    """Python from 033 unchanged; Java and JS/TS resolved from the parsed import lines."""
    rel_by_key = {fb.module.sourceFileId: rel(fb.module.filePath, root) for fb in bundle.files}
    key_by_rel = {v: k for k, v in rel_by_key.items()}
    lang = {fb.module.sourceFileId: fb.file.language for fb in bundle.files}
    java_by_suffix: dict[str, str] = {}
    java_by_package_dir: dict[str, list[str]] = defaultdict(list)
    for key, path in rel_by_key.items():
        if path.endswith(".java"):
            java_by_suffix[path[:-5]] = key
            java_by_package_dir[str(PurePosixPath(path).parent)].append(key)

    adjacency: dict[str, dict[str, Fraction]] = {k: {} for k in rel_by_key}
    for a, targets in python_adjacency.items():
        for b, w in targets.items():
            adjacency[a][b] = Fraction(w)

    def add(a: str, b: str, w: Fraction) -> None:
        if a == b:
            return
        adjacency[a][b] = adjacency[a].get(b, Fraction(0)) + w
        adjacency[b][a] = adjacency[b].get(a, Fraction(0)) + w

    stats = Counter()
    for fb in bundle.files:
        key = fb.module.sourceFileId
        language = lang[key]
        importer = rel_by_key[key]
        if language == "Java":
            for line in fb.module.imports:
                m = _JAVA.match(line)
                if not m:
                    continue
                name = m.group(2)
                if name.endswith(".*"):
                    parts = name[:-2].split(".")
                    members = next(
                        (java_by_package_dir[d] for d in java_by_package_dir if d.endswith("/".join(parts))), None
                    )
                    if members:
                        stats["java-wildcard"] += 1
                        for target in members:
                            add(key, target, Fraction(1, len(members)))
                    else:
                        stats["java-external"] += 1
                    continue
                parts = name.split(".")
                target = None
                for cut in range(len(parts), 0, -1):  # static imports and nested classes
                    suffix = "/".join(parts[:cut])
                    target = next((k for s, k in java_by_suffix.items() if s.endswith(suffix)), None) if cut >= 2 else None
                    if target:
                        break
                if target:
                    stats["java-direct"] += 1
                    add(key, target, Fraction(1))
                else:
                    stats["java-external"] += 1
        elif language in ("TypeScript", "JavaScript"):
            for line in fb.module.imports:
                m = _FROM.search(line)
                if not m or not m.group(1).startswith("."):
                    stats["js-package"] += 1
                    continue
                base = PurePosixPath(importer).parent / m.group(1)
                norm = str(PurePosixPath(*[p for p in _normalize(base.parts)]))
                cands = [norm] + [norm + e for e in JS_EXTENSIONS] + [f"{norm}/index{e}" for e in JS_EXTENSIONS]
                target = next((key_by_rel[c] for c in cands if c in key_by_rel), None)
                if target:
                    stats["js-relative"] += 1
                    add(key, target, Fraction(1))
                else:
                    stats["js-relative-unresolved"] += 1
    return adjacency, stats


def _normalize(parts):
    out: list[str] = []
    for p in parts:
        if p == "..":
            if out:
                out.pop()
        elif p not in (".", ""):
            out.append(p)
    return out


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    policy = sys.argv[2] if len(sys.argv) > 2 else "all"
    verbose = "--verbose" in sys.argv
    state = paths.repo_state_dir(root)
    bundle = RepositoryMetadataStore(paths.metadata_db_path(state)).load_repository(root)
    graph = DependencyGraph.load(paths.graph_db_path(state), graph_id=stable_repository_id(root))
    evidence = build_repository_evidence(bundle, graph, repository_root=root)
    by_key = evidence.by_module_key()
    relp = {k: rel(v.filePath, root) for k, v in by_key.items()}
    name = {k: v.moduleName for k, v in by_key.items()}
    directory = {k: v.directoryPath for k, v in by_key.items()}

    adjacency, stats = resolve_imports(bundle, root, build_import_adjacency(bundle, graph))
    is_test = {k: is_test_path(relp[k]) for k in by_key}
    production = {k for k in by_key if not is_test[k]}

    # Entry kinds per module (038's main rule included).
    kinds: dict[str, set[str]] = defaultdict(set)
    eps: dict[str, int] = Counter()
    for ep in identify_entry_points(bundle, graph):
        kind = "main" if ep.kind == "function" and ep.name == "main" else ep.kind
        kinds[ep.moduleKey].add(kind)
        eps[ep.moduleKey] += 1
    entry_module = {k for k in production if kinds.get(k, set()) & {"cli-command", "api-route", "main"}}
    seeds_all = sorted(k for k in production if eps.get(k))
    seeds = seeds_all if policy == "all" else sorted(entry_module)

    prod_adj = {k: {n: w for n, w in adjacency[k].items() if n in production} for k in production}

    # Seeded propagation over production modules only (033's rule, 2 sweeps).
    labels = {s: s for s in seeds}
    order = sorted(k for k in production if k not in labels)
    for _ in range(2):
        settled = dict(labels)
        changed = False
        for k in order:
            w = Counter()
            for n, weight in prod_adj[k].items():
                if n in settled:
                    w[settled[n]] += weight
            if w:
                best = min(w.items(), key=lambda it: (-it[1], it[0]))[0]
                if labels.get(k) != best:
                    labels[k], changed = best, True
        if not changed:
            break
    groups: dict[str, set[str]] = defaultdict(set)
    for k, s in labels.items():
        groups[s].add(k)
    unreached = [by_key[k] for k in sorted(production) if k not in labels]
    for g in build_fallback_groups(unreached, {k: {n: int(w * 1000) for n, w in v.items()} for k, v in prod_adj.items()}):
        groups[g.leadModuleKey] = set(g.memberKeys)

    def has_entry(members):
        return bool(members & entry_module)

    def coupling(a, b):
        return sum(prod_adj[x].get(y, 0) for x in a for y in b)

    def dir_share(members, d):
        return sum(1 for m in members if directory[m] == d)

    # Consolidate: small groups fold by coupling, then by own/ancestor directory; entry groups protected.
    changed = True
    while changed:
        changed = False
        for seed in sorted(groups, key=lambda s: (len(groups[s]), s)):
            members = groups[seed]
            if len(members) >= MIN_GROUP or seed not in groups:
                continue
            others = {s: m for s, m in groups.items() if s != seed and (len(m) >= MIN_GROUP or has_entry(m))}
            if has_entry(members):
                others = {s: m for s, m in others.items() if has_entry(m)}
            target = None
            scored = sorted(((coupling(members, m), s) for s, m in others.items()), key=lambda it: (-it[0], it[1]))
            if scored and scored[0][0] > 0:
                target = scored[0][1]
            else:
                d = directory[next(iter(members))]
                while target is None:
                    shares = sorted(((dir_share(m, d), s) for s, m in others.items()), key=lambda it: (-it[0], it[1]))
                    if shares and shares[0][0] > 0:
                        target = shares[0][1]
                    elif d == ".":
                        break
                    else:
                        d = str(PurePosixPath(d).parent) if "/" in d else "."
            if target is None:
                continue  # stays alone (entry module with nothing to join, or truly isolated)
            groups[target] |= members
            del groups[seed]
            changed = True
            break

    # Tests: join the feature holding most of the production code they import; else by directory.
    feature_of = {m: s for s, ms in groups.items() for m in ms}
    for t in sorted(k for k in by_key if is_test[k]):
        tally = Counter()
        for n, w in adjacency[t].items():
            if n in feature_of:
                tally[feature_of[n]] += w
        if tally:
            target = min(tally.items(), key=lambda it: (-it[1], it[0]))[0]
        else:
            d = directory[t]
            target = None
            while target is None:
                shares = sorted(((dir_share(m, d), s) for s, m in groups.items()), key=lambda it: (-it[0], it[1]))
                if shares and shares[0][0] > 0:
                    target = shares[0][1]
                elif d == ".":
                    target = max(groups, key=lambda s: (len(groups[s]), s))
                else:
                    d = str(PurePosixPath(d).parent) if "/" in d else "."
        groups[target].add(t)
        feature_of[t] = target

    def anchor(members):
        entries = [m for m in members if m in entry_module]
        if entries:
            return min(entries, key=lambda m: (-eps[m], name[m], m))
        seeded = [m for m in members if eps.get(m) and not is_test[m]]
        if seeded:
            return min(seeded, key=lambda m: (-eps[m], name[m], m))
        return lead_module_key(tuple(members), {k: {n: int(w * 1000) for n, w in v.items()} for k, v in adjacency.items()}, name)

    total = len(by_key)
    lang_linked = Counter()
    lang_total = Counter()
    for fb in bundle.files:
        lang_total[fb.file.language] += 1
        if adjacency[fb.module.sourceFileId]:
            lang_linked[fb.file.language] += 1
    print(f"== {root.name} [{policy}] modules={total} seeds={len(seeds)} (non-test with entry points: {len(seeds_all)}, entry modules: {len(entry_module)})")
    print("   import resolution:", dict(stats))
    print("   coupled/total by language:", {l: f"{lang_linked[l]}/{n}" for l, n in lang_total.items()})
    rows = sorted(groups.items(), key=lambda it: (-len(it[1]), it[0]))
    largest = len(rows[0][1])
    print(f"   groups={len(rows)} largest={largest} ({100 * largest / total:.0f}%) singletons={sum(1 for _, m in rows if len(m) == 1)}")
    for seed, members in rows:
        a = anchor(members)
        prod = [m for m in members if not is_test[m]]
        dirs = Counter(directory[m] for m in prod).most_common(2)
        print(f"   {len(members):3} anchor={relp[a]}  eps={sum(eps[m] for m in prod)}  entry={'Y' if has_entry(members) else '-'}  dirs={dirs}")
        if verbose:
            print("        " + ", ".join(sorted(relp[m] for m in members)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
