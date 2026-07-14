import asyncio
from email.message import EmailMessage

from plantmind_core.schemas import EdgeType, NodeType
from extraction.mail.extractor import EmailExtractor
from extraction.text.extractor import TextExtractor
from extraction.text.relations import BatchFindings
from conftest import FakeEmbedder, FakeLLM


def build_eml():
    msg = EmailMessage()
    msg["From"] = "Ravi Sharma <ravi.sharma@plant.example>"
    msg["To"] = "ops-team@plant.example"
    msg["Subject"] = "P-101A seal issue after restart"
    msg["Date"] = "Mon, 13 Jul 2026 09:12:00 +0530"
    msg.set_content(
        "Team,\n\n"
        "P-101A is weeping at the gland again after this morning's restart. "
        "Suction pressure on PI-102 was 0.5 barg at start.\n\n"
        "Regards,\nRavi\n\n"
        "On Fri, 10 Jul 2026 someone wrote:\n"
        "> Historical note: K-301 also tripped last quarter.\n"
    )
    return bytes(msg)


def extract():
    text = TextExtractor(FakeLLM(*[BatchFindings()] * 3), FakeEmbedder())
    extractor = EmailExtractor(text)
    return asyncio.run(extractor.extract("doc-mail", "hash-mail",
                                         "seal_issue.eml", build_eml()))


def test_headers_land_on_document_node():
    csg = extract()

    doc = next(n for n in csg.nodes if n.type == NodeType.DOCUMENT)
    assert doc.props["subject"] == "P-101A seal issue after restart"
    assert "ravi.sharma@plant.example" in doc.props["from"]


def test_people_become_nodes_with_roles():
    csg = extract()

    people = {n.surface_form: n for n in csg.nodes if n.type == NodeType.PERSON}
    assert "Ravi Sharma" in people
    assert people["Ravi Sharma"].props["email"] == "ravi.sharma@plant.example"

    roles = {(e.src, e.props.get("role")) for e in csg.edges
             if e.type == EdgeType.MENTIONED_IN
             and e.src in people}
    assert ("Ravi Sharma", "from") in roles
    assert ("ops-team@plant.example", "to") in roles


def test_body_tags_extracted_but_quoted_history_dropped():
    csg = extract()

    surfaces = {n.surface_form for n in csg.nodes}
    assert "P-101A" in surfaces and "PI-102" in surfaces
    assert "K-301" not in surfaces        # lived only in the quoted reply


def test_subject_participates_in_text():
    csg = extract()

    chunks = [n for n in csg.nodes if n.type == NodeType.CHUNK]
    sections = [n for n in csg.nodes if n.type == NodeType.SECTION]
    all_text = " ".join(n.props["text"] for n in chunks + sections)
    assert "weeping at the gland" in all_text
