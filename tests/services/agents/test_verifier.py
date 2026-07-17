from agents.verifier import check_grounding


def trace(*results):
    return [("some_tool", {}, r) for r in results]


def test_answer_grounded_in_tool_results():
    t = trace([{"tag": "P-101A", "count": 3, "causes": ["cavitation"]}])

    g = check_grounding(
        "P-101A has had 3 seal leaks; check it before restart.",
        t, given={"P-101B", "P-101"})

    assert g.verified is True
    assert g.ungrounded_tags == []


def test_invented_tag_flagged():
    t = trace([{"tag": "P-101A", "count": 3}])

    g = check_grounding(
        "Also inspect K-999 which shares the failure.",   # never in evidence
        t, given={"P-101B", "P-101"})

    assert g.verified is False
    assert g.ungrounded_tags == ["K-999"]


def test_given_tags_count_as_grounded():
    # the trigger's own tag is legitimate even with no tool results
    g = check_grounding("P-101B needs a suction check.", trace(),
                        given={"P-101B", "P-101"})
    assert g.verified is True


def test_tag_in_nested_tool_result_is_found():
    t = trace([{"siblings": [{"tag": "P-101A"}, {"tag": "P-101C"}]}])

    g = check_grounding("Compare against P-101A and P-101C.",
                        t, given={"P-101B"})
    assert g.verified is True


def test_answer_with_no_tags_is_trivially_grounded():
    g = check_grounding("Check the suction strainer and the gland flush.",
                        trace(), given=set())
    assert g.verified is True


def test_a_tag_read_off_a_filename_is_grounded():
    """The real one this missed. An underscore is a word character, so TAG_RE's
    \\b never fired inside 'incident_report_IR-2025-032.md': the answer side saw
    a tag, the evidence side saw nothing, and a document the agent genuinely
    read came back as an invention."""
    t = trace([{"document": "incident_report_IR-2025-032.md"}])

    g = check_grounding("Per incident report IR-2025-032, the seal failed.",
                        t, given={"P-101A"})

    assert g.verified is True
    assert g.ungrounded_tags == []


def test_splitting_separators_does_not_ground_an_invention():
    """The fix widens what counts as evidence, so this is the test that keeps
    it honest: a tag that is not in the evidence at all must still be caught."""
    t = trace([{"document": "incident_report_IR-2025-032.md"}])

    g = check_grounding("Per report IR-2025-032, also replace X-777.",
                        t, given={"P-101A"})

    assert g.verified is False
    assert g.ungrounded_tags == ["X-777"]


def test_tag_inside_a_snake_case_key_is_grounded():
    # same failure shape one level down: the tag hides inside an identifier
    t = trace([{"notes": "see wo_2201_P-101A_report for the strip-down"}])

    g = check_grounding("P-101A was stripped down.", t, given=set())
    assert g.verified is True
