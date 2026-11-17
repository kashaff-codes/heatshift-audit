"""Tiny JSON-RPC client for the FortyGuard MCP server (Streamable HTTP).

Used for Phase A MCP tests (T8, T9). Auth: Authorization: Bearer <key>.
Usage:
  python scripts/mcp_client.py tools            # list tools (names + descriptions)
  python scripts/mcp_client.py schema <tool>    # print one tool's input schema
  python scripts/mcp_client.py call <tool> '<json args>'
"""

from __future__ import annotations

import json
import os
import sys
import time

import httpx
from dotenv import load_dotenv

MCP_URL = "https://tos-mcp.app.fortyguard.com/mcp"


class MCPClient:
    def __init__(self, key: str, url: str = MCP_URL):
        self.key = key
        self.url = url
        self.session_id: str | None = None
        self._id = 0
        self.http = httpx.Client(timeout=600)

    def _headers(self) -> dict:
        h = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    def _post(self, payload: dict) -> dict | None:
        for attempt in range(4):
            try:
                resp = self.http.post(self.url, headers=self._headers(), json=payload)
                break
            except httpx.ConnectError:  # TLS handshake failed; nothing was sent
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))
        sid = resp.headers.get("mcp-session-id")
        if sid:
            self.session_id = sid
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:800].replace(self.key, '***')}")
        if "id" not in payload:
            return None
        ctype = resp.headers.get("content-type", "")
        if "text/event-stream" in ctype:
            result = None
            for line in resp.text.splitlines():
                if line.startswith("data:"):
                    data = line[5:].strip()
                    if not data:
                        continue
                    msg = json.loads(data)
                    if msg.get("id") == payload["id"]:
                        result = msg
            return result
        return resp.json() if resp.text else None

    def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            msg["params"] = params
        out = self._post(msg)
        if out is None:
            raise RuntimeError(f"No response for {method}")
        if "error" in out:
            raise RuntimeError(f"JSON-RPC error: {out['error']}")
        return out["result"]

    def initialize(self) -> dict:
        res = self.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "heatshift-phase-a", "version": "0.1"},
        })
        try:
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except RuntimeError as exc:  # observed: intermittent 504 on this notification
            print(f"# warning: notifications/initialized failed: {exc}", file=sys.stderr)
        return res

    def tools(self) -> list[dict]:
        return self.request("tools/list")["tools"]

    def call(self, name: str, args: dict) -> tuple[dict, float]:
        t0 = time.perf_counter()
        res = self.request("tools/call", {"name": name, "arguments": args})
        return res, round(time.perf_counter() - t0, 2)


def main(argv: list[str]) -> None:
    load_dotenv()
    key = os.environ.get("FORTYGUARD_API_KEY", "")
    c = MCPClient(key)
    info = c.initialize()
    cmd = argv[0] if argv else "tools"
    if cmd == "info":
        print(json.dumps(info, indent=2))
    elif cmd == "tools":
        for t in c.tools():
            print(f"- {t['name']}: {t.get('description', '')[:160]!r}")
    elif cmd == "schema":
        for t in c.tools():
            if t["name"] == argv[1]:
                print(t.get("description", ""))
                print(json.dumps(t.get("inputSchema"), indent=2))
    elif cmd == "call":
        res, dt = c.call(argv[1], json.loads(argv[2]) if len(argv) > 2 else {})
        print(f"# latency {dt}s")
        print(json.dumps(res, indent=2, ensure_ascii=False).replace(key, "***")[:20000])


if __name__ == "__main__":
    main(sys.argv[1:])
