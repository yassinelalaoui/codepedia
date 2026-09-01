from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from embedding_engine.models import DEFAULT_EMBED_TIMEOUT as DEFAULT_EMBEDDING_GENERATE_TIMEOUT
from embedding_engine.models import DEFAULT_ENDPOINT_URL as DEFAULT_EMBEDDING_ENDPOINT_URL
from embedding_engine.openai_provider import DEFAULT_OPENAI_MODEL_NAME
from embedding_engine.models import normalize_endpoint_url as normalize_embedding_endpoint_url
from local_llm.models import DEFAULT_ENDPOINT_URL as DEFAULT_LLM_ENDPOINT_URL
from local_llm.models import DEFAULT_GENERATE_TIMEOUT as DEFAULT_LLM_GENERATE_TIMEOUT
from local_llm.models import normalize_endpoint_url as normalize_llm_endpoint_url
from provider_routing import ProviderRef

from . import paths

# A sensible, code-summarization-oriented default so `index`/`serve` work
# without requiring `config` to be run first (spec.md's "no configuration has
# ever been set" edge case). Used as the local model name whenever a
# `local:` chain entry is written (e.g. `provider mode full-local`).
DEFAULT_LLM_MODEL = "qwen2.5-coder"

# The local embedding model, paired with `DEFAULT_LLM_MODEL` above: the two
# names every `local:` chain entry defaults to. Both are Ollama model tags.
DEFAULT_LOCAL_EMBEDDING_MODEL = "nomic-embed-text"

# Local-first chains (spec FR-002/FR-003, data-model.md `ProviderChain`).
# Every stage tries the local Ollama runtime first and only reaches a remote
# provider when the local one is genuinely unavailable - not installed, not
# running, or failing. This is the privacy-preserving default: with Ollama up,
# no repository content leaves the machine, and the remote entry exists purely
# as a fallback so a machine without Ollama still works out of the box.
#
# The remote entries are second, not absent. Dropping them entirely is what
# `provider mode full-local` is for (FR-004) - that is a stronger guarantee
# than this default makes, because a chain with a remote entry can still fail
# over to it. Order alone is a preference, not a boundary.
#
# Groq retires/renames models from its catalog periodically (confirmed
# 2026-08-25: "llama-3.3-70b-versatile", this default's original choice, is
# no longer served - GET https://api.groq.com/openai/v1/models is the source
# of truth for what's currently available). "openai/gpt-oss-20b" is Groq's
# current general-purpose open-weight instruct model, a reasonable
# quality/latency default for per-symbol summarization and chat; switch to a
# larger model (e.g. "openai/gpt-oss-120b") via `provider chain set` for
# higher quality at the cost of latency.
DEFAULT_EMBEDDING_CHAIN: tuple[str, ...] = (
    f"local:{DEFAULT_LOCAL_EMBEDDING_MODEL}",
    f"openai:{DEFAULT_OPENAI_MODEL_NAME}",
)
DEFAULT_SUMMARY_CHAIN: tuple[str, ...] = (
    f"local:{DEFAULT_LLM_MODEL}",
    "groq:openai/gpt-oss-20b",
)
DEFAULT_CHAT_CHAIN: tuple[str, ...] = (
    f"local:{DEFAULT_LLM_MODEL}",
    "groq:openai/gpt-oss-20b",
)

# `provider mode full-local`'s result (spec FR-004) - all three chains
# collapse to a single local entry each, dropping the remote fallback that
# the defaults above keep.
FULL_LOCAL_EMBEDDING_CHAIN: tuple[str, ...] = (f"local:{DEFAULT_LOCAL_EMBEDDING_MODEL}",)
FULL_LOCAL_SUMMARY_CHAIN: tuple[str, ...] = (f"local:{DEFAULT_LLM_MODEL}",)
FULL_LOCAL_CHAT_CHAIN: tuple[str, ...] = (f"local:{DEFAULT_LLM_MODEL}",)

STAGES = ("embeddings", "summary", "chat")

# How many symbols/files each indexing stage has in flight at once. These
# numbers were chosen for the remote providers, where each call is almost pure
# network wait and the useful ceiling is the rate limit on one API key rather
# than local CPU - which is why the two differ. Summarization on Groq's free
# tier limits requests per minute tightly, and every 429 it earns is paid back
# as backoff (`provider_routing.BackoffPolicy`); OpenAI embeddings are far more
# permissive per key, so that stage can run wider.
#
# Now that both chains lead with `local:`, the first provider tried is a single
# Ollama process, where concurrency behaves differently: it is bounded by
# OLLAMA_NUM_PARALLEL and by the machine's own CPU/GPU, so requests past that
# bound queue rather than overlap. Leaving these values as they are is
# deliberate - queueing is harmless, and the numbers still apply unchanged the
# moment a stage falls back to its remote entry. Lower `summaryConcurrency`
# via `config` if a local run makes the machine unresponsive, and note that a
# tightly-quotaed remote key (a Groq free tier capped by tokens per minute, say)
# wants 1 here whatever the local path can take. What protects such a key at 4
# is no longer the guess it used to be: `provider_routing.BackoffPolicy` now
# waits for as long as the provider's own `Retry-After` header asks.
DEFAULT_SUMMARY_CONCURRENCY = 4
DEFAULT_EMBEDDING_CONCURRENCY = 8


