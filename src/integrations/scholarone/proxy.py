from __future__ import annotations
import os
from datetime import datetime, time, timedelta
from typing import Any, Dict, Iterable, List, Tuple

from fastapi import HTTPException
from src.s1_client.client import ScholarOneAPI, S1Error
from src.core.constants import ALLOWED_SITES
from .endpoints import ENDPOINTS, EndpointDef

def _validate_site(site: str) -> str:
    if not site or site not in ALLOWED_SITES:
        raise HTTPException(400, f"Invalid site_name '{site}'. Must be one of: {', '.join(ALLOWED_SITES)}")
    return site

def _ensure_ids_quoted(ids: str) -> str:
    parts = [p.strip() for p in str(ids).split(",") if p.strip()]
    norm = []
    for p in parts:
        if p.startswith("'") and p.endswith("'"):
            norm.append(p)
        else:
            norm.append(f"'{p}'")
    return ",".join(norm)

_DATE_PATTERNS = [
    "%m/%d/%Y", "%d/%m/%Y", "%Y/%d/%m",
    "%m/%-d/%Y", "%-m/%d/%Y", "%d/%-m/%Y", "%-d/%m/%Y",
    "%Y/%m/%d", "%Y/%-m/%-d",
]
def _parse_user_date(s: str) -> datetime:
    s = s.strip()
    for pat in _DATE_PATTERNS:
        try:
            return datetime.strptime(s, pat)
        except Exception:
            continue
    for pat in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, pat)
        except Exception:
            pass
    raise HTTPException(400, f"Could not parse date '{s}'. Expected one of: 09/23/2025, 23/09/2025, 2025/23/09, 9/23/2025, 23/9/2025, 2025/23/9, 2025/9/23, or ISO YYYY-MM-DD.")

def _to_utc_z(dt: datetime, end_of_day: bool = False) -> str:
    return dt.strftime("%Y-%m-%dT23:59:59Z" if end_of_day else "%Y-%m-%dT00:00:00Z")

def _massage_params(defn: EndpointDef, params: Dict[str, Any]) -> Dict[str, Any]:
    if "_type" in (defn.get("required_params") or []) and "_type" not in params:
        params["_type"] = "json"
    if "ids" in (defn.get("required_params") or []) and "ids" in params:
        params["ids"] = _ensure_ids_quoted(str(params["ids"]))
    if defn.get("path", "").endswith("/idsByDate"):
        start = params.get("from_time") or params.get("start_date")
        end = params.get("to_time") or params.get("end_date")
        if not start or not end:
            raise HTTPException(400, "from_time/to_time (or start_date/end_date) are required for ids_by_date")
        params["from_time"] = _to_utc_z(_parse_user_date(str(start)), end_of_day=False)
        params["to_time"] = _to_utc_z(_parse_user_date(str(end)), end_of_day=True)
        params.pop("start_date", None)
        params.pop("end_date", None)
    return params

def _date_batch_window_days() -> int:
    try:
        value = int(os.getenv("SCHOLARONE_DATE_RANGE_BATCH_DAYS", "7"))
        return value if value > 0 else 1
    except ValueError:
        return 7

_ISO_UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

def _split_date_range_batches(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    from_time = params.get("from_time")
    to_time = params.get("to_time")
    if not from_time or not to_time:
        return [params]
    try:
        start_dt = datetime.strptime(str(from_time), _ISO_UTC_FORMAT)
        end_dt = datetime.strptime(str(to_time), _ISO_UTC_FORMAT)
    except Exception:
        return [params]
    start_date = start_dt.date()
    end_date = end_dt.date()
    if start_date > end_date:
        return [params]
    window_days = _date_batch_window_days()
    if window_days <= 1:
        return [params]
    total_days = (end_date - start_date).days + 1
    if total_days <= window_days:
        return [params]
    batches: List[Dict[str, Any]] = []
    current_start = start_date
    while current_start <= end_date:
        current_end = min(current_start + timedelta(days=window_days - 1), end_date)
        batch = dict(params)
        batch["from_time"] = datetime.combine(current_start, time(0, 0, 0)).strftime(_ISO_UTC_FORMAT)
        batch["to_time"] = datetime.combine(current_end, time(23, 59, 59)).strftime(_ISO_UTC_FORMAT)
        batches.append(batch)
        current_start = current_end + timedelta(days=1)
    return batches

def _merge_ids_by_date_responses(
    batches: Iterable[Tuple[Dict[str, Any], Dict[str, Any]]]
) -> Dict[str, Any]:
    combined_results: List[Any] = []
    total_count = 0
    statuses: List[str] = []
    meta_batches: List[Dict[str, Any]] = []

    for params, response in batches:
        resp_section = response.get("Response") or response.get("response") or {}
        status = resp_section.get("Status") or resp_section.get("status")
        if status:
            statuses.append(status)
        result = resp_section.get("Result") or resp_section.get("result")
        if isinstance(result, list):
            combined_results.extend(result)
        elif result:
            combined_results.append(result)
        count = resp_section.get("Count") or resp_section.get("count")
        if isinstance(count, int):
            total_count += count
        meta_batches.append({
            "from_time": params.get("from_time"),
            "to_time": params.get("to_time"),
            "count": count if isinstance(count, int) else None,
            "response": response,
        })

    status = "SUCCESS"
    if statuses and any(s for s in statuses if s and s.upper() != "SUCCESS"):
        status = statuses[-1]

    response_payload: Dict[str, Any] = {
        "Response": {
            "Status": status,
            "Result": combined_results,
        },
        "Meta": {
            "batch_count": len(meta_batches),
            "batches": meta_batches,
        },
    }
    if total_count:
        response_payload["Response"]["Count"] = total_count
    return response_payload

def _call_single_endpoint(
    client: ScholarOneAPI,
    defn: EndpointDef,
    params: Dict[str, Any],
    body: Dict[str, Any] | None,
    method: str,
) -> Dict[str, Any]:
    if method == "GET":
        return client._get(defn["path"], params)
    if method == "POST":
        return client._post(defn["path"], params, json=body or {})
    raise HTTPException(405, f"Unsupported method {method}")

def _call_with_strategies(
    client: ScholarOneAPI,
    defn: EndpointDef,
    params: Dict[str, Any],
    body: Dict[str, Any] | None,
    method: str,
) -> Dict[str, Any]:
    if defn.get("path", "").endswith("/idsByDate"):
        batches = _split_date_range_batches(params)
        if len(batches) == 1:
            return _call_single_endpoint(client, defn, batches[0], body, method)
        responses: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
        for batch_params in batches:
            responses.append((batch_params, _call_single_endpoint(client, defn, batch_params, body, method)))
        return _merge_ids_by_date_responses(responses)
    return _call_single_endpoint(client, defn, params, body, method)

def call_named_endpoint(name: str, site_name: str, params: Dict[str, Any], body: Dict[str, Any] | None = None) -> Dict:
    if name not in ENDPOINTS:
        raise HTTPException(404, f"Unknown endpoint name '{name}'. Add it in endpoints.py.")
    defn = ENDPOINTS[name]
    _validate_site(site_name)
    required = defn.get("required_params") or []
    full_params = dict(params or {})
    full_params["site_name"] = site_name
    full_params = _massage_params(defn, full_params)
    missing = [p for p in required if p not in full_params]
    if missing:
        raise HTTPException(400, f"Missing required params: {', '.join(missing)}")
    client = ScholarOneAPI()
    method = defn.get("method", "GET").upper()
    try:
        return _call_with_strategies(client, defn, full_params, body, method)
    except S1Error as e:
        raise HTTPException(502, f"Upstream S1 error: {e}")
