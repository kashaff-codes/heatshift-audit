"""Minimal REST client for the FortyGuard Temperature API.

Async pattern: POST an analysis endpoint -> activity_id, then poll
GET /v1/status/{activity_id} until Completed or Failed. Credits are charged
only on Completed, and identical re-runs are charged again, so Completed
results go through the disk cache.

The API key is never printed: every error message passes through _redact().
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from .cache import DiskCache, NullCache

BASE_URL = "https://api.fortyguard.com"
USAGE_PATH = "/v1/system/fetch-api-key-usage"


class FortyGuardError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None,
                 activity_id: str | None = None, body: Any = None):
        self.status_code = status_code
        self.activity_id = activity_id
        self.body = body
        parts = [message]
        if status_code is not None:
            parts.append(f"(HTTP {status_code})")
        if activity_id:
            parts.append(f"[activity_id={activity_id}]")
        super().__init__(" ".join(parts))


@dataclass
class ActivityResult:
    endpoint: str
    request: dict
    status: str                      # Completed | Failed | Timeout
    activity_id: str | None
    result: Any = None
    latency_s: float | None = None   # submit -> terminal status
    submit_latency_s: float | None = None
    polls: int = 0
    cached: bool = False
    raw_status: Any = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "Completed"

    def to_dict(self) -> dict:
        return {
            "endpoint": self.endpoint,
            "request": self.request,
            "status": self.status,
            "activity_id": self.activity_id,
            "latency_s": self.latency_s,
            "submit_latency_s": self.submit_latency_s,
            "polls": self.polls,
            "cached": self.cached,
            "error": self.error,
            "result": self.result,
        }


@dataclass
class FortyGuardClient:
    api_key: str
    base_url: str = BASE_URL
    cache: DiskCache | NullCache = field(default_factory=DiskCache)
    poll_interval: float = 5.0
    max_wait: float = 360.0
    timeout: float = 60.0
    log: Callable[[str], None] = lambda msg: None
    sleep: Callable[[float], None] = time.sleep
    http: httpx.Client | None = None

    def __post_init__(self) -> None:
        if not self.api_key:
            raise FortyGuardError("FORTYGUARD_API_KEY is not set (put it in .env)")
        if self.http is None:
            self.http = httpx.Client(base_url=self.base_url, timeout=self.timeout)

    @classmethod
    def from_env(cls, **kwargs) -> "FortyGuardClient":
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        return cls(api_key=os.environ.get("FORTYGUARD_API_KEY", ""), **kwargs)

    # ------------------------------------------------------------------ utils
    def _redact(self, text: str) -> str:
        return text.replace(self.api_key, "***") if self.api_key else text

    def _headers(self) -> dict:
        return {"api-key": self.api_key, "Content-Type": "application/json"}

    def _json(self, resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except ValueError:
            return {"raw_text": self._redact(resp.text[:2000])}

    @staticmethod
    def _message(payload: Any) -> str:
        if isinstance(payload, dict):
            for key in ("message", "detail", "error_message", "msg"):
                val = payload.get(key)
                if isinstance(val, str) and val:
                    return val
            data = payload.get("data")
            if isinstance(data, dict):
                for key in ("message", "detail", "error"):
                    val = data.get(key)
                    if isinstance(val, str) and val:
                        return val
            err = payload.get("error")
            if isinstance(err, (str, dict)) and err:
                return str(err)
        return str(payload)[:500]

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        # A ConnectError (incl. TLS handshake failure) means nothing reached the
        # server, so it is safe to retry any method. Read-side errors are only
        # retried for GET: never blindly re-POST a job that may have been accepted.
        retryable: tuple = (httpx.ConnectError, httpx.ConnectTimeout)
        if method == "GET":
            retryable += (httpx.TransportError,)
        last_exc: Exception | None = None
        for i in range(4):
            try:
                return self.http.request(method, path, headers=self._headers(), **kwargs)
            except retryable as exc:
                last_exc = exc
                self.log(f"network error on {method} {path}: {type(exc).__name__}; retry {i + 1}")
                self.sleep(2 * (i + 1))
        raise FortyGuardError(self._redact(f"Network error calling {path}: {last_exc}"))

    # ------------------------------------------------------------- endpoints
    def credits(self) -> dict:
        """POST /v1/system/fetch-api-key-usage (free; key in the JSON body)."""
        resp = self._request("POST", USAGE_PATH, json={"api_key": self.api_key})
        payload = self._json(resp)
        if resp.status_code != 200:
            raise FortyGuardError(self._redact(self._message(payload)), status_code=resp.status_code, body=payload)
        return payload.get("data", payload) if isinstance(payload, dict) else payload

    def submit(self, endpoint: str, body: dict) -> tuple[str, float]:
        t0 = time.perf_counter()
        resp = self._request("POST", endpoint, json=body)
        dt = time.perf_counter() - t0
        payload = self._json(resp)
        if resp.status_code >= 500:
            # Observed 17 Nov 2026: a 504 "upstream request timeout" on submit can still create
            # (and charge for) the job, without returning an activity_id. Never auto-retry.
            raise FortyGuardError(
                self._redact(self._message(payload)) + " — the job may still have been created and "
                "charged; check credits before re-submitting", status_code=resp.status_code, body=payload)
        if resp.status_code != 200 or (isinstance(payload, dict) and payload.get("error") is True):
            raise FortyGuardError(self._redact(self._message(payload)), status_code=resp.status_code, body=payload)
        try:
            return payload["data"]["activity_id"], dt
        except (KeyError, TypeError):
            raise FortyGuardError(f"No activity_id in response: {str(payload)[:300]}",
                                  status_code=resp.status_code, body=payload)

    def status(self, activity_id: str, result_delivery: str | None = None) -> tuple[int, Any]:
        params = {"result_delivery": result_delivery} if result_delivery else None
        resp = self._request("GET", f"/v1/status/{activity_id}", params=params)
        return resp.status_code, self._json(resp)

    def poll(self, activity_id: str, result_delivery: str | None = None) -> tuple[str, Any, int]:
        """Poll until Completed/Failed. 404 right after submit = not ready yet."""
        start = time.perf_counter()
        polls = 0
        server_errors = 0
        while True:
            self.sleep(self.poll_interval)
            polls += 1
            try:
                code, payload = self.status(activity_id, result_delivery)
            except FortyGuardError:
                code, payload = 599, {"message": "network error while polling"}
            data = payload.get("data") if isinstance(payload, dict) else None
            state = data.get("status") if isinstance(data, dict) else None
            if code == 200 and state in ("Completed", "Failed"):
                return state, payload, polls
            if code >= 500:  # observed: intermittent 504 "upstream request timeout"
                server_errors += 1
                self.log(f"status {code} for {activity_id}; still polling ({server_errors})")
                if server_errors >= 10:
                    raise FortyGuardError(self._redact(self._message(payload)), status_code=code,
                                          activity_id=activity_id, body=payload)
            elif code not in (200, 404):
                raise FortyGuardError(self._redact(self._message(payload)), status_code=code,
                                      activity_id=activity_id, body=payload)
            if time.perf_counter() - start > self.max_wait:
                return "Timeout", payload, polls

    def resume(self, endpoint: str, body: dict, activity_id: str, *,
               result_delivery: str | None = None) -> ActivityResult:
        """Poll an already-submitted activity (no new charge) and cache it."""
        t0 = time.perf_counter()
        state, payload, polls = self.poll(activity_id, result_delivery)
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        res = ActivityResult(endpoint=endpoint, request=body, status=state, activity_id=activity_id,
                             result=data.get("result"), latency_s=round(time.perf_counter() - t0, 2),
                             polls=polls, raw_status={k: v for k, v in data.items() if k != "result"})
        if state == "Completed":
            self.cache.put(endpoint, body, res.to_dict() | {"raw_status": res.raw_status})
        return res

    def run(self, endpoint: str, body: dict, *, use_cache: bool = True,
            result_delivery: str | None = None) -> ActivityResult:
        """Submit + poll, with cache. Raises FortyGuardError on HTTP rejection."""
        if use_cache:
            hit = self.cache.get(endpoint, body)
            if hit is not None:
                self.log(f"cache hit {endpoint}")
                res = ActivityResult(**{k: v for k, v in hit.items() if k in ActivityResult.__dataclass_fields__})
                res.cached = True
                return res

        pending = self.cache.get_pending(endpoint, body) if use_cache else None
        if pending:
            self.log(f"resuming already-submitted {endpoint} activity {pending} (no new charge)")
            activity_id, submit_dt = pending, 0.0
        else:
            activity_id, submit_dt = self.submit(endpoint, body)
            self.log(f"submitted {endpoint} -> {activity_id}")
            if use_cache:
                self.cache.put_pending(endpoint, body, activity_id)
        t0 = time.perf_counter()
        state, payload, polls = self.poll(activity_id, result_delivery)
        if state in ("Completed", "Failed") and use_cache:
            self.cache.clear_pending(endpoint, body)
        latency = round(time.perf_counter() - t0 + submit_dt, 2)
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        res = ActivityResult(
            endpoint=endpoint, request=body, status=state, activity_id=activity_id,
            result=data.get("result") if isinstance(data, dict) else None,
            latency_s=latency, submit_latency_s=round(submit_dt, 2), polls=polls,
            raw_status={k: v for k, v in data.items() if k != "result"} if isinstance(data, dict) else None,
        )
        if state != "Completed":
            res.error = f"Activity {state} (no reason given by API)"
        elif use_cache:
            self.cache.put(endpoint, body, res.to_dict() | {"raw_status": res.raw_status})
        self.log(f"{endpoint} {state} in {latency}s")
        return res
