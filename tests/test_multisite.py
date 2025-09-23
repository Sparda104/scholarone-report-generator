import asyncio

import pytest

from fastapi import HTTPException

import src.app.main as app_main
import src.integrations.scholarone.proxy as proxy


def test_normalize_site_names_handles_commas():
    names = app_main._normalize_site_names(["ms, orgsci", "deca", "ms"])
    assert names == ["ms", "orgsci", "deca"]


def test_shape_basic_omits_site_when_not_provided():
    payload = {
        "Response": {
            "result": [
                {
                    "submissionId": "123",
                    "submissionTitle": "Title",
                    "submissionStatus": {
                        "documentStatusName": "status",
                        "decisionName": "decision",
                        "inDraftFlag": False,
                    },
                    "submissionDate": "2024-01-01",
                    "authorFullName": "Author",
                    "authorORCIDId": "0000-0000-0000-0000",
                    "documentId": 42,
                    "journalDigitalIssn": "1234-5678",
                    "journalPrintIssn": "9876-5432",
                }
            ]
        }
    }

    items = app_main._shape_basic(payload)

    assert len(items) == 1
    assert items[0].site is None


def test_resolve_sites_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("S1_SITE_NAME", "ms")
    assert app_main._resolve_sites(site_name=None) == ["ms"]


def test_resolve_sites_invalid_raises(monkeypatch):
    monkeypatch.delenv("S1_SITE_NAME", raising=False)
    with pytest.raises(HTTPException):
        app_main._resolve_sites(site_names=["notreal"])


def test_chunked_sites_limits_to_three():
    batches = list(app_main._chunked_sites(["a", "b", "c", "d", "e"], size=3))
    assert batches == [["a", "b", "c"], ["d", "e"]]


def test_call_endpoint_for_sites_batches(monkeypatch):
    calls = []

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    def fake_call(name, site, params, body=None):
        calls.append((site, params))
        return {"site": site}

    monkeypatch.setattr(app_main.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(app_main, "call_named_endpoint", fake_call)

    async def runner():
        return await app_main._call_endpoint_for_sites(
            "endpoint",
            ["ms", "orgsci", "deca", "isr"],
            {"foo": "bar"},
        )

    result = asyncio.run(runner())

    assert set(result.keys()) == {"ms", "orgsci", "deca", "isr"}
    assert len(calls) == 4
    for _, params in calls:
        assert params == {"foo": "bar"}


def test_split_date_range_batches(monkeypatch):
    monkeypatch.setenv("SCHOLARONE_DATE_RANGE_BATCH_DAYS", "3")
    params = {
        "from_time": "2024-01-01T00:00:00Z",
        "to_time": "2024-01-10T23:59:59Z",
        "site_name": "ms",
    }
    batches = proxy._split_date_range_batches(params)
    assert len(batches) == 4
    assert batches[0]["from_time"] == "2024-01-01T00:00:00Z"
    assert batches[-1]["to_time"] == "2024-01-10T23:59:59Z"


def test_merge_ids_by_date_responses_merges_results():
    batches = [
        (
            {"from_time": "2024-01-01T00:00:00Z", "to_time": "2024-01-03T23:59:59Z"},
            {"Response": {"Status": "SUCCESS", "Result": [{"id": 1}], "Count": 1}},
        ),
        (
            {"from_time": "2024-01-04T00:00:00Z", "to_time": "2024-01-06T23:59:59Z"},
            {"Response": {"Status": "SUCCESS", "Result": [{"id": 2}, {"id": 3}], "Count": 2}},
        ),
    ]

    merged = proxy._merge_ids_by_date_responses(batches)

    assert merged["Response"]["Count"] == 3
    assert len(merged["Response"]["Result"]) == 3
    assert merged["Meta"]["batch_count"] == 2
    assert len(merged["Meta"]["batches"]) == 2
