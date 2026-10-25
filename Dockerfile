# One image for the print server and the fake printer devices: docs/setup-deploy.md, "Docker Compose".

FROM node:24.19.0-bookworm-slim AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY design-system /app/design-system
COPY web ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.10.8 AS uv

# <agent>Not bookworm: there, Chromium's headless shell crashed (SIGSEGV) in about 3% of launches on
# Docker Desktop arm64; trixie had 0 crashes in 320 launches.</agent>
FROM python:3.12.15-slim-trixie
COPY --from=uv /uv /uvx /bin/
# The build runs as root and the containers as "printer", so the browsers and the device's
# script environment (in the uv cache) must live outside root's home.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_CACHE_DIR=/opt/uv-cache \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache \
    && uv run --no-sync playwright install --with-deps --only-shell chromium \
    && rm -rf /var/lib/apt/lists/*

COPY src/scripts/print_device.py src/scripts/print_device.py.lock src/scripts/
RUN uv sync --locked --script src/scripts/print_device.py

COPY src src
COPY samples samples
COPY --from=web /app/web/dist web/dist

RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin printer \
    && mkdir /data /printers \
    && chown -R printer /data /printers /opt/uv-cache
USER printer
EXPOSE 8787
CMD [".venv/bin/python", "src/scripts/print_server.py", "--config", "/config/server.toml"]
