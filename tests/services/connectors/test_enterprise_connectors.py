"""SharePoint against mocked HTTP. It can't be run against the real system
here, so the mocks mirror the documented response shapes and the tests pin the
contract the connector depends on.

This file used to cover SAP Plant Maintenance and the OSIsoft PI historian too.
Those connectors were removed in 9b8772d; the tests outlived them and failed at
import, which took the whole connectors suite down with them.
"""

import httpx

from connectors.sharepoint import SharePointConnector


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


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
