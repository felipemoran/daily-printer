"""
Print a photo over BLE at a fixed byte rate while logging what the printer sends back.

Built to test whether the printer signals flow control (XON 0x11 / XOFF 0x13)
on the MLDP RX characteristic. Never run to completion in 2026-10: the printer
was off. Images over BLE garbled at 7 KB/s and at 800 B/s; see
docs/setup-bluetooth-investigation.md.

Example:
  uv run src/scripts/experiments/ble_probe.py data/photo.jpg --rate 400
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

from bleak import BleakClient, BleakScanner
from escpos.printer import Dummy

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from photo_dither import dither, load, prepare  # noqa: E402
from printer import (  # noqa: E402
    BLE_CHUNK_SIZE,
    BT_PRINTER_NAME,
    MLDP_TX_CHAR,
    PRINT_WIDTH_DOTS,
    _apply_profile,
    _send_paced,
)

RX_CHAR = "49535343-1e4d-4bd9-ba61-23c647249616"


async def _run(data: bytes, rate: float) -> None:
    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: BT_PRINTER_NAME in (d.name or ad.local_name or "").upper(), timeout=15
    )
    if not device:
        sys.exit("printer not found in scan (connected in System Settings? see docs)")
    start, sent = time.monotonic(), 0

    def gone(_):
        print(f"DISCONNECTED at {time.monotonic() - start:.1f}s after {sent} bytes", flush=True)

    def received(_, payload: bytearray):
        print(f"RX at {time.monotonic() - start:.1f}s after {sent} bytes: {payload.hex(' ')}", flush=True)

    async with BleakClient(device, disconnected_callback=gone, timeout=10) as client:
        await client.start_notify(RX_CHAR, received)
        start = time.monotonic()

        async def write(chunk: bytes) -> None:
            nonlocal sent
            await client.write_gatt_char(MLDP_TX_CHAR, chunk, response=False)
            sent += len(chunk)

        try:
            await _send_paced(write, data, chunk_size=BLE_CHUNK_SIZE, bytes_per_second=rate)
            print(f"SENT {sent} bytes in {time.monotonic() - start:.1f}s; listening 5s more", flush=True)
            await asyncio.sleep(5)
        except Exception as error:
            print(f"FAILED at {time.monotonic() - start:.1f}s after {sent} bytes: {error}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("photo", type=Path)
    parser.add_argument("--rate", type=float, default=400, help="bytes per second (default: %(default)s)")
    args = parser.parse_args()
    d = Dummy()
    _apply_profile(d)
    d.hw("INIT")
    d.image(dither(prepare(load(args.photo), width=PRINT_WIDTH_DOTS), "atkinson"), center=False)
    d.ln(3)
    print(f"job: {len(d.output)} bytes at {args.rate:.0f} B/s (~{len(d.output) / args.rate:.0f}s)")
    asyncio.run(_run(d.output, args.rate))


if __name__ == "__main__":
    main()
