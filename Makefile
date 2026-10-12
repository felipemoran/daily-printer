# daily-printer task runner
# Usage: make <target>

.PHONY: help print dry-run render-sample template photo-compare photo-strip test server simulate device-fake web-dev web-build design-sync setup setup-web setup-playwright

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

template: ## Render and print a template payload: make template PAYLOAD=samples/templates/ticket.json
	uv run src/scripts/print_template.py "$(PAYLOAD)"

photo-compare: ## Screen sheet of every dither method: make photo-compare PHOTO=me.jpg
	uv run src/scripts/photo_print.py "$(PHOTO)" --compare

photo-strip: ## Print a band per dither method: make photo-strip PHOTO=me.jpg
	uv run src/scripts/photo_print.py "$(PHOTO)" --test-strip

test: ## Run the unit tests
	uv run python -m unittest discover -s tests

# ── Print server ──────────────────────────────────────────────────────────────

server: ## Run the print server: make server CONFIG=~/print-server/config.toml
	@test -n "$(CONFIG)" || { echo "Set CONFIG to the server config, e.g. make server CONFIG=~/print-server/config.toml (format: samples/print-server.example.toml)"; exit 2; }
	uv run src/scripts/print_server.py --config $(CONFIG)

simulate: ## Run the server and two fake printers locally, print two jobs (needs make web-build)
	uv run src/scripts/simulate.py

device-fake: ## Fake printer device: make device-fake TOKEN_FILE=path [SERVER=ws://...] [OUT=dir]
	@test -n "$(TOKEN_FILE)" || { echo "Set TOKEN_FILE to a file holding the printer token, e.g. make device-fake TOKEN_FILE=~/.print-token"; exit 2; }
	uv run src/scripts/print_device.py --server "$(or $(SERVER),ws://127.0.0.1:8787/device)" --token-file $(TOKEN_FILE) --fake "$(or $(OUT),data/fake-printer)"

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
