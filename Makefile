# daily-printer task runner
# Usage: make <target>

.PHONY: help print dry-run render-sample photo-compare photo-strip test web-dev web-build design-sync setup setup-web setup-playwright

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

photo-compare: ## Screen sheet of every dither method: make photo-compare PHOTO=me.jpg
	uv run src/scripts/photo_print.py "$(PHOTO)" --compare

photo-strip: ## Print a band per dither method: make photo-strip PHOTO=me.jpg
	uv run src/scripts/photo_print.py "$(PHOTO)" --test-strip

test: ## Run the unit tests
	uv run python -m unittest discover -s tests

# ── Web UI ────────────────────────────────────────────────────────────────────

web-dev: ## Start Vite dev server (edits web/public/payload.json to preview)
	cd web && npm run dev

web-build: ## Build web/dist (runs automatically during print)
	cd web && npm run build

design-sync: ## Mirror the design system and regenerate web files: make design-sync SRC=<downloaded project/>
	uv run src/scripts/sync_design_system.py $(SRC)

# ── Setup ─────────────────────────────────────────────────────────────────────

setup: setup-web setup-playwright ## Install all dependencies

setup-web: ## Install Node dependencies for the web UI
	cd web && npm install

setup-playwright: ## Install Playwright's Chromium browser
	uv run playwright install chromium
