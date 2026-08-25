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

# Remote-default chains (spec FR-002/FR-003, data-model.md `ProviderChain`).
# A fresh install, with zero configuration, already routes every stage to a
# named remote provider - full-local remains fully supported, but only via
# explicit configuration (`provider mode full-local`).
DEFAULT_EMBEDDING_CHAIN: tuple[str, ...] = (f"openai:{DEFAULT_OPENAI_MODEL_NAME}",)
DEFAULT_SUMMARY_CHAIN: tuple[str, ...] = ("groq:llama-3.3-70b-versatile",)
DEFAULT_CHAT_CHAIN: tuple[str, ...] = ("groq:llama-3.3-70b-versatile",)

# `provider mode full-local`'s result (spec FR-004) - all three chains
# collapse to a single local entry each.
FULL_LOCAL_EMBEDDING_CHAIN: tuple[str, ...] = ("local:nomic-embed-text",)
FULL_LOCAL_SUMMARY_CHAIN: tuple[str, ...] = (f"local:{DEFAULT_LLM_MODEL}",)
FULL_LOCAL_CHAT_CHAIN: tuple[str, ...] = (f"local:{DEFAULT_LLM_MODEL}",)

STAGES = ("embeddings", "summary", "chat")


@dataclass(frozen=True, slots=True)
class CLIConfiguration:
    llmModel: str = DEFAULT_LLM_MODEL
    llmEndpointUrl: str = DEFAULT_LLM_ENDPOINT_URL
    llmGenerateTimeout: float = DEFAULT_LLM_GENERATE_TIMEOUT
    embeddingModel: str = DEFAULT_OPENAI_MODEL_NAME
    embeddingEndpointUrl: str = DEFAULT_EMBEDDING_ENDPOINT_URL
    embeddingGenerateTimeout: float = DEFAULT_EMBEDDING_GENERATE_TIMEOUT
    embeddingChain: tuple[str, ...] = DEFAULT_EMBEDDING_CHAIN
    summaryChain: tuple[str, ...] = DEFAULT_SUMMARY_CHAIN
    chatChain: tuple[str, ...] = DEFAULT_CHAT_CHAIN
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
        disclosureAcknowledgedSignature=data.get(
            "disclosureAcknowledgedSignature", defaults.disclosureAcknowledgedSignature
        ),
    )


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
        disclosureAcknowledgedSignature=config.disclosureAcknowledgedSignature,
    )
    path = paths.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized.to_dict(), indent=2), encoding="utf-8")
