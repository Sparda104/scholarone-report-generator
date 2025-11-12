from __future__ import annotations
import os
import logging
from typing import Dict, List, Optional

from dotenv import load_dotenv
import requests
from requests.auth import HTTPDigestAuth

load_dotenv()

logger = logging.getLogger(__name__)
# don't attach handlers here – let uvicorn/app configure them
logger.setLevel(logging.INFO)


class S1Error(RuntimeError):
    pass


class ScholarOneAPI:
    def __init__(
        self,
        username: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        # allow both naming schemes
        self.username = (
            username
            or os.getenv("S1_USERNAME")
            or os.getenv("SCHOLARONE_USERNAME")
            or ""
        )
        self.api_key = (
            api_key
            or os.getenv("S1_API_KEY")
            or os.getenv("SCHOLARONE_API_KEY")
            or ""
        )
        self.base_url = (
            base_url
            or os.getenv("S1_BASE_URL")
            or os.getenv("SCHOLARONE_BASE_URL")
            or ""
        ).rstrip("/")

        if not (self.username and self.api_key and self.base_url):
            raise S1Error("Missing S1_USERNAME, S1_API_KEY, or S1_BASE_URL")

        # optional debug toggle
        self.debug = os.getenv("S1_DEBUG", "0") == "1"

        self.session = requests.Session()
        self.session.auth = HTTPDigestAuth(self.username, self.api_key)
        self.session.headers.update({"Accept": "application/json"})

        # keep your retry setup
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

    def _log_raw(self, resp: requests.Response) -> None:
        """
        Log raw response if debug is enabled or response is bad.
        Truncate to avoid dumping massive payloads.
        """
        try:
            body = resp.text
        except Exception:
            body = "<unreadable body>"
        logger.warning(
            "ScholarOne raw response [%s %s]: %s",
            resp.status_code,
            resp.url,
            body[:4000],
        )

    def _get(self, path: str, params: Dict) -> Dict:
        url = f"{self.base_url}{path}"
        if self.debug:
            logger.info("S1 GET %s params=%s", url, params)

        resp = self.session.get(url, params=params, timeout=60)

        # log on debug or error
        if self.debug or not resp.ok:
            self._log_raw(resp)

        # raise on HTTP errors
        resp.raise_for_status()

        data: Dict = resp.json() if resp.content else {}
        response_obj = data.get("Response") or {}
        status = response_obj.get("Status") or response_obj.get("status")

        # log non-success S1 status
        if status and status != "SUCCESS":
            self._log_raw(resp)
            raise S1Error(f"S1 API: {status} — {data}")

        return data

    def _post(self, path: str, params: Dict, json: Dict | None = None) -> Dict:
        url = f"{self.base_url}{path}"
        if self.debug:
            logger.info("S1 POST %s params=%s json=%s", url, params, json)

        resp = self.session.post(url, params=params, json=json or {}, timeout=60)

        # log on debug or error
        if self.debug or not resp.ok:
            self._log_raw(resp)

        resp.raise_for_status()

        data: Dict = resp.json() if resp.content else {}
        response_obj = data.get("Response") or {}
        status = response_obj.get("Status") or response_obj.get("status")
        if status and status != "SUCCESS":
            self._log_raw(resp)
            raise S1Error(f"S1 API: {status} — {data}")

        return data

    def get_submission_info_basic(
        self, site_name: str, ids: List[str], id_type: str = "submissionids"
    ) -> Dict:
        path = f"/api/s1m/v3/submissions/basic/metadata/{id_type}"
        ids_param = ",".join(f"'{x}'" for x in ids)
        return self._get(
            path,
            {"site_name": site_name, "ids": ids_param, "_type": "json"},
        )

    def get_person_info_full_by_email(self, site_name: str, email: str) -> Dict:
        path = "/api/s1m/v7/person/full/email/search"
        return self._get(
            path,
            {"site_name": site_name, "primary_email": email, "_type": "json"},
        )

