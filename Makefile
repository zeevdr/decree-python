TOOLS_IMAGE := decree-python-tools
TOOLS_SENTINEL := .tools-image-built
DOCKER_RUN      := docker run --rm -u $(shell id -u):$(shell id -g) -e HOME=/tmp -v $(CURDIR):/workspace -v $(CURDIR)/../decree/proto:/proto:ro -w /workspace $(TOOLS_IMAGE)
DOCKER_RUN_ROOT := docker run --rm -v $(CURDIR):/workspace -v $(CURDIR)/../decree/proto:/proto:ro -w /workspace $(TOOLS_IMAGE)

PROTO_DIR := /proto
GEN_DIR   := sdk/src/opendecree/_generated

.PHONY: all generate lint format typecheck test build clean tools help

all: generate lint typecheck test

## tools: Build the tools Docker image (only when Dockerfile.tools changes)
tools: $(TOOLS_SENTINEL)
$(TOOLS_SENTINEL): build/Dockerfile.tools
	docker build -t $(TOOLS_IMAGE) -f build/Dockerfile.tools build/
	@touch $(TOOLS_SENTINEL)

## generate: Generate Python proto stubs from proto definitions
generate: $(TOOLS_SENTINEL)
	$(DOCKER_RUN) sh -c '\
		SITE=$$(python -c "import site; print(site.getsitepackages()[0])") && \
		GRPC_PROTO=$$(python -c "import grpc_tools; import os; print(os.path.join(os.path.dirname(grpc_tools.__file__), \"_proto\"))") && \
		python -m grpc_tools.protoc \
			-I $(PROTO_DIR) \
			-I $$GRPC_PROTO \
			-I $$SITE \
			--python_out=$(GEN_DIR) \
			--grpc_python_out=$(GEN_DIR) \
			--mypy_out=$(GEN_DIR) \
			--mypy_grpc_out=$(GEN_DIR) \
			$(PROTO_DIR)/centralconfig/v1/*.proto'
	@echo "Generated stubs in $(GEN_DIR)"

## lint: Lint with ruff (check + format)
lint: $(TOOLS_SENTINEL)
	$(DOCKER_RUN) ruff check sdk/src/ sdk/tests/
	$(DOCKER_RUN) ruff format --check sdk/src/ sdk/tests/

## format: Auto-format with ruff
format: $(TOOLS_SENTINEL)
	$(DOCKER_RUN) ruff format sdk/src/ sdk/tests/
	$(DOCKER_RUN) ruff check --fix sdk/src/ sdk/tests/

## typecheck: Type check with mypy
typecheck: $(TOOLS_SENTINEL)
	$(DOCKER_RUN) sh -c "cd sdk && mypy src/"

## test: Run tests with coverage
test: $(TOOLS_SENTINEL)
	$(DOCKER_RUN_ROOT) sh -c "cd sdk && pip install -e . -q 2>/dev/null && pytest --cov --cov-report=term-missing"

## build: Build sdist + wheel
build: $(TOOLS_SENTINEL)
	$(DOCKER_RUN) sh -c "cd sdk && python -m build"

## clean: Remove build artifacts
clean: $(TOOLS_SENTINEL)
	$(DOCKER_RUN_ROOT) rm -rf sdk/dist/ sdk/build/ sdk/src/*.egg-info
	$(DOCKER_RUN_ROOT) find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

## help: Show this help
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/## //' | column -t -s ':'
