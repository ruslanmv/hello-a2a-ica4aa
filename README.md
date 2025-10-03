# Hello World A2A (ICA4AA-ready)

A tiny, production-friendly agent that **uses** the `universal-a2a-agent` package (from PyPI) and adds **ICA4AA**-friendly discovery endpoints. It’s perfect as a starter template for teams who want a small agent they can run anywhere (a single VM, EC2 instance, IBM Code Engine, or Kubernetes), yet still integrate cleanly with orchestration platforms that speak **A2A**.

---

## Why this template?

Most “hello world” agents are either coupled to a specific LLM vendor, or demo-only. This one is different:

* **Vendor-neutral runtime.** We reuse Universal A2A’s pluggable provider layer (Watsonx, OpenAI, Ollama, etc.) and framework layer (LangGraph, LangChain, CrewAI…).
* **Interoperable protocols.** You get **A2A**, **JSON-RPC 2.0**, and an **OpenAI-compatible** route in a single service.
* **ICA4AA-ready discovery.** It exposes `/a2a/manifest` and `/a2a/agents` so **Builder Studio** can import via:

  1. Upload YAML, 2) Directory listing, or 3) Base URL (manifest auto-discover).
* **Portable & simple.** Run on a laptop, a single VM, container platforms (Code Engine), or Kubernetes.

**TL;DR:** one small container; a clean HTTP surface; pluggable brains inside. Keep clients stable as your internals evolve.

---

## What you get out of the box

**ICA4AA / discovery endpoints**

* `GET /a2a/manifest` – machine-readable **single agent** manifest
* `GET /a2a/agents` – **directory** listing (here: just this agent)
* `POST /a2a/actions/say_hello` – demo action (delegates to Universal A2A runtime)

**Universal A2A surface** (from `universal-a2a-agent`)

* `POST /a2a` – raw A2A envelope (e.g., `"method": "message/send"`)
* `POST /rpc` – JSON-RPC 2.0 wrapper
* `POST /openai/v1/chat/completions` – OpenAI-compatible
* `GET /healthz`, `GET /readyz`, `GET /.well-known/agent-card.json`

**Pluggable runtime**

* Select a provider at runtime: `LLM_PROVIDER=echo|watsonx|openai|ollama|anthropic|gemini|azure_openai|bedrock`
* Select orchestration style: `AGENT_FRAMEWORK=langgraph|langchain|crewai|native`

---

## Project layout (quick glance)

```
hello-a2a-ica4aa/
├─ README.md
├─ requirements.txt
├─ agent.yaml                     # for “Upload Agent YAML File” flow
├─ .env.example
├─ Dockerfile
├─ k8s/
│  └─ hello-a2a-ica4aa.yaml       # optional, if you use Kubernetes
└─ src/
   └─ hello_a2a_ica4aa/
      ├─ __init__.py
      └─ service.py               # extends the Universal A2A FastAPI app
```

---

## 1) Local development (no Kubernetes required)

> Works on macOS, Linux, and WSL on Windows. You just need Python 3.11+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# minimal dev env
export PUBLIC_URL=http://localhost:8000
export LLM_PROVIDER=echo
export AGENT_FRAMEWORK=langgraph

# run the app
uvicorn --app-dir src hello_a2a_ica4aa.service:app --host 0.0.0.0 --port 8000
```

Or with the included **Makefile**:

```bash
make run
```

### Smoke tests

```bash
# Manifest (for “Agent Endpoint URL” import flow)
curl -s http://localhost:8000/a2a/manifest | jq

# Directory listing (for “Get Agents from A2A Server” flow)
curl -s http://localhost:8000/a2a/agents | jq

# ICA4AA-style action
curl -s -X POST http://localhost:8000/a2a/actions/say_hello \
  -H 'Content-Type: application/json' \
  -d '{"name":"ICA4AA"}' | jq

