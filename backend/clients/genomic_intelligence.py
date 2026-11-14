"""Thin client for the Genomic Intelligence (GI) models, over their MCP server.

Why MCP and not the REST API: the hosted MCP server at mcp.genomicintelligence.ai
answers on a shared demo key, so the PoC gets real model output with no key at
all. It also fetches reference sequence from Ensembl server-side and hands back
a short handle (``seq_...``), so DNA never passes through this process. If
``GI_API_KEY`` is set, the same server is called with that key instead (higher
caps, private quota). Docs: https://docs.genomicintelligence.ai/mcp

Transport: MCP "Streamable HTTP" (JSON-RPC 2.0 over POST, replies as JSON or
server-sent events, session in the ``Mcp-Session-Id`` header). Only the handful
of calls stage 3 needs are wrapped; pipeline code never talks HTTP itself.

Error handling follows the GI contract: switch on ``error.code``, never the
message. Transient codes are retried with backoff; everything else raises
:class:`GIError` with the code attached.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

import httpx

from backend import config

PROTOCOL_VERSION = "2025-03-26"
CLIENT_INFO = {"name": "b5-hackers-poc", "version": "0.1"}

# GI error codes worth retrying (docs: reference/errors). Everything else is permanent.
RETRYABLE_CODES = {
    "too_many_requests",
    "rate_limited",
    "model_loading",
    "service_unavailable",
    "timeout",
    "insufficient_memory",
    "gateway_timeout",
}


class GIError(RuntimeError):
    """A GI call failed. ``code`` is the GI error code (or a transport label)."""

    def __init__(self, code: str, message: str, tool: str = ""):
        super().__init__(f"[{code}] {tool}: {message}" if tool else f"[{code}] {message}")
        self.code = code
        self.tool = tool

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE_CODES


def _parse_tool_error(text: str) -> tuple[str, str]:
    """Tool errors arrive as text like 'Error executing tool X: {"error": {...}}'."""
    start = text.find("{")
    if start >= 0:
        try:
            err = json.loads(text[start:]).get("error", {})
            return err.get("code", "tool_error"), err.get("message", text)
        except json.JSONDecodeError:
            pass
    return "tool_error", text


class GIClient:
    """Minimal MCP client for the GI server. Use as a context manager."""

    def __init__(
        self,
        url: str = config.GI_MCP_URL,
        api_key: Optional[str] = config.GI_API_KEY,
        timeout_s: float = config.GI_TIMEOUT_S,
        max_retries: int = config.GI_MAX_RETRIES,
    ):
        self.url = url
        self.max_retries = max_retries
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if api_key:  # never logged; without it the server uses its shared demo key
            headers["Authorization"] = f"Bearer {api_key}"
        self.uses_demo_key = not api_key
        self._http = httpx.Client(timeout=timeout_s, headers=headers)
        self._session: Optional[str] = None
        self._next_id = 0
        self.server_info: dict[str, Any] = {}

    # ------------------------------------------------------------ plumbing
    def __enter__(self) -> "GIClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._session:
            try:  # politely end the MCP session; failure here is harmless
                self._http.delete(self.url, headers={"Mcp-Session-Id": self._session})
            except httpx.HTTPError:
                pass
        self._http.close()

    def _rpc_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _post(self, payload: dict) -> Optional[dict]:
        """POST one JSON-RPC message; return the response with the same id (or None)."""
        headers = {"Mcp-Session-Id": self._session} if self._session else {}
        r = self._http.post(self.url, json=payload, headers=headers)
        if r.status_code == 404 and self._session:
            raise _SessionExpired()
        if r.status_code == 429:
            raise GIError("too_many_requests", f"HTTP 429, retry after {r.headers.get('Retry-After', '?')}s")
        if r.status_code >= 500:
            raise GIError("service_unavailable", f"HTTP {r.status_code}")
        if r.status_code >= 400:
            raise GIError("bad_request", f"HTTP {r.status_code}: {r.text[:300]}")
        if sid := r.headers.get("mcp-session-id"):
            self._session = sid
        if "id" not in payload:  # a notification: nothing comes back
            return None
        messages: list[dict] = []
        if r.headers.get("content-type", "").startswith("text/event-stream"):
            for line in r.text.splitlines():  # SSE: progress notifications, then the result
                if line.startswith("data:"):
                    messages.append(json.loads(line[5:].strip()))
        elif r.text.strip():
            body = r.json()
            messages = body if isinstance(body, list) else [body]
        for m in reversed(messages):
            if m.get("id") == payload["id"]:
                return m
        raise GIError("protocol_error", f"no JSON-RPC reply with id {payload['id']}")

    def _ensure_session(self) -> None:
        if self._session:
            return
        reply = self._post({
            "jsonrpc": "2.0", "id": self._rpc_id(), "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": CLIENT_INFO},
        })
        if not reply or "result" not in reply:
            raise GIError("protocol_error", f"initialize failed: {reply}")
        self.server_info = reply["result"].get("serverInfo", {})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Call one MCP tool and return its ``structuredContent`` (the GI envelope)."""
        delay = 1.0
        for attempt in range(self.max_retries + 1):
            try:
                self._ensure_session()
                reply = self._post({
                    "jsonrpc": "2.0", "id": self._rpc_id(), "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                })
                if "error" in reply:  # JSON-RPC level error (bad method / params)
                    raise GIError("rpc_error", str(reply["error"]), name)
                result = reply["result"]
                if result.get("isError"):
                    text = " ".join(c.get("text", "") for c in result.get("content", []))
                    code, message = _parse_tool_error(text)
                    raise GIError(code, message, name)
                if "structuredContent" in result:
                    return result["structuredContent"]
                text = " ".join(c.get("text", "") for c in result.get("content", []))
                return json.loads(text)
            except _SessionExpired:  # noqa: PERF203
                self._session = None  # sessions expire server-side; open a new one
                if attempt == self.max_retries:
                    raise GIError("session_expired", "MCP session kept expiring", name)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == self.max_retries:
                    raise GIError("timeout", f"{type(exc).__name__}: {exc}", name) from exc
            except GIError as exc:
                if not exc.retryable or attempt == self.max_retries:
                    raise
            time.sleep(delay)
            delay = min(delay * 2, config.GI_BACKOFF_CAP_S)
        raise AssertionError("unreachable")

    # ------------------------------------------------------------ the calls stage 3 uses
    def list_models(self, task: str) -> dict:
        """{task, default_model, models: [{id, bio_spec, ...}]} (flat, not enveloped)."""
        return self.call_tool("list_models", {"task": task})

    def fetch_gene_for_expression(self, gene: str) -> dict:
        """Server-side fetch of a gene-sense, TSS-centred window sized for the expression
        models. Returns data = {ref, tss, strand, region, tss_index, ensembl_id, ...}."""
        return self.call_tool("fetch_gene_for_expression", {"gene": gene, "species": config.GI_SPECIES})

    def fetch_region(self, region: str, strand: int = 1) -> dict:
        """Server-side fetch of 'chrom:start-end' (1-based, inclusive) on the given strand.
        strand=-1 returns the reverse complement, i.e. gene-sense for minus-strand genes."""
        return self.call_tool("fetch_region", {"region": region, "species": config.GI_SPECIES, "strand": strand})

    def predict_expression(self, ref: str, description: str, model: Optional[str] = None) -> dict:
        args = {"sequence_ref": ref, "description": description}
        if model:
            args["model"] = model
        return self.call_tool("predict_expression", args)

    def predict_promoter(self, ref: str, model: Optional[str] = None) -> dict:
        args = {"sequence_ref": ref}
        if model:
            args["model"] = model
        return self.call_tool("predict_promoter", args)

    def predict_chromatin(self, ref: str, model: Optional[str] = None) -> dict:
        args = {"sequence_ref": ref}
        if model:
            args["model"] = model
        return self.call_tool("predict_chromatin", args)

    def find_genes_and_predict_expression(self, ref: str, description: str) -> dict:
        """Composite: annotate the region, then predict each found gene's expression.
        Blocks until done (the server streams progress; we keep only the result)."""
        return self.call_tool(
            "find_genes_and_predict_expression",
            {"sequence_ref": ref, "description": description, "wait": True},
        )


class _SessionExpired(Exception):
    pass
