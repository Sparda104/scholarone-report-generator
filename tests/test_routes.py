import csv
import io

import pytest
from fastapi.testclient import TestClient

from src.app import main


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def sample_ids_by_date_raw():
    return {
        "Response": {
            "Status": "SUCCESS",
            "submission": [
                {
                    "documentId": 101,
                    "submissionId": "SUB-001",
                    "submissionTitle": "Sample Manuscript",
                    "submissionStatus": {
                        "documentStatusName": "Submitted",
                        "decisionName": "Accept",
                    },
                    "submissionDate": "2024-01-02T10:00:00Z",
                    "authorFullName": "Jane Author",
                    "journalDigitalIssn": "1234-5678",
                    "journalPrintIssn": "9876-5432",
                }
            ],
        }
    }


def test_ids_by_date_shapes_payload(client, monkeypatch, sample_ids_by_date_raw):
    captured = {}

    def fake_call(name, site, params, body=None):
        captured["name"] = name
        captured["site"] = site
        captured["params"] = params
        return sample_ids_by_date_raw

    monkeypatch.setattr(main, "call_named_endpoint", fake_call)

    response = client.get(
        "/v1/submissions/ids-by-date",
        params={
            "site_name": "ms",
            "from_time": "2024-01-01",
            "to_time": "2024-01-31",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert captured["name"] == "ids_by_date"
    assert captured["site"] == "ms"
    assert captured["params"]["from_time"] == "2024-01-01"
    assert captured["params"]["to_time"] == "2024-01-31"
    assert data["raw"] == sample_ids_by_date_raw
    assert data["items"][0]["submissionId"] == "SUB-001"
    assert data["items"][0]["authorFullName"] == "Jane Author"
    assert data["items"][0]["journalDigitalIssn"] == "1234-5678"
    assert data["items"][0]["journalPrintIssn"] == "9876-5432"


def test_ids_by_date_csv_export(client, monkeypatch, sample_ids_by_date_raw):
    monkeypatch.setattr(main, "call_named_endpoint", lambda *args, **kwargs: sample_ids_by_date_raw)
    response = client.get(
        "/v1/export/ids-by-date.csv",
        params={
            "site_name": "ms",
            "from_time": "2024-01-01",
            "to_time": "2024-01-31",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = response.text.strip().splitlines()
    assert rows[0] == "id,submissionId,title,status,decision,submissionDate,authorFullName,journalIssns"
    reader = csv.DictReader(io.StringIO(response.text))
    first = next(reader)
    assert first["id"] == "101"
    assert first["journalIssns"] == "1234-5678, 9876-5432"


@pytest.fixture
def sample_submission_full_raw():
    return {
        "Response": {
            "Status": "SUCCESS",
            "submission": [
                {
                    "documentId": 42,
                    "submissionId": "SUB-042",
                    "submissionTitle": "Deep Dive",
                    "submissionStatus": {
                        "documentStatusName": "Under Review",
                        "decisionName": "Pending",
                    },
                    "submissionDate": "2024-02-10T09:00:00Z",
                    "submissionType": "Article",
                    "abstractText": "Abstract text",
                    "submittingAuthor": {
                        "authorFullName": "Alex Editor",
                        "emailAddress": "alex@example.com",
                    },
                    "contributors": {
                        "authors": {
                            "author": [
                                {
                                    "fullName": "Alex Editor",
                                    "primaryEmail": "alex@example.com",
                                },
                                {
                                    "fullName": "Jamie CoAuthor",
                                    "primaryEmail": "jamie@example.com",
                                },
                            ]
                        }
                    },
                    "journal": {
                        "journalDigitalIssn": "2222-3333",
                        "journalPrintIssn": "4444-5555",
                    },
                }
            ],
        }
    }


def test_submission_full_by_submission_id(client, monkeypatch, sample_submission_full_raw):
    captured = {}

    def fake_call(name, site, params, body=None):
        captured["name"] = name
        captured["site"] = site
        captured["params"] = params
        return sample_submission_full_raw

    monkeypatch.setattr(main, "call_named_endpoint", fake_call)

    response = client.get(
        "/v1/submissions/full/by-submission-id",
        params={"site_name": "ms", "ids": "SUB-042"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert captured["name"] == "submission_full_by_submissionids"
    assert payload["items"][0]["submissionId"] == "SUB-042"
    assert payload["items"][0]["submissionType"] == "Article"
    assert payload["items"][0]["abstract"] == "Abstract text"
    assert payload["items"][0]["correspondingAuthor"] == "Alex Editor"
    assert payload["items"][0]["correspondingAuthorEmail"] == "alex@example.com"
    authors = payload["items"][0]["authors"]
    assert {author["fullName"] for author in authors} == {"Alex Editor", "Jamie CoAuthor"}


def test_submission_full_by_document_id(client, monkeypatch, sample_submission_full_raw):
    def fake_call(name, site, params, body=None):
        assert name == "submission_full_by_documentids"
        assert site == "ms"
        assert params["ids"] == "12345"
        return sample_submission_full_raw

    monkeypatch.setattr(main, "call_named_endpoint", fake_call)

    response = client.get(
        "/v1/submissions/full/by-document-id",
        params={"site_name": "ms", "ids": "12345"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["documentId"] == 42
    assert payload["items"][0]["journalDigitalIssn"] == "2222-3333"
    assert payload["raw"] == sample_submission_full_raw
