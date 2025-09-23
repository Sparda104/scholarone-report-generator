import csv
import io
import os
from typing import Any, Dict, Optional

from fastapi import Body, HTTPException, Query, Request, Response, FastAPI
from pydantic import BaseModel, Field
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


class SubmissionSummary(BaseModel):
    documentId: int | None = None
    submissionId: str | None = None
    title: str | None = None
    status: str | None = None
    decision: str | None = None
    submissionDate: str | None = None
    authorFullName: str | None = None
    journalDigitalIssn: str | None = None
    journalPrintIssn: str | None = None


class SubmissionSummaryResponse(BaseModel):
    items: list[SubmissionSummary]
    raw: dict


class SubmissionAuthor(BaseModel):
    fullName: str | None = None
    email: str | None = None


class SubmissionFull(BaseModel):
    submissionId: str | None = None
    documentId: int | None = None
    title: str | None = None
    status: str | None = None
    decision: str | None = None
    submissionDate: str | None = None
    submissionType: str | None = None
    abstract: str | None = None
    correspondingAuthor: str | None = None
    correspondingAuthorEmail: str | None = None
    authors: list[SubmissionAuthor] = Field(default_factory=list)
    journalDigitalIssn: str | None = None
    journalPrintIssn: str | None = None


class SubmissionFullResponse(BaseModel):
    items: list[SubmissionFull]
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


def _extract_submissions(data: dict) -> list[dict]:
    response = data.get("Response") or {}
    for key in ("submission", "submissions", "result", "results"):
        value = response.get(key)
        if not value:
            continue
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [value]
    return []


def _first_author_name(entry: dict) -> str | None:
    contributors = entry.get("contributors") or {}
    authors_section = contributors.get("authors")
    if isinstance(authors_section, dict):
        possible = authors_section.get("author")
    else:
        possible = authors_section
    if isinstance(possible, list) and possible:
        candidate = possible[0]
    elif isinstance(possible, dict):
        candidate = possible
    else:
        candidate = None
    if isinstance(candidate, dict):
        return candidate.get("fullName") or candidate.get("authorFullName")
    return None


def _build_submission_summary(entry: dict) -> SubmissionSummary:
    status_block = entry.get("submissionStatus") or {}
    journal = entry.get("journal") or {}
    submitting_author = entry.get("submittingAuthor") or {}
    return SubmissionSummary(
        documentId=entry.get("documentId"),
        submissionId=entry.get("submissionId"),
        title=entry.get("submissionTitle") or entry.get("title"),
        status=status_block.get("documentStatusName"),
        decision=status_block.get("decisionName"),
        submissionDate=entry.get("submissionDate") or entry.get("datetimeCreated"),
        authorFullName=
        entry.get("authorFullName")
        or submitting_author.get("authorFullName")
        or submitting_author.get("fullName")
        or _first_author_name(entry),
        journalDigitalIssn=entry.get("journalDigitalIssn") or journal.get("journalDigitalIssn"),
        journalPrintIssn=entry.get("journalPrintIssn") or journal.get("journalPrintIssn"),
    )


def _shape_submission_summaries(data: dict) -> list[SubmissionSummary]:
    return [_build_submission_summary(entry) for entry in _extract_submissions(data)]


def _extract_authors(entry: dict) -> list[SubmissionAuthor]:
    authors: list[SubmissionAuthor] = []
    candidates: list[Any] = []
    contributors = entry.get("contributors") or {}
    authors_section = contributors.get("authors")
    if isinstance(authors_section, dict):
        authors_section = authors_section.get("author") or authors_section.get("authors")
    if isinstance(authors_section, list):
        candidates.extend(authors_section)
    elif isinstance(authors_section, dict):
        candidates.append(authors_section)
    direct_authors = entry.get("authors")
    if isinstance(direct_authors, list):
        candidates.extend(direct_authors)
    elif isinstance(direct_authors, dict):
        possible = direct_authors.get("author") or direct_authors
        if isinstance(possible, list):
            candidates.extend(possible)
        elif isinstance(possible, dict):
            candidates.append(possible)
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        authors.append(
            SubmissionAuthor(
                fullName=candidate.get("fullName") or candidate.get("authorFullName"),
                email=candidate.get("primaryEmail") or candidate.get("emailAddress"),
            )
        )
    return authors


def _shape_submission_full(data: dict) -> list[SubmissionFull]:
    results: list[SubmissionFull] = []
    for entry in _extract_submissions(data):
        summary = _build_submission_summary(entry)
        submitting_author = entry.get("submittingAuthor") or {}
        corresponding_email = submitting_author.get("emailAddress") or submitting_author.get("primaryEmail")
        results.append(
            SubmissionFull(
                submissionId=summary.submissionId,
                documentId=summary.documentId,
                title=summary.title,
                status=summary.status,
                decision=summary.decision,
                submissionDate=summary.submissionDate,
                journalDigitalIssn=summary.journalDigitalIssn,
                journalPrintIssn=summary.journalPrintIssn,
                submissionType=entry.get("submissionType"),
                abstract=entry.get("abstractText"),
                correspondingAuthor=submitting_author.get("authorFullName") or submitting_author.get("fullName"),
                correspondingAuthorEmail=corresponding_email,
                authors=_extract_authors(entry),
            )
        )
    return results


def _normalize_ids(ids: str) -> list[str]:
    id_list = [i.strip() for i in ids.split(",") if i.strip()]
    if not id_list:
        raise HTTPException(400, "No valid IDs provided")
    return id_list


