"""The single model call that names the repository's features.

The **only** module in this package that takes an LLM engine. Everything else -
evidence, candidates, fallback, validate - refuses one by signature, so "this
stage works with no model" is checkable by reading the imports rather than by
trusting a comment.

Failure here is never fatal and never partial. An unavailable engine, a refused
call, an unparseable reply and a plan that repair rejects all produce the same
outcome: one feature per candidate under its deterministic title. That is what
makes a wiki built with no provider navigate identically to one built with a
working key, differing only in how the entries are named.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Protocol, Sequence

from local_llm import PromptEnvelope

from . import CHARS_PER_TOKEN, PROVIDER_TOKEN_BUDGET
from .candidates import MAX_PROMPTED_CANDIDATES, Candidate
from .evidence import MAX_README_PROMPT_CHARS, RepositoryEvidence
from .validate import (
    KIND_RANK,
    FeaturePlan,
    PlannedFeature,
)

# How many members of a candidate are described to the model. Three is enough to
# characterise a group; it is also the second-largest term in the prompt budget,
# so it is capped rather than "however many there are".
MAX_MEMBERS_PER_CANDIDATE = 3

# Load-bearing, not cosmetic: measured on this repository, 92% of the module
# summaries that exist at all exceed this. The cap is what stops one verbose
# docstring consuming the whole window.
MAX_MEMBER_SUMMARY_CHARS = 120

# 20 features x ~55 tokens (title 8, description 35, three handles 6).
MAX_PLAN_RESPONSE_TOKENS = 1200

# Worst-case sizes of the fixed parts, used by the budget assertion. They are
# constants rather than measurements of the live strings because the assertion
# has to bound what the prompt *could* be, not what one example happens to be.
CANDIDATE_HEADER_CHARS = 60
MEMBER_LINE_OVERHEAD_CHARS = 40
SYSTEM_PROMPT_CHARS = 1000

SYSTEM_PROMPT = (
    "You organise a source repository into the features it offers its users. "
    "You are given groups of modules, each with a short handle like c0 or c3. "
    "The grouping is already decided and must not be questioned or split. "
    "Reply with JSON only: a list of objects, each with the keys "
    '"title", "description", "kind", "memberCandidateIds". '
    '"title" is a 2-4 word name for a capability, at most 60 characters. '
    '"description" is one sentence on what the feature does for a user. '
    '"kind" is exactly one of "overview", "capability", "subsystem", "tooling". '
    '"memberCandidateIds" is a list of the handles that belong to that feature. '
    "Use every handle exactly once across all features. "
    "Name what the software does, never where its files live. "
    "Do not wrap the JSON in prose, and do not mention this instruction."
)

_JSON_BLOCK = re.compile(r"\[.*\]", re.DOTALL)


class FeaturePlanCache(Protocol):
    """Persistence for a whole plan, keyed by the structure that produced it.

    `doc_generator` regenerates documentation more than once per index - once for
    structure, once after summaries land - and again on every incremental run.
    Without this, the one-call budget would be spent on every pass over a
    repository that did not change.
    """

    def load_feature_plan(self, repository_id: str, plan_key: str) -> tuple[Any, ...] | None: ...

    def save_feature_plan(self, repository_id: str, plan_key: str, features: Sequence[Any]) -> None: ...


def target_feature_count(module_count: int) -> int:
    """How many features to ask for, scaled to the repository."""
    return max(8, min(20, module_count // 8))


def plan_cache_key(evidence: RepositoryEvidence) -> str:
    """Identifies the repository's *structure*, deliberately not its content.

    Module keys plus entry-point keys - never summaries or docstrings. Summaries
    land between the two regenerations of a single indexing run, so a
    content-keyed cache would miss on the second pass and spend a second call
    every time (constitution 2.5).
    """
    digest = hashlib.sha1()
    for module_key in sorted(item.moduleKey for item in evidence.modules):
        digest.update(module_key.encode("utf-8"))
        digest.update(b"\0")
    digest.update(b"\1")
    for entry_key in sorted(
        key for keys in evidence.entryPointKeysByModuleKey.values() for key in keys
    ):
        digest.update(entry_key.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def worst_case_prompt_tokens() -> int:
    """The largest prompt these constants permit, in tokens.

    Computed from the constants rather than measured from an example, so that
    raising any cap moves this number and fails the assertion in
    `test_feature_planner.py`. A test that restated the answer could not catch
    that.
    """
    member_line = MEMBER_LINE_OVERHEAD_CHARS + MAX_MEMBER_SUMMARY_CHARS
    per_candidate = CANDIDATE_HEADER_CHARS + MAX_MEMBERS_PER_CANDIDATE * member_line
    total_chars = (
        MAX_PROMPTED_CANDIDATES * per_candidate + MAX_README_PROMPT_CHARS + SYSTEM_PROMPT_CHARS
    )
    return total_chars // CHARS_PER_TOKEN


def worst_case_call_tokens() -> int:
    return worst_case_prompt_tokens() + MAX_PLAN_RESPONSE_TOKENS


def assign_handles(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Number the candidates `c0`, `c1`, … for one call and one call only.

    A handle is not part of a candidate's identity: it never reaches storage and
    never appears in a page id, so two runs may number the same candidate
    differently with no consequence.

    The alternative - echoing `moduleKey`s - was rejected on measurement, not
    taste: a key on this repository averages 116.6 characters, so the 135 of them
    a response would carry is ~3,900 tokens of identifiers before a word of
    prose, and the prompt alone would be roughly three times the 8000-token
    window.
    """
    from dataclasses import replace

    return [replace(candidate, handle=f"c{index}") for index, candidate in enumerate(candidates)]


