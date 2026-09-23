from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Optional

import typer
from embedding_engine import create_embedding_engine
from local_llm import create_local_llm_engine

from .config import CLIConfiguration, load_config, save_config


def run_config(
    *,
    llm_model: Optional[str],
    llm_endpoint: Optional[str],
    llm_generate_timeout: Optional[float],
    embedding_model: Optional[str],
    embedding_endpoint: Optional[str],
    embedding_generate_timeout: Optional[float],
    show: bool,
) -> None:
    """View or change the local model settings.

    Never fails solely because a selected model isn't installed yet - that is
    reported as a warning, since `ollama pull` is the fix and refusing to
    store the name would make it impossible to configure ahead of the pull.
    """
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
        )
    )
    if not has_changes:
        _print_status(current)
        return

    # Built from `current` with `replace` rather than field by field: the
    # field-by-field rebuild this used to do silently dropped
    # `summaryConcurrency` and `embeddingConcurrency`, resetting them to their
    # defaults on every `config` edit.
    updates: dict[str, Any] = {}
    if llm_model is not None:
        updates["llmModel"] = llm_model
    if llm_endpoint is not None:
        updates["llmEndpointUrl"] = llm_endpoint
    if llm_generate_timeout is not None:
        updates["llmGenerateTimeout"] = llm_generate_timeout
    if embedding_model is not None:
        updates["embeddingModel"] = embedding_model
    if embedding_endpoint is not None:
        updates["embeddingEndpointUrl"] = embedding_endpoint
    if embedding_generate_timeout is not None:
        updates["embeddingGenerateTimeout"] = embedding_generate_timeout

    updated = replace(current, **updates)
    save_config(updated)  # raises ValueError before writing if invalid
    typer.echo("Configuration saved.")

    if llm_model is not None:
        _warn_if_not_installed("LLM", updated.llmModel, updated.llmEndpointUrl, create_local_llm_engine)
    if embedding_model is not None:
        _warn_if_not_installed("embedding", updated.embeddingModel, updated.embeddingEndpointUrl, create_embedding_engine)

    _print_status(updated)


def _print_status(config: CLIConfiguration) -> None:
    typer.echo(f"Local LLM: {config.llmModel} ({config.llmEndpointUrl})")
    typer.echo(f"LLM generation timeout: {config.llmGenerateTimeout:g}s")
    typer.echo(f"Local embedding model: {config.embeddingModel} ({config.embeddingEndpointUrl})")
    typer.echo(f"Embedding generation timeout: {config.embeddingGenerateTimeout:g}s")
    typer.echo(f"Summary concurrency: {config.summaryConcurrency}")
    typer.echo(f"Embedding concurrency: {config.embeddingConcurrency}")

    _print_availability("Summary/chat", config.llmModel, config.llmEndpointUrl, create_local_llm_engine)
    _print_availability("Embeddings", config.embeddingModel, config.embeddingEndpointUrl, create_embedding_engine)


def _print_availability(label: str, model_name: str, endpoint_url: str, factory: Callable[[str, str], Any]) -> None:
    try:
        engine = factory(model_name, endpoint_url)
        status = engine.checkAvailability()
    except Exception as exc:  # noqa: BLE001 - status display is best-effort, never fatal
        typer.echo(f"{label}: could not check availability ({exc})")
        return
    state = "available" if status.available else "unavailable"
    typer.echo(f"{label}: {state} - {status.message}")


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
            f"Run `ollama pull {model_name}` before it can be used."
        )
