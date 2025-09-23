from __future__ import annotations
from typing import Dict, Any
from fastapi import HTTPException
from datetime import datetime
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
        if method == "GET":
            return client._get(defn["path"], full_params)
        elif method == "POST":
            return client._post(defn["path"], full_params, json=body or {})
        else:
            raise HTTPException(405, f"Unsupported method {method}")
    except S1Error as e:
        raise HTTPException(502, f"Upstream S1 error: {e}")
