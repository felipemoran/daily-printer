"""
printer.py — Shared printer config and setup routines.

Import this module in any script that needs to talk to the printer.
Supports two transports: USB and Bluetooth BLE (MLDP via GATT).

Usage pattern — USB:
    p = open_printer()
    p.text("Hello\n")
    p.ln(3)

Usage pattern — BLE:
    with open_printer_ble() as p:
        p.text("Hello\n")
        p.ln(3)
    # flushes and disconnects on exit
"""

import sys
import asyncio
from contextlib import contextmanager
from escpos.printer import Usb, Dummy

# ---------------------------------------------------------------------------
# Hardware constants
# ---------------------------------------------------------------------------

# USB
VENDOR_ID = 0x6868
PRODUCT_ID = 0x0200

# Bluetooth BLE (GATT / MLDP)
BT_PRINTER_NAME = "MPT-II"
# Microchip MLDP service — confirmed working for ESC/POS data
MLDP_TX_CHAR = "49535343-8841-43f4-a8d4-ecbe34729bb3"
BLE_CHUNK_SIZE = 20  # safe MTU floor; increase if printer supports larger

# Bluetooth SPP serial port (Classic BT — does NOT work on macOS; RFCOMM link
# never auto-establishes from a script. Kept for reference only.)
BT_SPP_PORT = "/dev/cu.MPT-II"

# Print width: confirmed 384 dots by physical calibration (48 mm at 203 DPI).
PRINT_WIDTH_DOTS = 384


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _apply_profile(p) -> None:
    p.profile.profile_data["media"]["width"]["pixels"] = PRINT_WIDTH_DOTS


async def _find_ble_address() -> str:
    from bleak import BleakScanner
    results = await BleakScanner.discover(timeout=5.0, return_adv=True)
    for addr, (device, _) in results.items():
        if device.name and BT_PRINTER_NAME.upper() in device.name.upper():
            return device.address
    raise RuntimeError(f'BLE printer "{BT_PRINTER_NAME}" not found in scan.')


async def _ble_send(address: str, data: bytes) -> None:
    from bleak import BleakClient
    async with BleakClient(address, timeout=10.0) as client:
        for i in range(0, len(data), BLE_CHUNK_SIZE):
            await client.write_gatt_char(MLDP_TX_CHAR, data[i:i + BLE_CHUNK_SIZE], response=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def open_printer() -> Usb:
    """Open and initialize via USB. Exits with a helpful message on failure."""
    try:
        p = Usb(VENDOR_ID, PRODUCT_ID, timeout=0)
        p.open()
    except Exception as e:
        print(f"ERROR: could not open USB printer — {e}")
        print()
        print("Checklist:")
        print("  • Printer plugged in via USB?")
        print("  • Removed from System Settings > Printers & Scanners?")
        print("  • libusb installed? (brew install libusb)")
        print("  • Try: sudo uv run <script>")
        sys.exit(1)

    _apply_profile(p)
    p.hw("INIT")
    return p


@contextmanager
def open_printer_ble():
    """
    Context manager that yields a Dummy printer for building ESC/POS commands,
    then sends the accumulated bytes to the printer via BLE MLDP on exit.

    Example:
        with open_printer_ble() as p:
            p.text("Hello\\n")
            p.ln(3)
    """
    p = Dummy()
    _apply_profile(p)
    p.hw("INIT")

    yield p

    data = p.output
    if not data:
        return

    try:
        address = asyncio.run(_find_ble_address())
        asyncio.run(_ble_send(address, data))
    except Exception as e:
        print(f"ERROR: BLE send failed — {e}")
        print()
        print("Checklist:")
        print("  • Printer powered on with BT enabled?")
        print("  • Paired in System Settings > Bluetooth?")
        print("  • Terminal has Bluetooth permission? (Privacy & Security → Bluetooth)")
        sys.exit(1)
