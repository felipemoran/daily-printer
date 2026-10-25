"""
printer.py — Shared printer config and setup routines.

Single entry point:

    with open_printer() as p:
        p.text("Hello\\n")
        p.ln(3)

Transport selection is automatic:
  1. USB (preferred) — faster, no connection beep
  2. BLE via MLDP GATT (fallback) — wireless, ~5s scan overhead

USB uses a live escpos Usb object (commands sent immediately).
BLE uses a Dummy buffer (commands accumulated, sent in bulk on context exit).
The caller sees the same escpos API either way.
"""

import math
import os
import sys
import asyncio
from contextlib import contextmanager

import usb.core
from escpos.printer import Usb, Dummy

# ---------------------------------------------------------------------------
# Hardware constants
# ---------------------------------------------------------------------------

# USB
VENDOR_ID = 0x6868
PRODUCT_ID = 0x0200

# Bluetooth BLE (GATT / Microchip MLDP)
BT_PRINTER_NAME = "MPT-II"
MLDP_TX_CHAR    = "49535343-8841-43f4-a8d4-ecbe34729bb3"
BLE_CHUNK_SIZE  = 20  # safe MTU floor for all BLE peripherals
# MLDP is write-without-response with no flow control: sent faster than the
# printer drains, an image garbles after a line or two. Override with the
# DAILY_PRINTER_BLE_BPS env var when tuning.
BLE_BYTES_PER_SECOND = 800

# Print width: confirmed 384 dots by physical calibration (48 mm at 203 DPI).
PRINT_WIDTH_DOTS = 384
DOTS_PER_MM = 8


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _apply_profile(p) -> None:
    p.profile.profile_data["media"]["width"]["pixels"] = PRINT_WIDTH_DOTS


def _usb_available() -> bool:
    return usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID) is not None


def _ble_bytes_per_second() -> float:
    raw = os.environ.get("DAILY_PRINTER_BLE_BPS")
    if raw is None:
        return BLE_BYTES_PER_SECOND
    try:
        rate = float(raw)
    except ValueError:
        rate = math.nan
    if not rate > 0:
        raise ValueError(f"DAILY_PRINTER_BLE_BPS must be a number > 0, got {raw!r}")
    return rate


async def _send_paced(write, data: bytes, *, chunk_size: int, bytes_per_second: float) -> None:
    """Call ``write(chunk)`` for each chunk, holding the average rate to ``bytes_per_second``."""
    loop = asyncio.get_running_loop()
    start = loop.time()
    sent = 0
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        await write(chunk)
        sent += len(chunk)
        delay = start + sent / bytes_per_second - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)


async def _ble_find_and_send(data: bytes, rate: float) -> None:
    """Single BLE session: scan → connect → send → flush → disconnect.

    Must be one session; two sequential asyncio.run() calls (two connections)
    cause the printer to miss the second one.
    """
    from bleak import BleakScanner, BleakClient

    results = await BleakScanner.discover(timeout=10.0, return_adv=True)
    address = next(
        (dev.address for _, (dev, _) in results.items()
         if dev.name and BT_PRINTER_NAME.upper() in dev.name.upper()),
        None,
    )
    if not address:
        raise RuntimeError(f'BLE printer "{BT_PRINTER_NAME}" not found in scan.')

    print(f"BLE: sending {len(data)} bytes at {rate:.0f} B/s (~{len(data) / rate:.0f}s)")
    async with BleakClient(address, timeout=10.0) as client:
        async def write(chunk: bytes) -> None:
            await client.write_gatt_char(MLDP_TX_CHAR, chunk, response=False)

        await _send_paced(write, data, chunk_size=BLE_CHUNK_SIZE, bytes_per_second=rate)
        await asyncio.sleep(0.5)  # let the BT stack flush before disconnect


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@contextmanager
def open_printer():
    """
    Context manager yielding an escpos-compatible printer object.

    Prefers USB; falls back to BLE automatically if USB is not connected.
    On BLE the print job is buffered and transmitted in bulk on context exit.
    """
    if _usb_available():
        # --- USB path ---
        try:
            p = Usb(VENDOR_ID, PRODUCT_ID, timeout=0)
            p.open()
        except Exception as e:
            print(f"ERROR: USB detected but could not open — {e}")
            print("  • Removed from System Settings > Printers & Scanners?")
            print("  • libusb installed? (brew install libusb)")
            sys.exit(1)

        _apply_profile(p)
        p.hw("INIT")
        try:
            yield p
        finally:
            p.close()

    else:
        # --- BLE path ---
        try:
            rate = _ble_bytes_per_second()
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
        print(
            "USB printer not found; falling back to Bluetooth (BLE). "
            "Text prints; images usually garble over BLE. Plug in the USB cable for images.",
            file=sys.stderr,
        )
        p = Dummy()
        _apply_profile(p)
        p.hw("INIT")

        yield p

        data = p.output
        if not data:
            return
        try:
            asyncio.run(_ble_find_and_send(data, rate))
        except Exception as e:
            print(f"ERROR: BLE send failed — {e}")
            print("  • Printer powered on with BT enabled?")
            print("  • Paired and Terminal has Bluetooth permission?")
            print("  • System Settings shows MPT-II as Connected? Click Disconnect (not Forget):")
            print("    a Classic Bluetooth link stops the printer advertising over BLE.")
            print("  • Printing an image? BLE garbles rasters; plug in the USB cable.")
            sys.exit(1)
