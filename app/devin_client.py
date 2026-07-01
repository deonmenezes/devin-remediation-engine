import requests

from . import config


class DevinClient:
    """Thin wrapper around the Devin v3 sessions API.

    https://docs.devin.ai/api-reference/overview
    """

    def __init__(self, api_key=None, org_id=None, base_url=None):
        self.api_key = api_key or config.DEVIN_API_KEY
        self.org_id = org_id or config.DEVIN_ORG_ID
        self.base_url = base_url or config.DEVIN_API_BASE
        self._http = requests.Session()
        self._http.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def _org_url(self, suffix=""):
        return f"{self.base_url}/organizations/{self.org_id}{suffix}"

    def whoami(self):
        resp = self._http.get(f"{self.base_url}/self", timeout=15)
        resp.raise_for_status()
        return resp.json()

    def create_session(self, prompt, title, tags=None, max_acu_limit=None):
        body = {"prompt": prompt, "title": title}
        if tags:
            body["tags"] = tags
        if max_acu_limit:
            body["max_acu_limit"] = max_acu_limit
        resp = self._http.post(self._org_url("/sessions"), json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_session(self, session_id):
        resp = self._http.get(self._org_url(f"/sessions/{session_id}"), timeout=30)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def is_terminal(session):
        status = session.get("status")
        detail = session.get("status_detail")
        return status in ("exit", "error") or detail == "finished"

    @staticmethod
    def is_error(session):
        return session.get("status") == "error"

    @staticmethod
    def pull_request_urls(session):
        return [pr.get("pr_url") for pr in session.get("pull_requests", []) if pr.get("pr_url")]
