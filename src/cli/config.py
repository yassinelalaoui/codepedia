from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace

from embedding_engine.models import DEFAULT_EMBED_TIMEOUT as DEFAULT_EMBEDDING_GENERATE_TIMEOUT
from embedding_engine.models import DEFAULT_ENDPOINT_URL as DEFAULT_EMBEDDING_ENDPOINT_URL
from embedding_engine.models import normalize_endpoint_url as normalize_embedding_endpoint_url
from embedding_engine.models import normalize_model_name as normalize_embedding_model_name
from local_llm.models import DEFAULT_ENDPOINT_URL as DEFAULT_LLM_ENDPOINT_URL
from local_llm.models import DEFAULT_GENERATE_TIMEOUT as DEFAULT_LLM_GENERATE_TIMEOUT
from local_llm.models import normalize_endpoint_url as normalize_llm_endpoint_url
from local_llm.models import normalize_model_name as normalize_llm_model_name

from . import paths

# A sensible, code-summarization-oriented default so `index`/`serve` work
# without requiring `config` to be run first.
DEFAULT_LLM_MODEL = "qwen2.5-coder"

# The local embedding model, paired with `DEFAULT_LLM_MODEL` above. Both are
# Ollama model tags.
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"

# The stages that consume a model. Kept as a name the CLI and the availability
# check can share; there is one engine behind each of them.
STAGES = ("embeddings", "summary", "chat")

# How many symbols/files each indexing stage has in flight at once.
#
# These numbers were originally chosen for remote providers, where a call was
# almost pure network wait and the useful ceiling was the rate limit on one API
# key. The work is local now, but the pools still pay: measured on this
# machine (GTX 1650, 4 GB VRAM) with `nomic-embed-text`, eight concurrent
# embeddings took 6.8s against 51.4s one at a time - 6.42s/chunk down to
# 0.85s/chunk, a 7.6x speedup. Ollama genuinely overlaps requests up to
# OLLAMA_NUM_PARALLEL rather than merely queueing them.
#
# Lower `summaryConcurrency` if an index makes the machine unresponsive; raise
# either if the GPU sits idle while the queue is deep. Note that alternating
# between the summary and embedding models can force a model swap, which is why
# the pipeline drains one stage before starting the next.
DEFAULT_SUMMARY_CONCURRENCY = 4
DEFAULT_EMBEDDING_CONCURRENCY = 8


@dataclass(frozen=True, slots=True)
class CLIConfiguration:
    llmModel: str = DEFAULT_LLM_MODEL
    llmEndpointUrl: str = DEFAULT_LLM_ENDPOINT_URL
    llmGenerateTimeout: float = DEFAULT_LLM_GENERATE_TIMEOUT
    embeddingModel: str = DEFAULT_EMBEDDING_MODEL
    embeddingEndpointUrl: str = DEFAULT_EMBEDDING_ENDPOINT_URL
    embeddingGenerateTimeout: float = DEFAULT_EMBEDDING_GENERATE_TIMEOUT
    summaryConcurrency: int = DEFAULT_SUMMARY_CONCURRENCY
    embeddingConcurrency: int = DEFAULT_EMBEDDING_CONCURRENCY

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def model_for_stage(self, stage: str) -> str:
        """Which configured model serves one stage.

        Summary and chat share `llmModel`: they are the same engine asked
        different questions, and splitting them would let a repository be
        summarized by one model and discussed by another with no way to tell
        from a stored answer which had spoken.
        """
        if stage == "embeddings":
            return self.embeddingModel
        if stage in ("summary", "chat"):
            return self.llmModel
        raise ValueError(f"stage must be one of {STAGES!r}, got {stage!r}")


def load_config() -> CLIConfiguration:
    """Read the stored configuration, ignoring keys this version no longer has.

    Unknown keys are dropped rather than rejected. A file written before
    remote providers were removed still carries `embeddingChain`,
    `summaryChain`, `chatChain` and `disclosureAcknowledgedSignature`; none of
    them mean anything now, and refusing to start over their presence would
    strand every existing installation behind a manual edit. The next
    `save_config` writes the file back without them.
    """
    path = paths.config_path()
    if not path.exists():
        return CLIConfiguration()
    data = json.loads(path.read_text(encoding="utf-8"))
    defaults = CLIConfiguration()
    known = {field for field in defaults.to_dict()}
    return CLIConfiguration(**{key: value for key, value in data.items() if key in known})


def _validate_concurrency(field: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field} must be an integer of at least 1")


def save_config(config: CLIConfiguration) -> None:
    # Raises ValueError before anything is written if either endpoint isn't a
    # valid local-only URL (008/009's own validation, reused rather than
    # re-implemented), a model name is blank, the generation timeout isn't a
    # positive number, or either concurrency is below 1.
    if config.llmGenerateTimeout <= 0:
        raise ValueError("llmGenerateTimeout must be a positive number of seconds")
    if config.embeddingGenerateTimeout <= 0:
        raise ValueError("embeddingGenerateTimeout must be a positive number of seconds")
    _validate_concurrency("summaryConcurrency", config.summaryConcurrency)
    _validate_concurrency("embeddingConcurrency", config.embeddingConcurrency)
    # `replace` rather than a field-by-field rebuild: the rebuild silently
    # dropped whichever fields the writer forgot, which is how
    # `summaryConcurrency` and `embeddingConcurrency` used to reset themselves
    # to their defaults on every `config` edit and every disclosure prompt.
    normalized = replace(
        config,
        llmModel=normalize_llm_model_name(config.llmModel),
        llmEndpointUrl=normalize_llm_endpoint_url(config.llmEndpointUrl),
        embeddingModel=normalize_embedding_model_name(config.embeddingModel),
        embeddingEndpointUrl=normalize_embedding_endpoint_url(config.embeddingEndpointUrl),
        summaryConcurrency=int(config.summaryConcurrency),
        embeddingConcurrency=int(config.embeddingConcurrency),
    )
    path = paths.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized.to_dict(), indent=2), encoding="utf-8")
