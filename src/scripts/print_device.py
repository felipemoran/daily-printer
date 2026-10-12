# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "aiohttp>=3.14.5",
#     "pillow>=12.2.0",
#     "python-escpos[usb]>=3.1",
# ]
# ///
"""
Connect this computer's receipt printer to the print server and print the jobs it sends.

Examples:
  PRINT_DEVICE_TOKEN=... uv run --script src/scripts/print_device.py --server wss://device.example.com/device
  uv run --script src/scripts/print_device.py --server ws://127.0.0.1:8787/device --token-file ~/.print-token --fake out/
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from print_device import DeviceClient, FakeSink, UsbSink  # noqa: E402

TOKEN_ENV = "PRINT_DEVICE_TOKEN"


def _parse_args() -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    parser = argparse.ArgumentParser(
        description="Keep a connection open to the print server and print each job it sends.",
        epilog=f"The printer token comes from --token-file, or else from ${TOKEN_ENV}. "
        "There is no --token option: a command-line argument is visible to every user in `ps`.",
    )
    parser.add_argument(
        "--server",
        required=True,
        metavar="URL",
        help="the server's device endpoint, ws:// or wss://, e.g. wss://device.example.com/device",
    )
    parser.add_argument("--token-file", type=Path, metavar="PATH", help="file that holds this printer's token")
    parser.add_argument(
        "--fake",
        type=Path,
        metavar="DIR",
        help="save each job as DIR/<job id>.bin, plus DIR/<job id>.png for a raster job, in place of printing over USB",
    )
    return parser, parser.parse_args()


def _read_token(parser: argparse.ArgumentParser, token_file: Path | None) -> str:
    if token_file is not None:
        try:
            token = token_file.read_text().strip()
        except OSError as error:
            parser.error(f"cannot read the token file: {error}")
        if not token:
            parser.error(f"the token file {token_file} is empty")
        return token
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        parser.error(f"no printer token: pass --token-file PATH or set {TOKEN_ENV}")
    return token


async def _run(client: DeviceClient) -> None:
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, client.stop)
    await client.run()


def main() -> None:
    parser, args = _parse_args()
    if not args.server.startswith(("ws://", "wss://")):
        parser.error(f"--server must start with ws:// or wss://, got {args.server!r}")
    token = _read_token(parser, args.token_file)

    # python-escpos adds a root handler on import, so force replaces it.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True)
    sink = FakeSink(args.fake) if args.fake else UsbSink()
    logging.getLogger("print_device").info(
        "printing to %s", f"fake printer in {args.fake}/" if args.fake else "USB printer"
    )
    asyncio.run(_run(DeviceClient(args.server, token, sink)))


if __name__ == "__main__":
    main()
