"""SAP / PI / SharePoint against mocked HTTP. These can't be run against the
real systems here, so the mocks mirror the documented response shapes and the
tests pin the contract each connector depends on."""

import csv
import io

import httpx
import pytest

from connectors.pi import PiHistorianConnector
from connectors.sap import SapPmConnector
from connectors.sharepoint import SharePointConnector


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


# ------------------------------------------------------------------- SAP
SAP_V2 = {"d": {"results": [
    {"__metadata": {"uri": "x"}, "AUFNR": "4711", "EQUNR": "P-101A",
     "KTEXT": "Seal weeping at gland", "LastChangeDate": "2026-01-05",
     "Nav": {"deferred": {}}},
    {"__metadata": {"uri": "y"}, "AUFNR": "4712", "EQUNR": "K-301",
     "KTEXT": "High discharge temp trip", "LastChangeDate": "2026-02-01"},
]}}


def test_sap_pulls_odata_v2_and_emits_csv():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json=SAP_V2)

    conn = SapPmConnector("sap-pm", "https://sap.example/odata",
                          client=client_for(handler))
    items = list(conn.fetch("0"))

    assert len(items) == 1
    item = items[0]
    assert item.filename.endswith(".csv")

    rows = list(csv.DictReader(io.StringIO(item.data.decode())))
    assert [r["AUFNR"] for r in rows] == ["4711", "4712"]
    assert rows[0]["EQUNR"] == "P-101A"
    # SAP's own field names survive - the table lane maps them via the LLM
    assert "__metadata" not in rows[0] and "Nav" not in rows[0]


def test_sap_v4_shape_also_parses():
    def handler(request):
        return httpx.Response(200, json={"value": [{"AUFNR": "9001",
                                                    "EQUNR": "V-203"}]})

    items = list(SapPmConnector("s", "https://sap.example/odata",
                                client=client_for(handler)).fetch("0"))
    assert b"9001" in items[0].data


def test_sap_incremental_filter_uses_cursor():
    seen = {}

    def handler(request):
        seen["filter"] = request.url.params.get("$filter", "")
        return httpx.Response(200, json={"value": []})

    conn = SapPmConnector("s", "https://sap.example/odata",
                          changed_field="LastChangeDate", plant="1000",
                          client=client_for(handler))
    list(conn.fetch("20260115T090000"))

    assert "Plant eq '1000'" in seen["filter"]
    assert "LastChangeDate gt datetime'2026-01-15T09:00:00'" in seen["filter"]


def test_sap_empty_result_yields_nothing():
    handler = lambda r: httpx.Response(200, json={"value": []})
    assert list(SapPmConnector("s", "https://x/odata",
                               client=client_for(handler)).fetch("0")) == []


# -------------------------------------------------------------------- PI
def pi_handler(request):
    if "points" in request.url.path:
        return httpx.Response(200, json={"Items": [{"WebId": "W1"}]})
    return httpx.Response(200, json={"Items": [
        {"Timestamp": "2026-07-09T00:00:00Z", "Value": 126.8, "Good": True},
        {"Timestamp": "2026-07-12T00:00:00Z", "Value": 133.0, "Good": True},
        {"Timestamp": "2026-07-16T00:00:00Z", "Value": 141.6, "Good": True},
        {"Timestamp": "2026-07-16T01:00:00Z", "Value": {"Name": "Bad"},
         "Good": False},
    ]})


def test_pi_emits_trend_summary_naming_the_tag():
    conn = PiHistorianConnector("pi", "https://pi.example/piwebapi",
                                tags=["\\\\PISRV\\K-301.TI302"],
                                client=client_for(pi_handler))
    items = list(conn.fetch("0"))

    assert len(items) == 1
    text = items[0].data.decode()
    assert items[0].filename.endswith(".md")
    # the equipment tag must survive into the text so the mention pass links it
    assert "K-301" in text
    assert "rising" in text
    assert "126.80 to 141.60" in text
    assert "141.60" in text          # bad sample excluded, last good wins


def test_pi_skips_tag_that_errors_without_killing_the_sync():
    def handler(request):
        if "points" in request.url.path:
            if "BAD" in str(request.url):
                return httpx.Response(500)
            return httpx.Response(200, json={"Items": [{"WebId": "W1"}]})
        return pi_handler(request)

    conn = PiHistorianConnector("pi", "https://pi.example/piwebapi",
                                tags=["\\\\PISRV\\BAD.TAG",
                                      "\\\\PISRV\\K-301.TI302"],
                                client=client_for(handler))
    items = list(conn.fetch("0"))
    assert len(items) == 1 and "K-301" in items[0].data.decode()


# ------------------------------------------------------------ SharePoint
def sp_handler(request):
    if "oauth2" in str(request.url):
        return httpx.Response(200, json={"access_token": "tok"})
    if "children" in str(request.url):
        return httpx.Response(200, json={"value": [
            {"id": "1", "name": "old.pdf", "file": {},
             "lastModifiedDateTime": "2026-01-01T00:00:00Z",
             "@microsoft.graph.downloadUrl": "https://dl/old"},
            {"id": "2", "name": "sop_new.md", "file": {},
             "lastModifiedDateTime": "2026-07-01T00:00:00Z",
             "@microsoft.graph.downloadUrl": "https://dl/new"},
            {"id": "3", "name": "a-folder", "folder": {},
             "lastModifiedDateTime": "2026-07-02T00:00:00Z"},
        ]})
    return httpx.Response(200, content=b"file bytes")


def test_sharepoint_pulls_only_files_newer_than_cursor():
    conn = SharePointConnector("sp", "tenant", "client", "drive1",
                               folder="/Maintenance",
                               client=client_for(sp_handler))
    items = list(conn.fetch("2026-06-01T00:00:00Z"))

    assert [i.filename for i in items] == ["sop_new.md"]   # old.pdf skipped
    assert items[0].data == b"file bytes"
    assert items[0].marker == "2026-07-01T00:00:00Z"


def test_sharepoint_first_sync_takes_all_files_ascending():
    conn = SharePointConnector("sp", "t", "c", "d",
                               client=client_for(sp_handler))
    items = list(conn.fetch("0"))
    # folders excluded; ascending mtime so the last marker is the newest
    assert [i.filename for i in items] == ["old.pdf", "sop_new.md"]
