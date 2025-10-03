# ==== Hello A2A ICA4AA — Makefile ====
SHELL := /bin/bash

APP            ?= hello-a2a-ica4aa
VERSION        ?= 0.1.0
PORT           ?= 8000
HOST           ?= 0.0.0.0

# -------- Docker image coordinates --------
REGISTRY       ?= docker.io/ruslanmv
IMAGE          ?= $(REGISTRY)/$(APP):$(VERSION)
PLATFORMS      ?= linux/amd64,linux/arm64

# -------- Local Python venv --------
VENV           ?= .venv
PYTHON         ?= $(VENV)/bin/python
UVICORN        ?= $(VENV)/bin/uvicorn
PIP            ?= $(VENV)/bin/pip

.DEFAULT_GOAL := help
.PHONY: help install run clean \
        container-build container--build container-run container--run container-push \
        buildx-buildx buildx-push \
        codeengine-deploy codeengine-delete \
        ec2-run print

help:
	@echo ""
	@echo "Hello A2A ICA4AA — Makefile"
	@echo ""
	@echo "Local:"
	@echo "  make install            Create venv and install requirements.txt"
	@echo "  make run                Run uvicorn locally (uses src/ as app dir)"
	@echo ""
	@echo "Containers:"
	@echo "  make container-build    Build Docker image       (IMAGE=$(IMAGE))"
	@echo "  make container-run      Run container on port $(PORT)"
	@echo "  make container-push     Push image to registry"
	@echo "  make buildx-buildx      Multi-arch buildx build (PLATFORMS=$(PLATFORMS))"
	@echo "  make buildx-push        Multi-arch buildx build & push"
	@echo ""
	@echo "Cloud helpers:"
	@echo "  make codeengine-deploy  Deploy/update IBM Code Engine app"
	@echo "  make codeengine-delete  Delete IBM Code Engine app"
	@echo "  make ec2-run            SSH run on EC2 (requires EC2_HOST & SSH_KEY)"
	@echo ""
	@echo "Misc:"
	@echo "  make print              Show important vars"
	@echo "  make clean              Remove venv & caches"
	@echo ""

# ----- Local -----
$(VENV)/bin/pip:
	python -m venv $(VENV)
	$(PIP) install --upgrade pip

install: $(VENV)/bin/pip requirements.txt
	$(PIP) install -r requirements.txt

run: install
	@echo "Starting: http://$(HOST):$(PORT)"
	PUBLIC_URL=http://localhost:$(PORT) \
	LLM_PROVIDER=$${LLM_PROVIDER:-echo} \
	AGENT_FRAMEWORK=$${AGENT_FRAMEWORK:-langgraph} \
	$(UVICORN) --app-dir src hello_a2a_ica4aa.service:app --host $(HOST) --port $(PORT)

clean:
	rm -rf $(VENV) .pytest_cache __pycache__ .mypy_cache

print:
	@echo "APP=$(APP)"
	@echo "VERSION=$(VERSION)"
	@echo "IMAGE=$(IMAGE)"
	@echo "PORT=$(PORT)"
	@echo "PLATFORMS=$(PLATFORMS)"

# ----- Containers -----
container-build:
	docker build -t $(IMAGE) .

# alias requested
container--build: container-build

container-run:
	docker run --rm -p $(PORT):8000 \
		-e PUBLIC_URL=http://localhost:$(PORT) \
		-e LLM_PROVIDER=$${LLM_PROVIDER:-echo} \
		-e AGENT_FRAMEWORK=$${AGENT_FRAMEWORK:-langgraph} \
		$(IMAGE)

# alias requested
container--run: container-run

container-push:
	docker push $(IMAGE)

buildx-buildx:
	docker buildx build --platform $(PLATFORMS) -t $(IMAGE) . --load

buildx-push:
	docker buildx build --platform $(PLATFORMS) -t $(IMAGE) . --push

# ----- IBM Code Engine helpers -----
# Prereqs: ibmcloud CLI + ce plugin installed & logged in
# Vars you may override:
#   CE_APP_NAME (default $(APP))
#   CE_PORT (default 8000)
#   CE_REGISTRY_SECRET (if using private registry)
#   CE_ENV (space-separated NAME=VALUE pairs)
CE_APP_NAME ?= $(APP)
CE_PORT     ?= 8000
CE_ENV      ?= PUBLIC_URL=https://$(CE_APP_NAME).<your-region>.codeengine.appdomain.cloud LLM_PROVIDER=echo AGENT_FRAMEWORK=langgraph

codeengine-deploy:
	ibmcloud ce application create --name $(CE_APP_NAME) --image $(IMAGE) --port $(CE_PORT) $(foreach kv,$(CE_ENV),--env $(kv)) || \
	ibmcloud ce application update --name $(CE_APP_NAME) --image $(IMAGE) --port $(CE_PORT) $(foreach kv,$(CE_ENV),--env $(kv))

codeengine-delete:
	ibmcloud ce application delete --name $(CE_APP_NAME) --force

# ----- EC2 (simple ssh-run) -----
# Requires EC2_HOST (ec2-user@IP or ubuntu@IP) and SSH_KEY (path to .pem)
ec2-run:
	@test -n "$(EC2_HOST)" || (echo "EC2_HOST not set"; exit 1)
	@test -n "$(SSH_KEY)"  || (echo "SSH_KEY not set"; exit 1)
	ssh -i $(SSH_KEY) -o StrictHostKeyChecking=no $(EC2_HOST) \
	  "docker pull $(IMAGE) && docker rm -f $(APP) 2>/dev/null || true && \
	   docker run -d --name $(APP) -p 80:8000 \
	     -e PUBLIC_URL=http://$$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo localhost) \
	     -e LLM_PROVIDER=echo -e AGENT_FRAMEWORK=langgraph \
	     $(IMAGE))"
