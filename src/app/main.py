import asyncio
import os
from typing import Any, Dict, Iterable, Optional

from fastapi import Body, HTTPException, FastAPI, Query, Request
from pydantic import BaseModel

from src.core.constants import ALLOWED_SITES
from src.integrations.scholarone.proxy import call_named_endpoint
from src.integrations.scholarone.endpoints import ENDPOINTS

app = FastAPI(title="ScholarOne API Wrapper")

@app.get("/health")
def health():
    return {"ok": True, "sites": ALLOWED_SITES}

class SubmissionBasic(BaseModel):
    submissionId: str | None = None
    title: str | None = None
    status: str | None = None
    decision: str | None = None
    inDraft: bool | None = None
    submissionDate: str | None = None
    author: str | None = None
    authorORCID: str | None = None
    documentId: int | None = None
    journalDigitalIssn: str | None = None
    journalPrintIssn: str | None = None
    site: str | None = None

class BasicSubmissionsResponse(BaseModel):
    items: list[SubmissionBasic] | None = None
    raw: dict

def _resolve_site(site_name: str | None) -> str:
    site = site_name or os.getenv("S1_SITE_NAME") or ""
    if not site:
        raise HTTPException(400, "site_name not provided and S1_SITE_NAME not set")
    if site not in ALLOWED_SITES:
        raise HTTPException(400, f"Invalid site_name '{site}'. Must be one of: {', '.join(ALLOWED_SITES)}")
    return site

def _normalize_site_names(site_names: Optional[Iterable[str]]) -> list[str]:
    if not site_names:
        return []
    normalized: list[str] = []
    for entry in site_names:
        if not entry:
            continue
        parts = [p.strip() for p in str(entry).split(",") if p.strip()]
        for part in parts:
            if part not in normalized:
                normalized.append(part)
    return normalized

def _resolve_sites(site_name: Optional[str] = None, site_names: Optional[Iterable[str]] = None) -> list[str]:
    normalized = _normalize_site_names(site_names)
    if normalized:
        invalid = [s for s in normalized if s not in ALLOWED_SITES]
        if invalid:
            raise HTTPException(400, f"Invalid site_name(s) {', '.join(invalid)}. Must be one of: {', '.join(ALLOWED_SITES)}")
        return normalized
    return [_resolve_site(site_name)]

def _shape_basic(data: dict, site: str | None = None) -> list[SubmissionBasic]:
    r = data.get("Response", {})
    result = r.get("result")
    results = result if isinstance(result, list) else [result] if result else []
    items: list[SubmissionBasic] = []
    for x in results:
        if not isinstance(x, dict):
            continue
        s = SubmissionBasic(
            submissionId=x.get("submissionId"),
            title=x.get("submissionTitle"),
            status=(x.get("submissionStatus") or {}).get("documentStatusName"),
            decision=(x.get("submissionStatus") or {}).get("decisionName"),
            inDraft=bool((x.get("submissionStatus") or {}).get("inDraftFlag")) if x.get("submissionStatus") else None,
            submissionDate=x.get("submissionDate"),
            author=x.get("authorFullName"),
            authorORCID=x.get("authorORCIDId"),
            documentId=x.get("documentId"),
            journalDigitalIssn=x.get("journalDigitalIssn"),
            journalPrintIssn=x.get("journalPrintIssn"),
            site=site,
        )
        items.append(s)
    return items

def _chunked_sites(sites: Iterable[str], size: int = 3) -> Iterable[list[str]]:
    sites_list = list(sites)
    for i in range(0, len(sites_list), size):
        yield sites_list[i:i + size]

