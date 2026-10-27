# Use an installed environment: make PYTHON=.venv/bin/python <target>
PYTHON ?= python3
UV ?= uv
RUN ?= data/follow_the_money/run-$(shell date -u +%Y%m%dT%H%M%SZ)

override PYTHONDONTWRITEBYTECODE := 1
override HF_HUB_OFFLINE := 1
override TRANSFORMERS_OFFLINE := 1
override LANGSMITH_TRACING := false
export PYTHONDONTWRITEBYTECODE HF_HUB_OFFLINE TRANSFORMERS_OFFLINE LANGSMITH_TRACING

.PHONY: help test lint lock-check demo eval

help:
	@printf '%s\n' \
	  'test        Run the offline test suite (ML/M365 tests skip without their extras).' \
	  'lint        Check Ruff lint and formatting without changing files.' \
	  'lock-check  Check the lock offline.' \
	  'demo        Run the fictional trace into a new data/follow_the_money/ run.' \
	  'eval        Evaluate synthetic search (requires the ml extra).'

test:
	"$(PYTHON)" -B -m pytest -q -p no:cacheprovider

lint:
	"$(PYTHON)" -B -m ruff check src tests scripts
	"$(PYTHON)" -B -m ruff format --check src tests scripts

lock-check:
	"$(UV)" lock --check --offline

demo:
	"$(PYTHON)" -B -m follow_the_money demo --workspace "$(RUN)/demo"

eval:
	"$(PYTHON)" -B -m follow_the_money evaluate --output "$(RUN)/evaluation"
