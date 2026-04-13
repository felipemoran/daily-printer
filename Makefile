# daily-printer task runner
# Usage: make <target>

.PHONY: help print dry-run render-sample web-dev web-build setup setup-web setup-playwright

# Default: show help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

# ── Daily workflow ────────────────────────────────────────────────────────────

print: ## Fetch data, render, and print
	uv run src/scripts/daily_print.py

dry-run: ## Fetch data and render; skip printer
	uv run src/scripts/daily_print.py --no-print

# ── One-off / testing ─────────────────────────────────────────────────────────

render-sample: ## Render the sample payload without printing
	uv run src/scripts/receipt_print.py samples/receipt-sample.json --no-print

# ── Web UI ────────────────────────────────────────────────────────────────────

web-dev: ## Start Vite dev server (edits web/public/payload.json to preview)
	cd web && npm run dev

web-build: ## Build web/dist (runs automatically during print)
	cd web && npm run build

# ── Setup ─────────────────────────────────────────────────────────────────────

setup: setup-web setup-playwright ## Install all dependencies

setup-web: ## Install Node dependencies for the web UI
	cd web && npm install

setup-playwright: ## Install Playwright's Chromium browser
	uv run playwright install chromium