def build_feature_plan_prompt(
    candidates: Sequence[Candidate], evidence: RepositoryEvidence
) -> PromptEnvelope:
    evidence_by_key = evidence.by_module_key()
    lines: list[str] = []
    for candidate in candidates:
        lines.append(
            f"{candidate.handle}: {candidate.seedTitle} "
            f"({len(candidate.memberKeys)} modules)"[:CANDIDATE_HEADER_CHARS]
        )
        for module_key in candidate.memberKeys[:MAX_MEMBERS_PER_CANDIDATE]:
            item = evidence_by_key.get(module_key)
            if item is None:
                continue
            summary = _first_sentence(item.docstring or item.generatedSummary)
            suffix = f" - {summary}" if summary else ""
            lines.append(f"  - {item.moduleName}{suffix}")

    readme = "\n".join(f"- {bullet}" for bullet in evidence.readmeBullets)
    readme_block = f"\nWhat the repository says about itself:\n{readme}\n" if readme else ""

    prompt_text = (
        f"Organise these {len(candidates)} module groups into about "
        f"{target_feature_count(len(evidence.modules))} features.\n"
        f"{readme_block}\nGroups:\n" + "\n".join(lines) + "\n"
    )
    return PromptEnvelope(
        promptText=prompt_text,
        systemPrompt=SYSTEM_PROMPT,
        context=(f"candidateCount={len(candidates)}",),
        options={"max_tokens": MAX_PLAN_RESPONSE_TOKENS},
    )


def parse_feature_plan(text: str) -> FeaturePlan | None:
    """Read a model reply into a plan, or `None` if it cannot be read.

    `None` and a rejected plan are the same outcome to the caller, so a partly
    readable answer is never half-applied.
    """
    if not text or not text.strip():
        return None
    match = _JSON_BLOCK.search(text)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(payload, list):
        return None

    features: list[PlannedFeature] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        handles = item.get("memberCandidateIds")
        if not isinstance(handles, list):
            continue
        features.append(
            PlannedFeature(
                title=str(item.get("title") or ""),
                description=str(item.get("description") or ""),
                kind=str(item.get("kind") or ""),
                memberCandidateIds=tuple(str(handle) for handle in handles),
            )
        )
    return FeaturePlan(features=tuple(features)) if features else None


