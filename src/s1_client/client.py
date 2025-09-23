from __future__ import annotations
import os
from typing import Dict, List, Optional
from dotenv import load_dotenv
import requests
from requests.auth import HTTPDigestAuth

load_dotenv()

class S1Error(RuntimeError):
    pass

class ScholarOneAPI:
    def __init__(
        self,
        username: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.username = username or os.getenv("S1_USERNAME") or ""
        self.api_key = api_key or os.getenv("S1_API_KEY") or ""
        self.base_url = (base_url or os.getenv("S1_BASE_URL") or "").rstrip("/")
        if not (self.username and self.api_key and self.base_url):
            raise S1Error("Missing S1_USERNAME, S1_API_KEY, or S1_BASE_URL")

        self.session = requests.Session()
        self.session.auth = HTTPDigestAuth(self.username, self.api_key)
        self.session.headers.update({"Accept": "application/json"})

        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        retry = Retry(
            total=4,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "POST"),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _get(self, path: str, params: Dict) -> Dict:
        url = f"{self.base_url}{path}"
        resp = self.session.get(url, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json() if resp.content else {}
        status = (data.get("Response") or {}).get("Status") or (data.get("Response") or {}).get("status")
        if status and status != "SUCCESS":
            raise S1Error(f"S1 API: {status} — {data}")
        return data

    def _post(self, path: str, params: Dict, json: Dict | None = None) -> Dict:
        url = f"{self.base_url}{path}"
        resp = self.session.post(url, params=params, json=json or {}, timeout=60)
        resp.raise_for_status()
        data = resp.json() if resp.content else {}
        status = (data.get("Response") or {}).get("Status") or (data.get("Response") or {}).get("status")
        if status and status != "SUCCESS":
            raise S1Error(f"S1 API: {status} — {data}")
        return data

    def get_submission_info_basic(self, site_name: str, ids: List[str], id_type: str = "submissionids") -> Dict:
        path = f"/api/s1m/v3/submissions/basic/metadata/{id_type}"
        ids_param = ",".join(f"'{x}'" for x in ids)
        return self._get(path, {"site_name": site_name, "ids": ids_param, "_type": "json"})

    def get_person_info_full_by_email(self, site_name: str, email: str) -> Dict:
        path = "/api/s1m/v7/person/full/email/search"
        return self._get(path, {"site_name": site_name, "primary_email": email, "_type": "json"})
