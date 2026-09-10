"""`index` and `serve` hand the Overview narrator to the generator (038 T012).

Guards the failure 033's T060 recorded: a CLI construction site that is wrong
fails at runtime, not at import, so nothing but running the commands catches
it. The generator is wrapped rather than replaced - the commands still run end
to end on the in-memory engine doubles.
"""

from __future__ import annotations

import typer

import cli.index_command
import cli.serve_command
from cli.index_command import run_index
from cli.serve_command import run_serve
from doc_generator import DocGenerator, OverviewNarrator

from integration.test_cli import (  # noqa: F401 - imported for their fixture side effect
    _copy_fixture_repo,
    _local_config,
    cli_home,
    fake_engines,
)


def _capture(monkeypatch, module) -> dict[str, list]:
    records: dict[str, list] = {"init": [], "generate": []}

    class CapturingGenerator(DocGenerator):
        def __init__(self, **kwargs):
            records["init"].append(kwargs)
            super().__init__(**kwargs)

        def generateRepositoryDocumentation(self, repositoryRoot, **kwargs):
            records["generate"].append(kwargs.get("narrateOverview", True))
            return super().generateRepositoryDocumentation(repositoryRoot, **kwargs)

    monkeypatch.setattr(module, "DocGenerator", CapturingGenerator)
    return records


def test_index_wires_the_narrator_with_the_planners_engine_and_echo(tmp_path, cli_home, fake_engines, monkeypatch):
    records = _capture(monkeypatch, cli.index_command)
    root = _copy_fixture_repo(tmp_path)

    run_index(root, config=_local_config()).vectorIndex.close()

    kwargs = records["init"][0]
    assert isinstance(kwargs["overviewNarrator"], OverviewNarrator)
    assert kwargs["overviewNarrator"].llmEngine is kwargs["featurePlanner"].llmEngine
    assert kwargs["overviewNarrator"].cache is kwargs["manifestStore"]
    assert kwargs["onNotice"] is typer.echo


def test_index_structure_pass_passes_narrate_overview_false(tmp_path, cli_home, fake_engines, monkeypatch):
    records = _capture(monkeypatch, cli.index_command)
    root = _copy_fixture_repo(tmp_path)

    run_index(root, config=_local_config()).vectorIndex.close()

    assert records["generate"] == [False, True]


def test_serve_wires_the_narrator_with_the_summary_executor(tmp_path, cli_home, fake_engines, monkeypatch):
    root = _copy_fixture_repo(tmp_path)
    run_index(root, config=_local_config()).vectorIndex.close()
    records = _capture(monkeypatch, cli.serve_command)

    served = run_serve(root, config=_local_config())
    try:
        kwargs = records["init"][0]
        assert isinstance(kwargs["overviewNarrator"], OverviewNarrator)
        assert kwargs["overviewNarrator"].llmEngine is served.llmEngine
        assert kwargs["overviewNarrator"].cache is kwargs["manifestStore"]
        assert kwargs["onNotice"] is typer.echo
    finally:
        if served.watcher is not None:
            served.watcher.stop()
        served.vectorIndex.close()
