"""Thin DRES v2 client (login / list evaluations / submit).

Based on the official OpenAPI spec:
  POST /api/v2/login                       {username, password} -> {sessionId}
  GET  /api/v2/client/evaluation/list      ?session=...         -> [{id, name, ...}]
  POST /api/v2/submit/{evaluationId}       ?session=...         -> ApiClientSubmission

The session token is passed as the `session` query parameter on every call.
"""
from __future__ import annotations

import requests


class DresError(RuntimeError):
    pass


class DresClient:
    def __init__(self, base_url: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session_id: str | None = None

    # -- helpers -----------------------------------------------------------
    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v2{path}"

    def _params(self) -> dict:
        return {"session": self.session_id} if self.session_id else {}

    # -- API ---------------------------------------------------------------
    def login(self, username: str, password: str) -> str:
        r = self.session.post(
            self._url("/login"),
            json={"username": username, "password": password},
            timeout=self.timeout,
        )
        if not r.ok:
            raise DresError(f"login failed ({r.status_code}): {r.text[:200]}")
        self.session_id = r.json().get("sessionId")
        if not self.session_id:
            raise DresError(f"login returned no sessionId: {r.text[:200]}")
        return self.session_id

    def logout(self) -> None:
        """Invalidate the session on the server, then forget it locally.
        Safe to call when not logged in."""
        if self.session_id:
            try:
                self.session.get(self._url("/logout"), params=self._params(),
                                 timeout=self.timeout)
            except requests.RequestException:
                pass  # drop the local session regardless
        self.session_id = None

    def list_evaluations(self) -> list[dict]:
        r = self.session.get(
            self._url("/client/evaluation/list"),
            params=self._params(), timeout=self.timeout,
        )
        if not r.ok:
            raise DresError(f"evaluation/list failed ({r.status_code}): {r.text[:200]}")
        return r.json()

    def submit(
        self,
        evaluation_id: str,
        media_item_name: str,
        start_ms: int,
        end_ms: int,
        collection: str,
        text: str | None = None,
        task_name: str | None = None,
    ) -> dict:
        """Submit a single answer (a video segment and/or a text answer)."""
        answer: dict = {
            "text": text,
            "mediaItemName": media_item_name,
            "mediaItemCollectionName": collection,
            "start": start_ms,
            "end": end_ms,
        }
        answer_set: dict = {"answers": [answer]}
        if task_name:
            answer_set["taskName"] = task_name
        payload = {"answerSets": [answer_set]}

        r = self.session.post(
            self._url(f"/submit/{evaluation_id}"),
            params=self._params(), json=payload, timeout=self.timeout,
        )
        # Return a structured result rather than raising, so the GUI can show it.
        try:
            body = r.json()
        except ValueError:
            body = {"raw": r.text[:300]}
        return {"ok": r.ok, "status": r.status_code, "response": body}
