"""Tool-call markup must never reach an artifact.

The fixture below is real: it was rendered under "Safety Analysis & Pre-Job
Instruction" on a work permit. DeepSeek-family models serialise tool calls with
their own special tokens, and when the provider fails to parse them back out
they arrive in message.content as literal text.
"""

from plantmind_core.llm import sanitize_text

# verbatim, fullwidth bars and all
LEAKED = (
    'Safety Analysis & Pre-Job Instruction\n'
    '<｜｜DSML｜｜tool_calls> <｜｜DSML｜｜invoke name="get_document"> '
    '<｜｜DSML｜｜parameter name="doc_id" string="true">0a7a35833a048a3b'
    '</｜｜DSML｜｜parameter> </｜｜DSML｜｜invoke> '
    '<｜｜DSML｜｜invoke name="get_document"> '
    '<｜｜DSML｜｜parameter name="doc_id" string="true">39ceb0e793720f2e'
    '</｜｜DSML｜｜parameter> </｜｜DSML｜｜invoke> </｜｜DSML｜｜tool_calls>'
)


def test_the_permit_leak_is_removed_entirely():
    out = sanitize_text(LEAKED)
    assert "DSML" not in out
    assert "invoke" not in out
    assert "get_document" not in out
    assert out == "Safety Analysis & Pre-Job Instruction"


def test_prose_on_both_sides_survives_and_stays_readable():
    out = sanitize_text(f"Isolate the pump.\n\n{LEAKED}\n\nThen lock out.")
    assert "Isolate the pump." in out
    assert "Then lock out." in out
    assert "DSML" not in out
    assert "\n\n\n" not in out          # no crater where the block was


def test_deepseek_native_tool_tokens_go_too():
    raw = "Check the strainer.<｜tool▁calls▁begin｜><｜tool▁sep｜>get_docs<｜tool▁calls▁end｜>"
    out = sanitize_text(raw)
    assert out == "Check the strainer."


def test_ascii_bar_variant_is_handled():
    assert sanitize_text("Done.<|endoftext|>") == "Done."


def test_ordinary_engineering_prose_is_untouched():
    """The patterns must not eat legitimate content - permits are full of
    comparisons, units and pipe characters in tables."""
    text = ("Verify P-101A suction > 0.8 barg (PI-102).\n\n"
            "| Step | Action |\n|---|---|\n| 1 | Isolate |\n\n"
            "If DP < 0.5 barg, stop. See SOP-U100-07 §4.2.")
    assert sanitize_text(text) == text


def test_empty_and_none_are_safe():
    assert sanitize_text("") == ""
    assert sanitize_text(None) == ""