def _ids_by_date_params(
    from_time: str | None,
    to_time: str | None,
    start_date: str | None,
    end_date: str | None,
    role_type: str | None,
    custom_question: str | None,
    document_status: str | None,
    criteria: str | None,
    locale_id: int | None,
    external_id: str | None,
) -> Dict[str, Any]:
    actual_from = from_time or start_date
    actual_to = to_time or end_date
    if not actual_from or not actual_to:
        raise HTTPException(400, "from_time/to_time (or start_date/end_date) are required")
    params: Dict[str, Any] = {
        "from_time": actual_from,
        "to_time": actual_to,
    }
    if role_type:
        params["role_type"] = role_type
    if custom_question:
        params["custom_question"] = custom_question
    if document_status:
        params["document_status"] = document_status
    if criteria:
        params["criteria"] = criteria
    if locale_id is not None:
        params["locale_id"] = locale_id
    if external_id:
        params["external_id"] = external_id
    return params


def _fetch_ids_by_date(site: str, params: Dict[str, Any]) -> tuple[list[SubmissionSummary], dict]:
    data = call_named_endpoint("ids_by_date", site, params)
    return _shape_submission_summaries(data), data


def _ids_by_date_csv(items: list[SubmissionSummary]) -> str:
    buffer = io.StringIO()
    fieldnames = [
        "id",
        "submissionId",
        "title",
        "status",
        "decision",
        "submissionDate",
        "authorFullName",
        "journalIssns",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for item in items:
        journal_parts = [part for part in [item.journalDigitalIssn, item.journalPrintIssn] if part]
        writer.writerow(
            {
                "id": item.documentId,
                "submissionId": item.submissionId,
                "title": item.title,
                "status": item.status,
                "decision": item.decision,
                "submissionDate": item.submissionDate,
                "authorFullName": item.authorFullName,
                "journalIssns": ", ".join(journal_parts),
            }
        )
    return buffer.getvalue()

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


@app.get("/v1/submissions/ids-by-date", response_model=SubmissionSummaryResponse)
def submissions_ids_by_date(
    site_name: str | None = None,
    from_time: str | None = Query(None, description="Start date; accepts 09/23/2025, 23/09/2025, 2025/9/23, etc."),
    to_time: str | None = Query(None, description="End date; accepts 09/23/2025, 23/09/2025, 2025/9/23, etc."),
    start_date: str | None = Query(None, description="Alias for from_time"),
    end_date: str | None = Query(None, description="Alias for to_time"),
    role_type: str | None = Query(None, description="Filter by role type"),
    custom_question: str | None = Query(None, description="Filter by custom question"),
    document_status: str | None = Query(None, description="Filter by document status"),
    criteria: str | None = Query(None, description="Date criteria filter"),
    locale_id: int | None = Query(None, description="Locale identifier"),
    external_id: str | None = Query(None, description="External identifier"),
):
    site = _resolve_site(site_name)
    params = _ids_by_date_params(
        from_time,
        to_time,
        start_date,
        end_date,
        role_type,
        custom_question,
        document_status,
        criteria,
        locale_id,
        external_id,
    )
    items, raw = _fetch_ids_by_date(site, params)
    return {"items": items, "raw": raw}


@app.get("/v1/export/ids-by-date.csv")
def export_ids_by_date_csv(
    site_name: str | None = None,
    from_time: str | None = Query(None, description="Start date; accepts 09/23/2025, 23/09/2025, 2025/9/23, etc."),
    to_time: str | None = Query(None, description="End date; accepts 09/23/2025, 23/09/2025, 2025/9/23, etc."),
    start_date: str | None = Query(None, description="Alias for from_time"),
    end_date: str | None = Query(None, description="Alias for to_time"),
    role_type: str | None = Query(None),
    custom_question: str | None = Query(None),
    document_status: str | None = Query(None),
    criteria: str | None = Query(None),
    locale_id: int | None = Query(None),
    external_id: str | None = Query(None),
):
    site = _resolve_site(site_name)
    params = _ids_by_date_params(
        from_time,
        to_time,
        start_date,
        end_date,
        role_type,
        custom_question,
        document_status,
        criteria,
        locale_id,
        external_id,
    )
    items, _ = _fetch_ids_by_date(site, params)
    csv_payload = _ids_by_date_csv(items)
    return Response(content=csv_payload, media_type="text/csv")


@app.get("/v1/submissions/full/by-submission-id", response_model=SubmissionFullResponse)
def submissions_full_by_submission_id(ids: str = Query(..., description="Comma-separated Submission IDs"),
                                      site_name: str | None = None):
    site = _resolve_site(site_name)
    id_list = _normalize_ids(ids)
    params = {"ids": ",".join(id_list)}
    raw = call_named_endpoint("submission_full_by_submissionids", site, params)
    return {"items": _shape_submission_full(raw), "raw": raw}


@app.get("/v1/submissions/full/by-document-id", response_model=SubmissionFullResponse)
def submissions_full_by_document_id(ids: str = Query(..., description="Comma-separated Document IDs"),
                                    site_name: str | None = None):
    site = _resolve_site(site_name)
    id_list = _normalize_ids(ids)
    params = {"ids": ",".join(id_list)}
    raw = call_named_endpoint("submission_full_by_documentids", site, params)
    return {"items": _shape_submission_full(raw), "raw": raw}


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
