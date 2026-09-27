SHELL := /bin/bash
.DEFAULT_GOAL := help

PLATFORM ?= linux/arm64
QEMU_ACCEL ?= hvf
TARGET ?=
UV := uv run --frozen

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n", $$1, $$2}'

doctor: ## check host tooling
	@$(UV) python -m pihero_testkit.doctor

tools: ## build the tools container image
	@$(UV) python -m pihero_testkit.tools

build: ## build all .deb packages into dist/
	@$(UV) python -m pihero_testkit.build

test-tier0: ## unit tests and static checks
	@$(UV) pytest -m tier0

test-tier1: ## install packages into a systemd container and test
	@$(UV) pytest -m installed --target=podman --platform=$(PLATFORM)

test-tier2: ## boot a VM from a device file and test
	@$(UV) pytest -m 'installed or boot' --target=vm --qemu-accel=$(QEMU_ACCEL)

test: test-tier0 test-tier1 ## tiers 0 and 1

test-all: test-tier0 test-tier1 test-tier2 ## tiers 0 to 2

vm-prepare: ## build and cache the tier-2 base image
	@$(UV) python -m pihero_testkit.prepare

vm: ## boot the tier-2 VM and keep it running for inspection
	@$(UV) python -m pihero_testkit.vm --keep --qemu-accel=$(QEMU_ACCEL)

deploy: build ## install built packages on TARGET over SSH
	@test -n "$(TARGET)" || { echo "usage: make deploy TARGET=host"; exit 2; }
	@$(UV) python -m pihero_testkit.deploy "$(TARGET)"

clean: ## remove build outputs
	rm -rf dist packages/*/.build