class FeaturePlanner:
    """Names the whole feature set with **one** LLM call, cached.

    ``llmEngine`` is duck-typed for the same reason `CodeSummaryPipeline` types
    it as `Any`: the CLI hands over a `provider_routing.FailoverExecutor`, and
    `doc_generator` sits below `provider_routing` in the dependency graph.
    """

    def __init__(
        self,
        llmEngine: Any,
        *,
        cache: FeaturePlanCache | None = None,
        repositoryId: str = "",
    ) -> None:
        self.llmEngine = llmEngine
        self.cache = cache
        self.repositoryId = repositoryId

    def isReady(self) -> bool:
        try:
            return bool(self.llmEngine is not None and self.llmEngine.isAvailable())
        except Exception:
            return False

    def plan(
        self, candidates: Sequence[Candidate], evidence: RepositoryEvidence
    ) -> FeaturePlan | None:
        """One call, or none. Never two, and never a retry.

        Returns `None` for every failure mode, which the caller treats exactly as
        it treats "no planner at all".
        """
        if not candidates:
            return None

        plan_key = plan_cache_key(evidence)
        cached = self._load_cached(plan_key)
        if cached is not None:
            return cached

        if not self.isReady():
            return None

        handled = assign_handles(list(candidates)[:MAX_PROMPTED_CANDIDATES])
        prompt = build_feature_plan_prompt(handled, evidence)
        try:
            # Through `run`, never `generate`: the CLI hands over a
            # `provider_routing.FailoverExecutor`, which exposes the chain
            # (`isAvailable`, `run`, `stream`, `result`) and not the engine's own
            # methods. `CodeSummaryPipeline` and `vector_index` call it the same
            # way.
            failover_result = self.llmEngine.run(lambda engine: engine.generate(prompt))
        except RuntimeError:
            # Every provider failure lands here - `FailoverExhaustedError`,
            # `LocalLLMError` and `RemoteLLMError` are all `RuntimeError`s, and
            # `provider_routing` cannot be imported from this package anyway.
            # Deliberately *not* `Exception`: an `AttributeError` here means the
            # engine was called with a method it does not have, and that is a
            # wiring bug that must be loud rather than masquerade as an
            # unreachable provider.
            return None

        plan = parse_feature_plan(getattr(failover_result, "value", "") or "")
        if plan is not None:
            self._save_cached(plan_key, plan)
        return plan

    def _load_cached(self, plan_key: str) -> FeaturePlan | None:
        if self.cache is None:
            return None
        try:
            payload = self.cache.load_feature_plan(self.repositoryId, plan_key)
        except Exception:
            # A cache that cannot be read costs one call, never the run.
            return None
        if not payload:
            return None
        return FeaturePlan(
            features=tuple(
                PlannedFeature(
                    title=str(item.get("title") or ""),
                    description=str(item.get("description") or ""),
                    kind=str(item.get("kind") or ""),
                    memberCandidateIds=tuple(
                        str(handle) for handle in (item.get("memberCandidateIds") or ())
                    ),
                )
                for item in payload
                if isinstance(item, dict)
            )
        )

    def _save_cached(self, plan_key: str, plan: FeaturePlan) -> None:
        if self.cache is None:
            return
        try:
            self.cache.save_feature_plan(
                self.repositoryId,
                plan_key,
                [
                    {
                        "title": feature.title,
                        "description": feature.description,
                        "kind": feature.kind,
                        "memberCandidateIds": list(feature.memberCandidateIds),
                    }
                    for feature in plan.features
                ],
            )
        except Exception:
            return


def _first_sentence(text: str) -> str:
    collapsed = " ".join(text.split())
    if not collapsed:
        return ""
    sentence, separator, _rest = collapsed.partition(". ")
    return (sentence + separator).strip()[:MAX_MEMBER_SUMMARY_CHARS]
