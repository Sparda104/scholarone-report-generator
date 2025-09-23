from fastapi import FastAPI, Query, HTTPException, Body, Request
from pydantic import BaseModel
from typing import Any, Dict, Optional
import os
from src.s1_client.client import ScholarOneAPI, S1Error
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

def _shape_basic(data: dict) -> list[SubmissionBasic]:
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
        )
        items.append(s)
    return items

@app.get("/v1/submissions/basic", response_model=BasicSubmissionsResponse)
def submissions_basic(ids: str = Query(..., description="Comma-separated Submission IDs"),
                      site_name: str | None = None):
    try:
        site = _resolve_site(site_name)
        client = ScholarOneAPI()
        id_list = [x.strip() for x in ids.split(",") if x.strip()]
        if not id_list:
            raise HTTPException(400, "No valid IDs provided")
        data = client.get_submission_info_basic(site, id_list, id_type="submissionids")
        return {"items": _shape_basic(data), "raw": data}
    except HTTPException:
        raise
    except S1Error as e:
        raise HTTPException(502, f"Upstream error: {e}")
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
    site = _resolve_site(site_name)
    params = dict(request.query_params)
    params.pop("site_name", None)
    data = call_named_endpoint(name, site, params)
    return {"raw": data}

@app.post("/v1/s1/{name}", response_model=ProxyResponse)
async def s1_named_post(
    name: str,
    request: Request,
    body: Dict[str, Any] = Body(default={}),
    site_name: Optional[str] = None,
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
    site = _resolve_site(site_name)
    params = dict(request.query_params)
    params.pop("site_name", None)
    data = call_named_endpoint(name, site, params, body)
    return {"raw": data}