# Universal A2A (raw)
curl -s http://localhost:8000/a2a -H 'Content-Type: application/json' -d '{
  "method":"message/send",
  "params":{"message":{"role":"user","messageId":"m1","parts":[{"type":"text","text":"ping"}]}}
}' | jq
```

Open the interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 2) Run as a container (single VM, EC2, Code Engine—your choice)

Build the image:

```bash
# Build locally
make container-build IMAGE=docker.io/ruslanmv/hello-a2a-ica4aa:0.1.0
```

Run it anywhere that has Docker:

```bash
# On a VM or EC2:
make container-run IMAGE=docker.io/ruslanmv/hello-a2a-ica4aa:0.1.0 PORT=8000 \
  ENV='PUBLIC_URL=http://<public-host-or-ip>:8000 LLM_PROVIDER=echo AGENT_FRAMEWORK=langgraph'
```

Manual (without Makefile):

```bash
docker run --rm -p 8000:8000 \
  -e PUBLIC_URL=http://<public-host-or-ip>:8000 \
  -e LLM_PROVIDER=echo \
  -e AGENT_FRAMEWORK=langgraph \
  docker.io/ruslanmv/hello-a2a-ica4aa:0.1.0
```

> **Tip (prod-ish):** Put your container behind a TLS proxy (Nginx, Traefik, ALB/ELB, Code Engine HTTPS). Then set `PUBLIC_URL=https://your-domain` so manifests/links are correct.

### IBM Code Engine (optional)

A minimal path:

1. Push your image:

   ```bash
   docker push docker.io/ruslanmv/hello-a2a-ica4aa:0.1.0
   ```

2. Create/update a Code Engine app (conceptual snippet):

   ```bash
   ibmcloud ce app create --name hello-a2a-ica4aa \
     --image docker.io/ruslanmv/hello-a2a-ica4aa:0.1.0 \
     --port 8000 \
     --env PUBLIC_URL=https://hello-a2a-ica4aa.<region>.codeengine.appdomain.cloud \
     --env LLM_PROVIDER=echo \
     --env AGENT_FRAMEWORK=langgraph \
     --min 1 --max 2
   ```

> Code Engine gives you an HTTPS URL out-of-the-box—use that as your `PUBLIC_URL` for clean imports.

### AWS EC2 (optional)

On a small EC2 instance with Docker:

```bash
sudo docker run -d -p 80:8000 \
  -e PUBLIC_URL=http://<ec2-public-ip> \
  -e LLM_PROVIDER=echo \
  -e AGENT_FRAMEWORK=langgraph \
  docker.io/ruslanmv/hello-a2a-ica4aa:0.1.0
```

Open Security Group for inbound TCP 80 (or 8000 if you mapped that directly).

---

## 3) Import into Builder Studio (ICA4AA)

Once your service is reachable (localhost for a local test or a public URL for remote), you can import it in **three ways**:

1. **Upload Agent YAML File**
   Use `agent.yaml` (update `spec.endpointBaseUrl` to your service URL).

2. **Get Agents from A2A Server**
   Use your base + `/a2a/agents`, for example:

   ```
   http://<your-host-or-domain>:8000/a2a/agents
   ```

3. **Agent Endpoint URL**
   Paste just the base:

   ```
   http://<your-host-or-domain>:8000
   ```

   The UI will discover `/a2a/manifest`.

You’ll see one action: **say_hello**. Try payload `{ "name": "World" }`.

---

## 4) Optional: Kubernetes (if you have a cluster)

If your ICA4AA stack runs in Kubernetes, apply the sample manifest:

```bash
kubectl apply -n ica4aa-builder-studio -f k8s/hello-a2a-ica4aa.yaml
```

In-cluster URL:

```
http://hello-a2a-ica4aa.ica4aa-builder-studio.svc.cluster.local:8000
```

---

## 5) Switching providers & frameworks

Because this reuses Universal A2A under the hood, you don’t touch code—just change environment variables.

**Watsonx.ai example**

```bash
export LLM_PROVIDER=watsonx
export WATSONX_API_KEY=...
export WATSONX_URL=https://us-south.ml.cloud.ibm.com
export WATSONX_PROJECT_ID=...
export MODEL_ID=ibm/granite-3-3-8b-instruct
```

