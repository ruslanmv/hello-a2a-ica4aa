# src/hello_a2a_ica4aa/service.py
from __future__ import annotations

"""
Hello World A2A (ICA4AA-ready) service.

This module REUSES the production FastAPI app from `universal-a2a-agent`
and EXTENDS it with:
  - GET /a2a/manifest         (single-agent manifest; camelCase; apiVersion/kind/metadata/spec)
  - GET /a2a/agents           (directory endpoint; camelCase)
  - POST /a2a/actions/say_hello  (demo action that delegates to the Universal A2A backend)
  - GET /health               (alias for /healthz)

Why this design?
- You keep the stable, well-tested Universal A2A HTTP surface
  (/a2a, /rpc, /openai/v1/chat/completions, /.well-known/agent-card.json, /healthz, /readyz).
- You add the two ICA4AA discovery routes so platforms like Builder Studio can
  “Upload YAML”, “Get Agents from A2A Server”, or “Agent Endpoint URL” and auto-discover your agent.
- The demo action simply calls the local /a2a pipeline, so you can switch model providers
  and orchestration frameworks via environment variables (LLM_PROVIDER, AGENT_FRAMEWORK)
  without changing this code.
"""

import os
from typing import Any, Dict, Optional

import httpx
from fastapi import Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

# 1) Import the production FastAPI app from universal-a2a-agent.
#    We extend this app with ICA4AA-friendly endpoints.
from a2a_universal.server import app as _universal_app
from a2a_universal.client import A2AClient

# Re-export as our FastAPI app
app = _universal_app


# --------------------------------------------------------------------------------------
# Models for the custom action
# --------------------------------------------------------------------------------------
class SayHelloIn(BaseModel):
    name: Optional[str] = None


class SayHelloOut(BaseModel):
    message: str


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def _public_base_url(request: Request) -> str:
    """
    Compute the externally reachable base URL.

    Priority:
      1) PUBLIC_URL env var (recommended in containers/reverse proxies),
      2) request.base_url (FastAPI/ASGI-derived, respects Host/X-Forwarded-* if configured).

    Always returns without a trailing slash.
    """
    return (os.getenv("PUBLIC_URL") or str(request.base_url)).rstrip("/")


def _backend_base_url(request: Request) -> str:
    """
    Where to call the Universal A2A backend. Defaults to this same service,
    but can be pointed elsewhere if you run a separate A2A hub.

      A2A_BACKEND_BASE  -> overrides
      PUBLIC_URL        -> otherwise
      request.base_url  -> last resort

    Always returns without a trailing slash.
    """
    return (
        os.getenv("A2A_BACKEND_BASE")
        or os.getenv("PUBLIC_URL")
        or str(request.base_url)
    ).rstrip("/")


# --------------------------------------------------------------------------------------
# Convenience: health alias (many platforms probe /health)
# --------------------------------------------------------------------------------------
@app.get("/health", include_in_schema=False)
def health_alias() -> Dict[str, str]:
    # universal-a2a-agent already exposes /healthz; this is a friendly alias
    return {"status": "ok"}


# --------------------------------------------------------------------------------------
# ICA4AA: Agent Manifest (single-agent)
#   - IMPORTANT: Use camelCase and apiVersion/kind/metadata/spec structure.
#   - Matches the same shape as the agent.yaml used in “Upload Agent YAML”.
# --------------------------------------------------------------------------------------
@app.get("/a2a/manifest", tags=["ica4aa"], summary="Agent Manifest")
def get_manifest(request: Request) -> Dict[str, Any]:
    """
    Single-agent manifest so Builder Studio (and other A2A platforms) can
    discover from the base URL. Matches Kubernetes-style shape with camelCase keys.
    """
    base = _public_base_url(request)
    name = os.getenv("HELLO_AGENT_NAME", "hello-world-a2a")
    version = os.getenv("HELLO_AGENT_VERSION", "0.1.0")

    say_hello_input = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Name to greet"}
        },
        "required": [],
        "additionalProperties": False,
    }
    say_hello_output = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": False,
    }

    return {
        "apiVersion": "a2a/v1",
        "kind": "Agent",
        "metadata": {
            "name": name,
            "version": version,
            "description": "A minimal A2A-compatible Hello World agent built on universal-a2a-agent.",
        },
        "spec": {
            "endpointBaseUrl": base,
            # You have both /health and /healthz — keep one stable in the manifest
            "health": "/health",
            "openapi": "/openapi.json",
            "actions": [
                {
                    "name": "say_hello",
                    "description": "Return a friendly greeting using the Universal A2A backend.",
                    "method": "POST",
                    "path": "/a2a/actions/say_hello",
                    "input": say_hello_input,
                    "output": say_hello_output,
                }
            ],
        },
    }


# --------------------------------------------------------------------------------------
# ICA4AA: Directory endpoint (multi-agent list — here we return just this one)
#   - IMPORTANT: Use camelCase keys like manifestUrl and endpointBaseUrl.
# --------------------------------------------------------------------------------------
@app.get("/a2a/agents", tags=["ica4aa"], summary="Agents Directory")
def list_agents(request: Request) -> Dict[str, Any]:
    """
    Directory endpoint so Builder Studio can 'Get Agents from A2A Server'.
    """
    base = _public_base_url(request)
    name = os.getenv("HELLO_AGENT_NAME", "hello-world-a2a")
    version = os.getenv("HELLO_AGENT_VERSION", "0.1.0")

    return {
        "agents": [
            {
                "id": name,  # helpful stable identifier
                "name": name,
                "version": version,
                "manifestUrl": f"{base}/a2a/manifest",
                "endpointBaseUrl": base,
            }
        ]
    }


# --------------------------------------------------------------------------------------
# ICA4AA: Action - say_hello
#   - Delegates to the Universal A2A backend (/a2a) so you get whichever
#     provider/framework you configured via env (LLM_PROVIDER, AGENT_FRAMEWORK, …).
#   - Runs the blocking HTTP call in a thread to avoid blocking the event loop.
# --------------------------------------------------------------------------------------
@app.post("/a2a/actions/say_hello", response_model=SayHelloOut, tags=["ica4aa"], summary="Say Hello")
async def say_hello(payload: SayHelloIn, request: Request) -> SayHelloOut:
    name = (payload.name or "World").strip() or "World"
    prompt = f"Say hello to {name}."

    backend_base = _backend_base_url(request)
    client = A2AClient(base_url=backend_base)

    try:
        # A2AClient.send is synchronous; run in thread to keep async server responsive
        reply = await run_in_threadpool(client.send, prompt, False)
    except (httpx.HTTPError, Exception):
        # Offline / error fallback still returns a friendly message
        reply = f"Hello, {name}!"

    return SayHelloOut(message=reply)
