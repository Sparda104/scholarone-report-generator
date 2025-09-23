import logging

import pytest
import requests

from src.s1_client.client import ScholarOneAPI


class DummyResponse:
    status_code = 200
    content = b'{"Response": {"Status": "SUCCESS"}}'

    def json(self):
        return {"Response": {"Status": "SUCCESS"}}

    def raise_for_status(self):
        return None


def test_scholarone_client_logs(monkeypatch, caplog):
    monkeypatch.setenv("S1_USERNAME", "user")
    monkeypatch.setenv("S1_API_KEY", "key")
    monkeypatch.setenv("S1_BASE_URL", "https://example.org")

    def fake_get(self, url, params=None, timeout=None):
        return DummyResponse()

    monkeypatch.setattr(requests.Session, "get", fake_get)

    client = ScholarOneAPI()

    with caplog.at_level(logging.INFO):
        data = client._get("/path", {"site_name": "demo"})

    assert data == {"Response": {"Status": "SUCCESS"}}
    messages = [record.getMessage() for record in caplog.records]
    assert any("S1 request start" in message for message in messages)
    assert any("S1 request success" in message for message in messages)
