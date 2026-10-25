"""
Run the print server: job intake, the admin API and the device connections.

Example:
  uv run src/scripts/print_server.py --config ~/print-server/config.toml
"""

from __future__ import annotations

import argparse
import asyncio
import errno
import logging
import signal
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from aiohttp import web  # noqa: E402

from http_api import create_app  # noqa: E402
from job_queue import JobQueue  # noqa: E402
from render_job import DIST_DIR  # noqa: E402
from server_config import ConfigError, ServerConfig, load_config  # noqa: E402

log = logging.getLogger("print_server")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Take print jobs over HTTP and deliver them to the printer devices.",
        epilog="See samples/print-server.example.toml for the config format.",
    )
    parser.add_argument("--config", required=True, type=Path, metavar="PATH", help="the server TOML config")
    return parser.parse_args()


async def _serve(config: ServerConfig, queue: JobQueue) -> int:
    runner = web.AppRunner(create_app(config, queue), access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner, config.host, config.port).start()
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            log.error("port %d on %s is in use; is another print server running?", config.port, config.host)
        else:
            log.error("cannot listen on %s:%d: %s", config.host, config.port, error.strerror or error)
        await runner.cleanup()
        return 1

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    printers = ", ".join(config.printers) or "none"
    log.info("listening on http://%s:%d (printers: %s)", config.host, config.port, printers)
    await stop.wait()
    log.info("stopping")
    await runner.cleanup()
    return 0


def main() -> None:
    args = _parse_args()
    # python-escpos adds a root handler on import, so force replaces it.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", force=True)
    try:
        config = load_config(args.config)
    except ConfigError as error:
        print(error, file=sys.stderr)
        sys.exit(2)
    if not (DIST_DIR / "index.html").is_file():
        log.warning("%s is missing: receipt jobs will fail until you run `make web-build`", DIST_DIR / "index.html")
    try:
        config.database.parent.mkdir(parents=True, exist_ok=True)
        queue = JobQueue(config.database)
    except Exception as error:
        print(f"Cannot open the job database {config.database}: {error}", file=sys.stderr)
        sys.exit(1)
    try:
        code = asyncio.run(_serve(config, queue))
    finally:
        queue.close()
    log.info("stopped")
    sys.exit(code)


if __name__ == "__main__":
    main()
