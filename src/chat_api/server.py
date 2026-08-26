from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from embedding_engine import DEFAULT_ENDPOINT_URL as DEFAULT_EMBEDDING_ENDPOINT_URL
from embedding_engine import DEFAULT_MODEL_NAME as DEFAULT_EMBEDDING_MODEL_NAME
from embedding_engine import create_embedding_engine
from local_llm import create_local_llm_engine
from local_llm.models import DEFAULT_ENDPOINT_URL as DEFAULT_LLM_ENDPOINT_URL
from provider_routing import FailoverExecutor, PathFailoverLog, ProviderRef
from repository_metadata.sqlite_store import connect as connect_metadata_db
from vector_index import VectorIndex

from .app import create_app


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local chat API server.")
    parser.add_argument("--repo", required=True, help="Path to the indexed repository root.")
    parser.add_argument(
        "--metadata-db",
        default=None,
        help="Path to the vector index SQLite file (defaults to <repo>/.codepedia/vector-metadata.sqlite).",
    )
    parser.add_argument(
        "--repository-metadata-db",
        default=None,
        help="Path to the repository-metadata SQLite file used for chat session persistence (025; distinct "
        "from --metadata-db, which is the vector index's own file) - defaults to "
        "<repo>/.codepedia/repository-metadata.sqlite.",
    )
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL_NAME)
    parser.add_argument("--embedding-endpoint", default=DEFAULT_EMBEDDING_ENDPOINT_URL)
    parser.add_argument("--llm-model", required=True, help="Local model name to use for answer generation.")
    parser.add_argument("--llm-endpoint", default=DEFAULT_LLM_ENDPOINT_URL)
    parser.add_argument(
        "--docs-root",
        required=True,
        help="Path to the doc_generator output directory to serve as the documentation wiki.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address. Defaults to 127.0.0.1 (local machine only); pass an explicit "
        "local/private address to allow access from elsewhere on the local network.",
    )
    parser.add_argument("--port", type=int, default=8000)
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_arg_parser().parse_args(argv)


def _startup_message(host: str, port: int) -> str:
    return f"Documentation wiki available at http://{host}:{port}/"


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    repo_root = Path(args.repo).expanduser().resolve()
    metadata_db = (
        Path(args.metadata_db) if args.metadata_db else repo_root / ".codepedia" / "vector-metadata.sqlite"
    )
    repository_metadata_db = (
        Path(args.repository_metadata_db)
        if args.repository_metadata_db
        else repo_root / ".codepedia" / "repository-metadata.sqlite"
    )

    # This standalone entrypoint builds single-provider chains, each wrapped
    # in a `FailoverExecutor` so `ChatSession`/`VectorIndex.search()` see the
    # same interface (`.stream()`/`.run()`/`.isAvailable()`) as every other
    # entrypoint (research.md §13's C4 fix) - wrapping is what a real chain
    # would also produce, just with exactly one entry.
    failover_log = PathFailoverLog(repository_metadata_db, connect_metadata_db)
    embedding_engine = FailoverExecutor(
        "embeddings",
        ((ProviderRef("local", args.embedding_model), create_embedding_engine(args.embedding_model, args.embedding_endpoint)),),
        failover_log=failover_log,
    )
    llm_engine = FailoverExecutor(
        "chat",
        ((ProviderRef("local", args.llm_model), create_local_llm_engine(args.llm_model, args.llm_endpoint)),),
        failover_log=failover_log,
    )
    vector_index = VectorIndex(repo_root, metadata_db, embedding_engine=embedding_engine)
    docs_root = Path(args.docs_root)

    app = create_app(vector_index, embedding_engine, llm_engine, docs_root, repository_metadata_db)
    print(_startup_message(args.host, args.port))
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
