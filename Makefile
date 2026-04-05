PYTHON := /home/ai/ai-agents/venv2026/bin/python

.PHONY: release

release:
	$(PYTHON) scripts/release_gate.py
