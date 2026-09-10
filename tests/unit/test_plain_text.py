"""`plain_text.excerpt`: Markdown in, one readable line out.

The module list on the Overview used to print a README's leading text raw -
heading hash, emphasis asterisks, escaped punctuation - and cut it off wherever
the character budget ran out. These pin what a reader sees instead.
"""

from __future__ import annotations

from doc_generator.plain_text import MAX_MODULE_DESCRIPTION_CHARS, excerpt, first_sentence, to_plain

# The README row as it appeared on a real Overview (research Decision 12).
NEXTGEN_README = (
    "# NexGen Wealth Ledger\n\n"
    "Welcome to the **NexGen Wealth Ledger** repository!\n\n"
    "NexGen Wealth Ledger is a modern, high-performance wealth management platform "
    "built specifically for enterprise fintechs, investment firms, and digital asset "
    "custodians. We prioritize security, robust auditing, and a streamlined user "
    "experience to manage client portfolios, active wallets, and immutable ledger entries.\n\n"
    "---\n"
)


def test_leading_atx_heading_is_stripped():
    assert to_plain("# Title\n\nBody text.") == "Body text."
    assert to_plain("### Deep title\nBody.") == "Body."


def test_emphasis_code_and_html_markers_are_removed():
    assert to_plain("Uses **bold**, *italic*, __strong__ and `code`.") == "Uses bold, italic, strong and code."
    assert to_plain("A <b>tag</b> and <br/> break.") == "A tag and break."


def test_an_unpaired_backtick_is_dropped():
    assert to_plain("src/pkg/domain` — plain value objects") == "src/pkg/domain — plain value objects"


def test_snake_case_underscores_survive():
    assert to_plain("Calls `build_index` via build_index_now.") == "Calls build_index via build_index_now."


def test_links_reduce_to_their_text():
    assert to_plain("See [the guide](docs/guide.md) and ![logo](logo.png).") == "See the guide and."


def test_whitespace_collapses():
    assert to_plain("One\n\n  two\tthree  ") == "One two three"


def test_cut_at_last_sentence_boundary_within_cap():
    text = "First sentence here. Second sentence is longer than the rest of it. Third."
    assert excerpt(text, max_chars=50) == "First sentence here."


def test_cut_at_word_boundary_with_ellipsis_when_no_sentence_fits():
    text = "A single very long sentence that keeps going without any stop at all for a while"
    result = excerpt(text, max_chars=30)
    assert result.endswith("…")
    assert len(result) <= 30
    assert result == "A single very long sentence…"


def test_never_cuts_mid_word():
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda"
    for cap in range(8, len(text)):
        result = excerpt(text, max_chars=cap)
        stem = result.rstrip("…")
        assert text.startswith(stem)
        assert len(stem) == len(text) or text[len(stem)] == " "


def test_short_text_is_returned_whole():
    assert excerpt("Fits.", max_chars=MAX_MODULE_DESCRIPTION_CHARS) == "Fits."


def test_empty_and_heading_only_input_yield_empty():
    assert excerpt("") == ""
    assert excerpt("# Only a heading\n") == ""
    assert excerpt("---\n") == ""


def test_the_nextgen_readme_row_becomes_plain_text():
    result = excerpt(NEXTGEN_README)
    assert result == "Welcome to the NexGen Wealth Ledger repository!"
    for marker in ("#", "*", "\\", "---"):
        assert marker not in result


def test_first_sentence_takes_one_sentence_and_caps_it():
    assert first_sentence("Builds the index. Then serves it.", max_chars=120) == "Builds the index."
    long = "word " * 60
    assert len(first_sentence(long, max_chars=40)) <= 40