**OpenAI example**

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=...
# optional: OPENAI_BASE_URL=https://api.openai.com/v1
```

**Ollama example (local models)**

```bash
export LLM_PROVIDER=ollama
export OLLAMA_BASE_URL=http://localhost:11434
export MODEL_ID=llama3
```

**Framework style**

```bash
export AGENT_FRAMEWORK=langgraph    # or: crewai | langchain | native
```

Restart the container/process; **your HTTP API and ICA4AA routes remain the same**.

---

## 6) Configuration (env vars you’ll care about)

* **PUBLIC_URL** – the public base URL of this service (used in manifests/links).
* **LLM_PROVIDER** – `echo` (no external calls), `watsonx`, `openai`, `ollama`, `anthropic`, `gemini`, `azure_openai`, `bedrock`.
* **AGENT_FRAMEWORK** – `langgraph` (default), `crewai`, `langchain`, or `native`.
* **A2A_BACKEND_BASE** – (optional) if you want `/a2a/actions/say_hello` to call a **remote** Universal A2A backend instead of the same container.

Plus provider-specific credentials (see examples above).

---

## 7) API surface (what’s exposed)

**Discovery & health**

* `GET /a2a/manifest` – single-agent manifest (for “Agent Endpoint URL” imports)
* `GET /a2a/agents` – directory listing (for “Get Agents from A2A Server” imports)
* `GET /healthz` – liveness
* `GET /readyz` – readiness (provider/framework reasons included)
* `GET /.well-known/agent-card.json` – A2A Agent Card (standard discovery doc)

**Core A2A & optional shims (from Universal A2A)**

* `POST /a2a` – raw A2A envelope
* `POST /rpc` – JSON-RPC 2.0 (`method: "message/send"`)
* `POST /openai/v1/chat/completions` – OpenAI-compatible route (great for UIs)

**Demo action (ICA4AA style)**

* `POST /a2a/actions/say_hello` – accepts `{ "name": "…" }`, replies with `{ "message": "…" }`
  Implementation note: it **delegates** to the Universal A2A `/a2a` route under the hood, so it uses whatever provider/framework you configured.

---

## 8) Makefile cheat sheet

```bash
# Run locally (loads venv if present)
make run

# Build a container image
make container-build IMAGE=docker.io/ruslanmv/hello-a2a-ica4aa:0.1.0

# Run the container
make container-run IMAGE=docker.io/ruslanmv/hello-a2a-ica4aa:0.1.0 PORT=8000 \
  ENV='PUBLIC_URL=http://<host>:8000 LLM_PROVIDER=echo AGENT_FRAMEWORK=langgraph'
```

> Prefer `make` because it passes env cleanly and keeps commands consistent across devs.

---

## 9) Troubleshooting

* **`/readyz` is “not-ready”**
  Your provider credentials may be missing or invalid. Check the env vars for your chosen `LLM_PROVIDER`.
  Try `LLM_PROVIDER=echo` first to validate the rest of the stack.

* **Manifest shows the wrong host**
  Set `PUBLIC_URL` to the externally reachable base (e.g., `https://agent.example.com`).

* **Firewall / SG blocks**
  On EC2/VMs, open inbound TCP to the port you mapped (`80` or `8000`).

* **Code Engine 404/timeout**
  Ensure your app listens on `0.0.0.0:8000` (default) and Code Engine “port” is set to `8000`.

---

## 10) How it fits in your architecture (short story)

Your UI (or another agent) talks to this **one** HTTP service. The service then **chooses** which model to call and how to orchestrate the conversation. As your needs evolve—swap Watsonx for OpenAI, migrate LangChain → LangGraph, introduce tools—your clients don’t change. ICA4AA can discover and import the agent with no glue code via the three flows it supports.

**One API on the outside. All the freedom you want on the inside.**

---

**Happy shipping!** If you want a Helm chart, CI workflows, or production hardening checklists next, we can add those too.
