from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Sequence

from embedding_engine import create_embedding_engine
from embedding_engine.openai_provider import create_openai_embedding_provider
from local_llm import create_groq_llm_engine, create_local_llm_engine

from .chain import ProviderChain, ProviderRef
from .router import FailoverExecutor, FailoverLogWriter

if TYPE_CHECKING:  # pragma: no cover - import-cycle avoidance only
    from cli.config import CLIConfiguration


def _build_llm_engine(ref: ProviderRef, config: "CLIConfiguration") -> Any:
    if ref.kind == "local":
        return create_local_llm_engine(
            ref.model, config.llmEndpointUrl, generate_timeout=config.llmGenerateTimeout
        )
    if ref.kind == "groq":
        return create_groq_llm_engine(ref.model)
    raise ValueError(f"provider kind {ref.kind!r} cannot serve an LLM-backed stage")


def _build_embedding_provider(ref: ProviderRef, config: "CLIConfiguration") -> Any:
    if ref.kind == "local":
        return create_embedding_engine(
            ref.model, config.embeddingEndpointUrl, embed_timeout=config.embeddingGenerateTimeout
        )
    if ref.kind == "openai":
        return create_openai_embedding_provider(model_name=ref.model)
    raise ValueError(f"provider kind {ref.kind!r} cannot serve the embeddings stage")


def resolve_chain(chain: ProviderChain, config: "CLIConfiguration") -> tuple[tuple[ProviderRef, Any], ...]:
    """Resolve every entry in `chain` into a ready-to-call engine instance,
    in order. `chain.stage` selects which family of engine each `local:`
    entry resolves to - there is no separate local-LLM-for-chat vs.
    local-LLM-for-summary engine, both use the same local LLM machinery
    (data-model.md `ProviderRef`)."""
    builder = _build_embedding_provider if chain.stage == "embeddings" else _build_llm_engine
    return tuple((ref, builder(ref, config)) for ref in chain.providers)


def build_chain_from_strings(
    stage: str, entries: Sequence[str], config: "CLIConfiguration"
) -> tuple[tuple[ProviderRef, Any], ...]:
    chain = ProviderChain(stage=stage, providers=tuple(ProviderRef.parse(entry) for entry in entries))
    return resolve_chain(chain, config)


def _entries_for_stage(stage: str, config: "CLIConfiguration") -> Sequence[str]:
    if stage == "embeddings":
        return config.embeddingChain
    if stage == "summary":
        return config.summaryChain
    if stage == "chat":
        return config.chatChain
    raise ValueError(f"unknown stage {stage!r}")


def build_stage_executor(
    stage: str, config: "CLIConfiguration", *, failover_log: Optional[FailoverLogWriter] = None
) -> FailoverExecutor:
    """Build the fully-resolved `FailoverExecutor` for one stage, straight
    from `CLIConfiguration` - the one call site every CLI/API entrypoint
    uses to go from configuration to a ready-to-use engine chain."""
    resolved = build_chain_from_strings(stage, _entries_for_stage(stage, config), config)
    return FailoverExecutor(stage, resolved, failover_log=failover_log)
