from __future__ import annotations

import typer

from .config import CLIConfiguration, disclosure_signature, save_config

_DISCLOSURE_HEADER = (
    "This tool is configured to use the following AI providers by default:"
)
_FULL_LOCAL_HINT = "Run `codepedia provider mode full-local` to use only local models instead."


def _format_chain(stage_label: str, chain: tuple[str, ...]) -> str:
    return f"  {stage_label}: {', '.join(chain)}"


def ensure_disclosure_acknowledged(config: CLIConfiguration) -> CLIConfiguration:
    """The one, centrally-enforced blocking disclosure gate (spec FR-012/FR-013,
    contracts/cli-provider-commands.md). Called both from `cli/main.py`'s
    Typer callback (before every chain-consuming subcommand) and, a second
    time, immediately after `provider chain set`/`provider mode full-local`
    save their own change - so the disclosure a user sees always names the
    configuration that's actually about to be used (research.md §13's M1 fix).

    Returns `config` unchanged when its current chains' signature already
    matches `disclosureAcknowledgedSignature`. Otherwise prints the current
    provider for each stage, requires explicit acknowledgment, persists the
    new signature, and returns the updated config. A decline aborts the
    command - nothing is written, no engine is called.
    """
    current_signature = disclosure_signature(config)
    if current_signature == config.disclosureAcknowledgedSignature:
        return config

    typer.echo(_DISCLOSURE_HEADER)
    typer.echo(_format_chain("Embeddings", config.embeddingChain))
    typer.echo(_format_chain("Summary", config.summaryChain))
    typer.echo(_format_chain("Chat", config.chatChain))
    typer.echo(
        "Using a remote provider sends repository content (code, summaries, and/or chat "
        "questions) to that provider's cloud API."
    )
    typer.echo(_FULL_LOCAL_HINT)
    typer.confirm("Continue with this configuration?", abort=True)

    updated = CLIConfiguration(
        llmModel=config.llmModel,
        llmEndpointUrl=config.llmEndpointUrl,
        llmGenerateTimeout=config.llmGenerateTimeout,
        embeddingModel=config.embeddingModel,
        embeddingEndpointUrl=config.embeddingEndpointUrl,
        embeddingGenerateTimeout=config.embeddingGenerateTimeout,
        embeddingChain=config.embeddingChain,
        summaryChain=config.summaryChain,
        chatChain=config.chatChain,
        disclosureAcknowledgedSignature=current_signature,
    )
    save_config(updated)
    return updated
