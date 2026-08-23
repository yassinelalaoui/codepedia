from __future__ import annotations

import os
from typing import Any, Callable, Optional

import typer
from embedding_engine import create_embedding_engine
from local_llm import create_groq_llm_engine, create_local_llm_engine
from local_llm.groq_transport import API_KEY_ENV_VAR

from .config import CLIConfiguration, load_config, save_config

_REMOTE_PROVIDER_DISCLOSURE = (
    "Warning: setting --llm-provider groq sends the text of chat questions and the "
    "cited code context in their answers to Groq's cloud API. Only enable this if "
    "you have explicitly decided that trade-off is acceptable for this repository."
)


def run_config(
    *,
    llm_model: Optional[str],
    llm_endpoint: Optional[str],
    llm_generate_timeout: Optional[float],
    embedding_model: Optional[str],
    embedding_endpoint: Optional[str],
    embedding_generate_timeout: Optional[float],
    llm_provider: Optional[str],
    remote_llm_model: Optional[str],
    show: bool,
) -> None:
    """View or change `CLIConfiguration` (research.md §5, data-model.md's
    "State flow: `config`"). Never fails solely because a selected model
    isn't installed yet (spec US3) — that's reported as a warning."""
    current = load_config()

    has_changes = not show and any(
        value is not None
        for value in (
            llm_model,
            llm_endpoint,
            llm_generate_timeout,
            embedding_model,
            embedding_endpoint,
            embedding_generate_timeout,
            llm_provider,
            remote_llm_model,
        )
    )
    if not has_changes:
        _print_status(current)
        return

    updated = CLIConfiguration(
        llmModel=llm_model if llm_model is not None else current.llmModel,
        llmEndpointUrl=llm_endpoint if llm_endpoint is not None else current.llmEndpointUrl,
        llmGenerateTimeout=llm_generate_timeout if llm_generate_timeout is not None else current.llmGenerateTimeout,
        embeddingModel=embedding_model if embedding_model is not None else current.embeddingModel,
        embeddingEndpointUrl=embedding_endpoint if embedding_endpoint is not None else current.embeddingEndpointUrl,
        embeddingGenerateTimeout=(
            embedding_generate_timeout if embedding_generate_timeout is not None else current.embeddingGenerateTimeout
        ),
        llmProvider=llm_provider if llm_provider is not None else current.llmProvider,
        remoteLlmModel=remote_llm_model if remote_llm_model is not None else current.remoteLlmModel,
    )
    # FR-013: disclosed every time a change actually sets the provider to
    # "groq" - before saving, and regardless of whether it was already groq.
    if llm_provider == "groq":
        typer.echo(_REMOTE_PROVIDER_DISCLOSURE)
    save_config(updated)  # raises ValueError before writing if invalid (e.g. missing remoteLlmModel for groq)
    typer.echo("Configuration saved.")

    if llm_model is not None:
        _warn_if_not_installed("LLM", updated.llmModel, updated.llmEndpointUrl, create_local_llm_engine)
    if embedding_model is not None:
        _warn_if_not_installed("embedding", updated.embeddingModel, updated.embeddingEndpointUrl, create_embedding_engine)

    _print_status(updated)


def _print_status(config: CLIConfiguration) -> None:
    llm_engine = create_local_llm_engine(
        config.llmModel, config.llmEndpointUrl, generate_timeout=config.llmGenerateTimeout
    )
    embedding_engine = create_embedding_engine(
        config.embeddingModel, config.embeddingEndpointUrl, embed_timeout=config.embeddingGenerateTimeout
    )

    llm_status = llm_engine.checkAvailability()
    embedding_status = embedding_engine.checkAvailability()

    typer.echo(
        f"LLM model: {config.llmModel} ({config.llmEndpointUrl}) - "
        f"{'available' if llm_status.available else 'unavailable'}: {llm_status.message}"
    )
    typer.echo(f"LLM generation timeout: {config.llmGenerateTimeout:g}s")
    typer.echo(
        f"Embedding model: {config.embeddingModel} ({config.embeddingEndpointUrl}) - "
        f"{'available' if embedding_status.available else 'unavailable'}: {embedding_status.message}"
    )
    typer.echo(f"Embedding generation timeout: {config.embeddingGenerateTimeout:g}s")

    _print_other_installed_models("LLM", llm_engine, config.llmModel)
    _print_other_installed_models("embedding", embedding_engine, config.embeddingModel)

    typer.echo(f"Chat answer-generation provider: {config.llmProvider}")
    if config.llmProvider == "groq":
        if config.remoteLlmModel:
            remote_engine = create_groq_llm_engine(config.remoteLlmModel)
            remote_status = remote_engine.checkAvailability()
            typer.echo(
                f"Remote (Groq) model: {config.remoteLlmModel} - "
                f"{'available' if remote_status.available else 'unavailable'}: {remote_status.message}"
            )
        else:
            typer.echo(f"Remote (Groq) model: not set - configure with --remote-llm-model")
        typer.echo(
            f"{API_KEY_ENV_VAR} is "
            f"{'set' if os.environ.get(API_KEY_ENV_VAR) else 'NOT set'} in this environment."
        )


def _print_other_installed_models(label: str, engine: Any, configured_model: str) -> None:
    try:
        installed = engine.listInstalledModels()
    except Exception:  # noqa: BLE001 - best-effort extra info, never fatal
        return
    others = [name for name in installed if name != configured_model]
    if others:
        typer.echo(f"Other installed {label} models at this endpoint: {', '.join(others)}")


def _warn_if_not_installed(label: str, model_name: str, endpoint_url: str, factory: Callable[[str, str], Any]) -> None:
    engine = factory(model_name, endpoint_url)
    status = engine.checkAvailability()
    # `AvailabilityStatus` (local_llm, 008) names this field `serviceReachable`;
    # `EmbeddingAvailabilityStatus` (embedding_engine, 009) names the same
    # concept `runtimeReachable` - read whichever this status has.
    reachable = getattr(status, "serviceReachable", None)
    if reachable is None:
        reachable = getattr(status, "runtimeReachable", False)
    if reachable and not status.modelInstalled:
        typer.echo(
            f"Warning: {label} model '{model_name}' is not currently installed at {endpoint_url}. "
            "Install it before it can be used."
        )