async def _call_endpoint_for_sites(
    name: str,
    sites: list[str],
    params: Dict[str, Any],
    body: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not sites:
        raise HTTPException(400, "No site names provided")

    results: Dict[str, Any] = {}
    body_payload = body if body is not None else None

    async def _call_single(site: str) -> Any:
        return await asyncio.to_thread(
            call_named_endpoint,
            name,
            site,
            dict(params),
            body_payload,
        )

    if len(sites) == 1:
        site = sites[0]
        try:
            results[site] = await _call_single(site)
        except HTTPException as exc:
            raise HTTPException(exc.status_code, f"Site '{site}': {exc.detail}", headers=exc.headers) from exc
        return results

    for batch in _chunked_sites(sites, size=3):
        tasks = [
            asyncio.create_task(_call_single(site))
            for site in batch
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        for site, response in zip(batch, responses):
            if isinstance(response, HTTPException):
                raise HTTPException(response.status_code, f"Site '{site}': {response.detail}", headers=response.headers)
            if isinstance(response, Exception):
                raise HTTPException(500, f"Site '{site}' request failed: {response}")
            results[site] = response
    return results

@app.get("/v1/submissions/basic", response_model=BasicSubmissionsResponse)
async def submissions_basic(
    ids: str = Query(..., description="Comma-separated Submission IDs"),
    site_name: str | None = None,
    site_names: list[str] | None = Query(None, description="Select one or more site names"),
):
    try:
        sites = _resolve_sites(site_name, site_names)
        id_list = [x.strip() for x in ids.split(",") if x.strip()]
        if not id_list:
            raise HTTPException(400, "No valid IDs provided")
        params = {"ids": ",".join(id_list)}
        data_by_site = await _call_endpoint_for_sites("submissions_basic_by_ids", sites, params)
        items: list[SubmissionBasic] = []
        multiple_sites = len(sites) > 1
        for site in sites:
            site_data = data_by_site.get(site)
            if site_data:
                items.extend(_shape_basic(site_data, site=site if multiple_sites else None))
        raw_response: Dict[str, Any] = (
            data_by_site if len(sites) > 1 else next(iter(data_by_site.values()))
        )
        return {"items": items, "raw": raw_response}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Server error: {e}")

class ProxyResponse(BaseModel):
    raw: dict

@app.get("/v1/endpoints")
def list_endpoints():
    return {"count": len(ENDPOINTS), "endpoints": list(ENDPOINTS.keys())}

# Option A: expose common params on generic routes so Swagger shows fields
@app.get("/v1/s1/{name}", response_model=ProxyResponse)
async def s1_named_get(
    name: str,
    request: Request,
    site_name: Optional[str] = None,
    site_names: Optional[list[str]] = Query(None, description="Select one or more site names"),
    # Common params
    ids: Optional[str] = Query(None, description="Comma-separated IDs (no quotes needed)"),
    primary_email: Optional[str] = Query(None, description="Person email"),
    from_time: Optional[str] = Query(None, description="Start date; accepts 09/23/2025, 23/09/2025, 2025/9/23, etc."),
    to_time: Optional[str] = Query(None, description="End date; accepts 09/23/2025, 23/09/2025, 2025/9/23, etc."),
    start_date: Optional[str] = Query(None, description="Alias for from_time"),
    end_date: Optional[str] = Query(None, description="Alias for to_time"),
    role_type: Optional[str] = Query(None),
    custom_question: Optional[str] = Query(None),
):
    sites = _resolve_sites(site_name, site_names)
    params = dict(request.query_params)
    params.pop("site_name", None)
    params.pop("site_names", None)
    data_by_site = await _call_endpoint_for_sites(name, sites, params)
    raw_response: Dict[str, Any] = (
        data_by_site if len(sites) > 1 else next(iter(data_by_site.values()))
    )
    return {"raw": raw_response}

@app.post("/v1/s1/{name}", response_model=ProxyResponse)
async def s1_named_post(
    name: str,
    request: Request,
    body: Dict[str, Any] = Body(default={}),
    site_name: Optional[str] = None,
    site_names: Optional[list[str]] = Query(None, description="Select one or more site names"),
    # Common params
    ids: Optional[str] = Query(None, description="Comma-separated IDs (no quotes needed)"),
    primary_email: Optional[str] = Query(None, description="Person email"),
    from_time: Optional[str] = Query(None, description="Start date; accepts 09/23/2025, 23/09/2025, 2025/9/23, etc."),
    to_time: Optional[str] = Query(None, description="End date; accepts 09/23/2025, 23/09/2025, 2025/9/23, etc."),
    start_date: Optional[str] = Query(None, description="Alias for from_time"),
    end_date: Optional[str] = Query(None, description="Alias for to_time"),
    role_type: Optional[str] = Query(None),
    custom_question: Optional[str] = Query(None),
):
    sites = _resolve_sites(site_name, site_names)
    params = dict(request.query_params)
    params.pop("site_name", None)
    params.pop("site_names", None)
    data_by_site = await _call_endpoint_for_sites(name, sites, params, body)
    raw_response: Dict[str, Any] = (
        data_by_site if len(sites) > 1 else next(iter(data_by_site.values()))
    )
    return {"raw": raw_response}
