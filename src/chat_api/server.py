from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from embedding_engine import DEFAULT_ENDPOINT_URL as DEFAULT_EMBEDDING_ENDPOINT_URL
from embedding_engine import DEFAULT_MODEL_NAME as DEFAULT_EMBEDDING_MODEL_NAME
from embedding_engine import create_embedding_engine
from local_llm import create_local_llm_engine
from local_llm.models import DEFAULT_ENDPOINT_URL as DEFAULT_LLM_ENDPOINT_URL
from vector_index import VectorIndex

from .app import create_app


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local chat API server.")
    parser.add_argument("--repo", required=True, help="Path to the indexed repository root.")
    parser.add_argument(
        "--index-db",
        default=None,
        help="Path to the vector index SQLite file (defaults to <repo>/.repo-scanner/vector-index.sqlite).",
    )
    parser.add_argument(
        "--metadata-db",
        default=None,
        help="Path to the vector index metadata SQLite file (defaults to <repo>/.repo-scanner/vector-metadata.sqlite).",
    )
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL_NAME)
    parser.add_argument("--embedding-endpoint", default=DEFAULT_EMBEDDING_ENDPOINT_URL)
    parser.add_argument("--llm-model", required=True, help="Local model name to use for answer generation.")
    parser.add_argument("--llm-endpoint", default=DEFAULT_LLM_ENDPOINT_URL)
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


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    repo_root = Path(args.repo).expanduser().resolve()
    index_db = Path(args.index_db) if args.index_db else repo_root / ".repo-scanner" / "vector-index.sqlite"
    metadata_db = (
        Path(args.metadata_db) if args.metadata_db else repo_root / ".repo-scanner" / "vector-metadata.sqlite"
    )

    embedding_engine = create_embedding_engine(args.embedding_model, args.embedding_endpoint)
    vector_index = VectorIndex(repo_root, index_db, metadata_db, embedding_engine=embedding_engine)
    llm_engine = create_local_llm_engine(args.llm_model, args.llm_endpoint)

    app = create_app(vector_index, embedding_engine, llm_engine)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
