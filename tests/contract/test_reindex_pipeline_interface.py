import inspect

from reindex_pipeline import IncrementalReindexPipeline


def test_incremental_reindex_pipeline_exposes_run():
    assert callable(IncrementalReindexPipeline.run)


def test_incremental_reindex_pipeline_constructor_accepts_contract_parameters():
    parameters = inspect.signature(IncrementalReindexPipeline.__init__).parameters
    for name in (
        "repositoryRoot",
        "metadataStore",
        "dependencyGraph",
        "dependencyGraphPath",
        "summaryPipeline",
        "vectorIndex",
        "embeddingEngine",
        "docGenerator",
    ):
        assert name in parameters
