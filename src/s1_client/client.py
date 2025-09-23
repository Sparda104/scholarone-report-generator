from __future__ import annotations

import logging
import os
import uuid
from time import perf_counter
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv
from requests.auth import HTTPDigestAuth

load_dotenv()

logger = logging.getLogger(__name__)

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

    def _perform_request(self, method: str, path: str, params: Dict, json: Dict | None = None) -> Dict:
        url = f"{self.base_url}{path}"
        request_id = uuid.uuid4().hex
        start = perf_counter()
        logger.info("S1 request start [%s] %s %s", request_id, method.upper(), path)
        resp = None
        try:
            if method.upper() == "GET":
                resp = self.session.get(url, params=params, timeout=60)
            elif method.upper() == "POST":
                resp = self.session.post(url, params=params, json=json or {}, timeout=60)
            else:
                raise ValueError(f"Unsupported method {method}")
            resp.raise_for_status()
            data = resp.json() if resp.content else {}
            status = (data.get("Response") or {}).get("Status") or (data.get("Response") or {}).get("status")
            if status and status != "SUCCESS":
                logger.warning("S1 request upstream failure [%s] status=%s", request_id, status)
                raise S1Error(f"S1 API: {status} — {data}")
            elapsed = perf_counter() - start
            logger.info(
                "S1 request success [%s] %s %s status=%s time=%.3fs",
                request_id,
                method.upper(),
                path,
                resp.status_code,
                elapsed,
            )
            return data
        except Exception:
            elapsed = perf_counter() - start
            logger.exception(
                "S1 request error [%s] %s %s after %.3fs",
                request_id,
                method.upper(),
                path,
                elapsed,
            )
            raise

    def _get(self, path: str, params: Dict) -> Dict:
        return self._perform_request("GET", path, params)

    def _post(self, path: str, params: Dict, json: Dict | None = None) -> Dict:
        return self._perform_request("POST", path, params, json=json)

    def get_submission_info_basic(self, site_name: str, ids: List[str], id_type: str = "submissionids") -> Dict:
        path = f"/api/s1m/v3/submissions/basic/metadata/{id_type}"
        ids_param = ",".join(f"'{x}'" for x in ids)
        return self._get(path, {"site_name": site_name, "ids": ids_param, "_type": "json"})

    def get_person_info_full_by_email(self, site_name: str, email: str) -> Dict:
        path = "/api/s1m/v7/person/full/email/search"
        return self._get(path, {"site_name": site_name, "primary_email": email, "_type": "json"})
