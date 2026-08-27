from __future__ import annotations

from doc_generator.section_narrator import (
    SectionNarrator,
    apply_section_narrations,
    build_section_narration_prompt,
    parse_section_narration,
)
from doc_generator.sections import Section, SectionMember, SectionSelection


def _section(key: str = "src/api", title: str = "api") -> Section:
    return Section(
        key=key,
        title=title,
        directoryPath=key,
        members=(
            SectionMember(moduleKey="m1", name="handlers", filePath="src/api/handlers.py", docstring="Handles requests."),
            SectionMember(moduleKey="m2", name="models", filePath="src/api/models.py"),
        ),
    )


class _RecordingEngine:
    def __init__(self, reply: str = "Title: Request Handling\nDescription: Accepts and routes inbound requests.", *, available: bool = True):
        self.reply = reply
        self.available = available
        self.calls: list[object] = []

    def isAvailable(self) -> bool:
        return self.available

    def generate(self, prompt):
        self.calls.append(prompt)
        return self.reply


class _MemoryCache:
    def __init__(self):
        self.rows: dict[tuple[str, str], tuple[str, str, str]] = {}

    def load_section_narration(self, repository_id, section_key, membership_hash):
        row = self.rows.get((repository_id, section_key))
        if row is None or row[0] != membership_hash:
            return None
        return row[1], row[2]

    def save_section_narration(self, repository_id, section_key, membership_hash, *, title, description):
        self.rows[(repository_id, section_key)] = (membership_hash, title, description)


def test_prompt_describes_the_group_and_never_asks_for_membership():
    envelope = build_section_narration_prompt(_section())

    assert "handlers" in envelope.promptText
    assert "models" in envelope.promptText
    assert "src/api" in envelope.promptText
    assert "sectionKey=src/api" in envelope.context
    # The model names a group it is given; it is never asked to form one.
    assert "already decided" in (envelope.systemPrompt or "")


def test_parses_a_well_formed_reply():
    narration = parse_section_narration(
        "Title: Request Handling\nDescription: Accepts and routes inbound requests.", section=_section()
    )

    assert narration is not None
    assert narration.title == "Request Handling"
    assert narration.description == "Accepts and routes inbound requests."


def test_rejects_a_reply_with_no_usable_title():
    assert parse_section_narration("This area handles requests.", section=_section()) is None
    assert parse_section_narration("", section=_section()) is None
    assert parse_section_narration("Title: " + "x" * 200, section=_section()) is None


def test_narration_replaces_only_title_and_description():
    section = _section()
    engine = _RecordingEngine()

    narrated = apply_section_narrations(
        SectionSelection(sections=(section,)), SectionNarrator(engine, repositoryId="repo")
    )

    result = narrated.sections[0]
    assert result.title == "Request Handling"
    assert result.description == "Accepts and routes inbound requests."
    assert result.isNarrated is True
    # Structure is untouched: same key, same members, same order.
    assert result.key == section.key
    assert result.members == section.members


def test_one_call_per_section_and_none_at_all_once_cached():
    section = _section()
    engine = _RecordingEngine()
    cache = _MemoryCache()

    first = SectionNarrator(engine, cache=cache, repositoryId="repo")
    apply_section_narrations(SectionSelection(sections=(section,)), first)
    assert len(engine.calls) == 1

    second = SectionNarrator(engine, cache=cache, repositoryId="repo")
    narrated = apply_section_narrations(SectionSelection(sections=(section,)), second)
    assert len(engine.calls) == 1, "an unchanged section must not be narrated again"
    assert narrated.sections[0].title == "Request Handling"


def test_changed_membership_invalidates_the_cached_narration():
    engine = _RecordingEngine()
    cache = _MemoryCache()
    narrator = SectionNarrator(engine, cache=cache, repositoryId="repo")

    section = _section()
    apply_section_narrations(SectionSelection(sections=(section,)), narrator)

    from dataclasses import replace

    grown = replace(
        section,
        members=section.members + (SectionMember(moduleKey="m3", name="routes", filePath="src/api/routes.py"),),
    )
    apply_section_narrations(SectionSelection(sections=(grown,)), narrator)

    assert len(engine.calls) == 2


def test_an_unavailable_engine_leaves_the_deterministic_title_in_place():
    section = _section()
    engine = _RecordingEngine(available=False)

    narrated = apply_section_narrations(SectionSelection(sections=(section,)), SectionNarrator(engine))

    assert engine.calls == []
    assert narrated.sections[0].title == "api"
    assert narrated.sections[0].isNarrated is False


def test_a_failing_engine_degrades_the_page_not_the_run():
    class _Failing(_RecordingEngine):
        def generate(self, prompt):
            raise RuntimeError("provider chain exhausted")

    narrated = apply_section_narrations(
        SectionSelection(sections=(_section(),)), SectionNarrator(_Failing())
    )

    assert narrated.sections[0].title == "api"
    assert narrated.sections[0].isNarrated is False


def test_no_narrator_returns_the_selection_untouched():
    selection = SectionSelection(sections=(_section(),))

    assert apply_section_narrations(selection, None) is selection
