SHELL := /bin/bash
.DEFAULT_GOAL := help

PLATFORM ?= linux/arm64
QEMU_ACCEL ?= hvf
VM_DISPLAY ?= 800x480
TARGET ?=
DEVICE ?=
DISK ?=
NAME ?=
IMAGE ?=
OUT ?=
IDS ?=
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
	@$(UV) pytest -m 'installed or boot' --target=vm --qemu-accel=$(QEMU_ACCEL) --display=$(VM_DISPLAY)

test: test-tier0 test-tier1 ## tiers 0 and 1

test-all: test-tier0 test-tier1 test-tier2 ## tiers 0 to 2

vm-prepare: ## build and cache the tier-2 base image
	@$(UV) python -m pihero_testkit.prepare

vm: ## boot the tier-2 VM and keep it running for inspection
	@$(UV) python -m pihero_testkit.vm --keep --qemu-accel=$(QEMU_ACCEL) --display=$(VM_DISPLAY)

deploy: build ## install built packages on TARGET over SSH
	@test -n "$(TARGET)" || { echo "usage: make deploy TARGET=host"; exit 2; }
	@$(UV) python -m pihero_testkit.deploy "$(TARGET)"

flash: ## write Raspberry Pi OS and a device's files to an SD card (make flash DEVICE=name DISK=disk9)
	@test -n "$(DEVICE)" -a -n "$(DISK)" || { echo "usage: make flash DEVICE=name DISK=diskN   (diskutil list external)"; exit 2; }
	@$(UV) python -m pihero_testkit.flash "$(DEVICE)" "$(DISK)"

.PHONY: backup
backup: ## image an SD card into backups/<host>-<date>.img.xz (make backup [DISK=disk9] [NAME=host])
	@$(UV) python -m pihero_testkit.backup --disk="$(DISK)" --name="$(NAME)"

.PHONY: restore
restore: ## write a backup image onto an SD card (make restore [IMAGE=backups/x.img.xz] [DISK=disk9])
	@$(UV) python -m pihero_testkit.restore --image="$(IMAGE)" --disk="$(DISK)"

clean: ## remove build outputs
	rm -rf dist packages/*/.build

repo: build ## regenerate and sign the flat repo under dist/repo (needs ~/.config/pihero-apt-signing-key.asc)
	@$(UV) python -m pihero_testkit.repo publish --debs 'dist/*.deb' --repo dist/repo --key ~/.config/pihero-apt-signing-key.asc

docs-models: ## regenerate docs/models and the model tables in the READMEs from this Mac's icons (needs pngquant)
	@$(UV) python -m pihero_testkit.model_icons

release: ## run every tier locally, then tag VERSION (make release VERSION=2.0.0)
	@test -n "$(VERSION)" || { echo "usage: make release VERSION=X.Y.Z"; exit 2; }
	@git diff --quiet HEAD || { echo "working tree is dirty"; exit 1; }
	@$(MAKE) test-all
	git tag -a "v$(VERSION)" -m "v$(VERSION)"
	@echo "Tagged v$(VERSION). Push with: git push origin v$(VERSION)"