@dataclass(frozen=True, slots=True)
class CLIConfiguration:
    llmModel: str = DEFAULT_LLM_MODEL
    llmEndpointUrl: str = DEFAULT_LLM_ENDPOINT_URL
    llmGenerateTimeout: float = DEFAULT_LLM_GENERATE_TIMEOUT
    embeddingModel: str = DEFAULT_LOCAL_EMBEDDING_MODEL
    embeddingEndpointUrl: str = DEFAULT_EMBEDDING_ENDPOINT_URL
    embeddingGenerateTimeout: float = DEFAULT_EMBEDDING_GENERATE_TIMEOUT
    embeddingChain: tuple[str, ...] = DEFAULT_EMBEDDING_CHAIN
    summaryChain: tuple[str, ...] = DEFAULT_SUMMARY_CHAIN
    chatChain: tuple[str, ...] = DEFAULT_CHAT_CHAIN
    summaryConcurrency: int = DEFAULT_SUMMARY_CONCURRENCY
    embeddingConcurrency: int = DEFAULT_EMBEDDING_CONCURRENCY
    disclosureAcknowledgedSignature: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def chain_for_stage(self, stage: str) -> tuple[str, ...]:
        if stage == "embeddings":
            return self.embeddingChain
        if stage == "summary":
            return self.summaryChain
        if stage == "chat":
            return self.chatChain
        raise ValueError(f"stage must be one of {STAGES!r}, got {stage!r}")


def disclosure_signature(config: CLIConfiguration) -> str:
    """A stable hash of the three chains as they currently stand
    (data-model.md `disclosureAcknowledgedSignature`, research.md §10) - any
    edit to any chain changes this signature, which alone is what makes
    FR-013's "re-show on any actual change, skip on unchanged re-runs"
    requirement correct."""
    payload = "|".join(
        [
            "embeddings=" + ",".join(config.embeddingChain),
            "summary=" + ",".join(config.summaryChain),
            "chat=" + ",".join(config.chatChain),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_config() -> CLIConfiguration:
    path = paths.config_path()
    if not path.exists():
        return CLIConfiguration()
    data = json.loads(path.read_text(encoding="utf-8"))
    defaults = CLIConfiguration()
    return CLIConfiguration(
        llmModel=data.get("llmModel", defaults.llmModel),
        llmEndpointUrl=data.get("llmEndpointUrl", defaults.llmEndpointUrl),
        llmGenerateTimeout=data.get("llmGenerateTimeout", defaults.llmGenerateTimeout),
        embeddingModel=data.get("embeddingModel", defaults.embeddingModel),
        embeddingEndpointUrl=data.get("embeddingEndpointUrl", defaults.embeddingEndpointUrl),
        embeddingGenerateTimeout=data.get("embeddingGenerateTimeout", defaults.embeddingGenerateTimeout),
        embeddingChain=tuple(data["embeddingChain"]) if "embeddingChain" in data else defaults.embeddingChain,
        summaryChain=tuple(data["summaryChain"]) if "summaryChain" in data else defaults.summaryChain,
        chatChain=tuple(data["chatChain"]) if "chatChain" in data else defaults.chatChain,
        summaryConcurrency=data.get("summaryConcurrency", defaults.summaryConcurrency),
        embeddingConcurrency=data.get("embeddingConcurrency", defaults.embeddingConcurrency),
        disclosureAcknowledgedSignature=data.get(
            "disclosureAcknowledgedSignature", defaults.disclosureAcknowledgedSignature
        ),
    )


def _validate_concurrency(field: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field} must be an integer of at least 1")


def _validate_chain(stage: str, entries: tuple[str, ...]) -> None:
    if not entries:
        raise ValueError(f"{stage}Chain must be a non-empty chain of '<provider>:<model>' entries")
    for entry in entries:
        ProviderRef.parse(entry)  # raises ValueError for an unparseable entry


def save_config(config: CLIConfiguration) -> None:
    # Raises ValueError before anything is written if either endpoint isn't a
    # valid local-only URL (008/009's own validation, reused rather than
    # re-implemented), the generation timeout isn't a positive number, or any
    # of the three chains is empty or contains an unparseable entry.
    if config.llmGenerateTimeout <= 0:
        raise ValueError("llmGenerateTimeout must be a positive number of seconds")
    if config.embeddingGenerateTimeout <= 0:
        raise ValueError("embeddingGenerateTimeout must be a positive number of seconds")
    _validate_chain("embedding", config.embeddingChain)
    _validate_chain("summary", config.summaryChain)
    _validate_chain("chat", config.chatChain)
    _validate_concurrency("summaryConcurrency", config.summaryConcurrency)
    _validate_concurrency("embeddingConcurrency", config.embeddingConcurrency)
    normalized = CLIConfiguration(
        llmModel=config.llmModel,
        llmEndpointUrl=normalize_llm_endpoint_url(config.llmEndpointUrl),
        llmGenerateTimeout=config.llmGenerateTimeout,
        embeddingModel=config.embeddingModel,
        embeddingEndpointUrl=normalize_embedding_endpoint_url(config.embeddingEndpointUrl),
        embeddingGenerateTimeout=config.embeddingGenerateTimeout,
        embeddingChain=tuple(config.embeddingChain),
        summaryChain=tuple(config.summaryChain),
        chatChain=tuple(config.chatChain),
        summaryConcurrency=int(config.summaryConcurrency),
        embeddingConcurrency=int(config.embeddingConcurrency),
        disclosureAcknowledgedSignature=config.disclosureAcknowledgedSignature,
    )
    path = paths.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized.to_dict(), indent=2), encoding="utf-8")
