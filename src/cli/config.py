from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from embedding_engine.models import DEFAULT_ENDPOINT_URL as DEFAULT_EMBEDDING_ENDPOINT_URL
from embedding_engine.models import DEFAULT_MODEL_NAME as DEFAULT_EMBEDDING_MODEL
from embedding_engine.models import normalize_endpoint_url as normalize_embedding_endpoint_url
from local_llm.models import DEFAULT_ENDPOINT_URL as DEFAULT_LLM_ENDPOINT_URL
from local_llm.models import DEFAULT_GENERATE_TIMEOUT as DEFAULT_LLM_GENERATE_TIMEOUT
from local_llm.models import normalize_endpoint_url as normalize_llm_endpoint_url

from . import paths

# A sensible, code-summarization-oriented default so `index`/`serve` work
# without requiring `config` to be run first (spec.md's "no configuration has
# ever been set" edge case). Overridden any time via `repo-scanner config`.
DEFAULT_LLM_MODEL = "qwen2.5-coder"


@dataclass(frozen=True, slots=True)
class CLIConfiguration:
    llmModel: str = DEFAULT_LLM_MODEL
    llmEndpointUrl: str = DEFAULT_LLM_ENDPOINT_URL
    llmGenerateTimeout: float = DEFAULT_LLM_GENERATE_TIMEOUT
    embeddingModel: str = DEFAULT_EMBEDDING_MODEL
    embeddingEndpointUrl: str = DEFAULT_EMBEDDING_ENDPOINT_URL

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


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
    )


def save_config(config: CLIConfiguration) -> None:
    # Raises ValueError before anything is written if either endpoint isn't a
    # valid local-only URL (008/009's own validation, reused rather than
    # re-implemented) or the generation timeout isn't a positive number.
    if config.llmGenerateTimeout <= 0:
        raise ValueError("llmGenerateTimeout must be a positive number of seconds")
    normalized = CLIConfiguration(
        llmModel=config.llmModel,
        llmEndpointUrl=normalize_llm_endpoint_url(config.llmEndpointUrl),
        llmGenerateTimeout=config.llmGenerateTimeout,
        embeddingModel=config.embeddingModel,
        embeddingEndpointUrl=normalize_embedding_endpoint_url(config.embeddingEndpointUrl),
    )
    path = paths.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized.to_dict(), indent=2), encoding="utf-8")
