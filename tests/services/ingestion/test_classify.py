from ingestion.classify import Classifier, DocKind, ROUTE_FOR
from plantmind_core.queues import Routes


def test_spreadsheets_are_tables():
    c = Classifier()
    assert c.classify("work_orders.csv", "wo_id,date,tag") == DocKind.TABLE
    assert c.classify("INSPECTIONS.XLSX", "") == DocKind.TABLE


def test_drawings_by_extension_and_name_hint():
    c = Classifier()
    assert c.classify("pnid_unit100.svg", "<svg") == DocKind.PNID
    assert c.classify("U100-PID-001_rev2.pdf", "") == DocKind.PNID
    assert c.classify("feed_section_dwg.pdf", "") == DocKind.PNID


def test_prose_documents_are_text():
    c = Classifier()
    assert c.classify("sop_pump_seal_replacement.md", "# SOP") == DocKind.TEXT
    assert c.classify("incident_report.docx", "") == DocKind.TEXT


def test_pdf_with_text_layer_is_text():
    c = Classifier()
    sniff = "Incident Report IR-2026-014 " * 10  # plenty of readable words
    assert c.classify("report.pdf", sniff) == DocKind.TEXT


def test_unmatched_defaults_to_text_without_fallback():
    c = Classifier()
    assert c.classify("mystery.bin", "\x00\x01") == DocKind.TEXT


def test_fallback_is_consulted_and_trusted():
    calls = []

    def fake_llm(filename, sniff):
        calls.append(filename)
        return "pnid"

    c = Classifier(llm_fallback=fake_llm)
    assert c.classify("scan_0042.pdf", "") == DocKind.PNID
    assert calls == ["scan_0042.pdf"]


def test_broken_fallback_still_lands_on_text():
    def broken(filename, sniff):
        raise TimeoutError("llm down")

    c = Classifier(llm_fallback=broken)
    assert c.classify("scan_0042.pdf", "") == DocKind.TEXT


def test_emails_by_extension_and_headers():
    c = Classifier()
    assert c.classify("thread.eml", "") == DocKind.EMAIL
    sniff = "Return-Path: <x@y.z>\nReceived: from mail\nSubject: pump issue"
    assert c.classify("exported_message", sniff) == DocKind.EMAIL


def test_images_route_to_image_lane_unless_drawing_named():
    c = Classifier()
    assert c.classify("nameplate_photo.jpg", "") == DocKind.IMAGE
    assert c.classify("trend.png", "") == DocKind.IMAGE
    assert c.classify("unit100_dwg.png", "") == DocKind.PNID   # hint wins


def test_long_text_pdf_is_manual_short_is_text():
    c = Classifier()
    sniff = "maintenance instructions for centrifugal pumps " * 8
    long_pdf = b"%PDF" + b"/Type /Page\n" * 40
    short_pdf = b"%PDF" + b"/Type /Page\n" * 3
    assert c.classify("ksb_manual.pdf", sniff, long_pdf) == DocKind.MANUAL
    assert c.classify("report.pdf", sniff, short_pdf) == DocKind.TEXT


def test_every_kind_has_a_route():
    assert set(ROUTE_FOR) == set(DocKind)
    assert ROUTE_FOR[DocKind.TABLE] is Routes.parse_workorder
    assert ROUTE_FOR[DocKind.MANUAL] is Routes.extract_manual
    assert ROUTE_FOR[DocKind.IMAGE] is Routes.extract_image
