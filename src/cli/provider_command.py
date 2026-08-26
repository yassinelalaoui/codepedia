from __future__ import annotations

from typing import Sequence

import typer
from provider_routing import ProviderRef

from .config import (
    FULL_LOCAL_CHAT_CHAIN,
    FULL_LOCAL_EMBEDDING_CHAIN,
    FULL_LOCAL_SUMMARY_CHAIN,
    STAGES,
    CLIConfiguration,
    load_config,
    save_config,
)
from .disclosure import ensure_disclosure_acknowledged


def _validate_provider_refs(entries: Sequence[str]) -> tuple[str, ...]:
    if not entries:
        raise ValueError("At least one '<provider>:<model>' entry is required.")
    for entry in entries:
        ProviderRef.parse(entry)  # raises ValueError for an unparseable entry
    return tuple(entries)


def run_provider_chain_set(stage: str, providers: Sequence[str]) -> None:
    """`codepedia provider chain set <stage> <providerRef>...`
    (contracts/cli-provider-commands.md). Replaces exactly one stage's
    chain, then immediately re-runs the disclosure gate against the
    freshly-saved configuration (research.md §13's M1 fix) so what's shown
    names the chain that was just set, not stale defaults."""
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {STAGES!r}, got {stage!r}")
    validated = _validate_provider_refs(providers)

    current = load_config()
    if stage == "embeddings":
        updated = CLIConfiguration(**{**current.to_dict(), "embeddingChain": validated})
    elif stage == "summary":
        updated = CLIConfiguration(**{**current.to_dict(), "summaryChain": validated})
    else:
        updated = CLIConfiguration(**{**current.to_dict(), "chatChain": validated})
    save_config(updated)
    typer.echo("Configuration saved.")
    typer.echo(f"{stage} chain: {', '.join(validated)}")
    ensure_disclosure_acknowledged(load_config())


def run_provider_mode_full_local() -> None:
    """`codepedia provider mode full-local` (spec FR-004). Atomically sets
    all three chains to their local-only defaults in one `save_config` call
    (a single write, not three, so a crash mid-way can't leave only some
    chains switched), then immediately re-runs the disclosure gate against
    the freshly-saved, all-local configuration."""
    current = load_config()
    updated = CLIConfiguration(
        **{
            **current.to_dict(),
            "embeddingChain": FULL_LOCAL_EMBEDDING_CHAIN,
            "summaryChain": FULL_LOCAL_SUMMARY_CHAIN,
            "chatChain": FULL_LOCAL_CHAT_CHAIN,
        }
    )
    save_config(updated)
    typer.echo("Configuration saved. All three chains now use only local models.")
    typer.echo(f"embeddings chain: {', '.join(updated.embeddingChain)}")
    typer.echo(f"summary chain: {', '.join(updated.summaryChain)}")
    typer.echo(f"chat chain: {', '.join(updated.chatChain)}")
    ensure_disclosure_acknowledged(load_config())
