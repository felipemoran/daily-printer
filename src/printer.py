"""
printer.py — Shared printer config and setup routines.

Import this module in any script that needs to talk to the printer.
Supports two transports: USB and Bluetooth (SPP).
"""

import sys
from escpos.printer import Usb, Serial

# ---------------------------------------------------------------------------
# Hardware constants
# ---------------------------------------------------------------------------

# USB
VENDOR_ID = 0x6868
PRODUCT_ID = 0x0200

# Bluetooth SPP — macOS virtual serial port after pairing
BT_PORT = "/dev/cu.MPT-II"
BT_BAUD = 9600

# Print width: confirmed 384 dots by physical calibration (48 mm at 203 DPI).
PRINT_WIDTH_DOTS = 384


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def _apply_profile(p) -> None:
    """Set known hardware parameters on the escpos profile."""
    p.profile.profile_data["media"]["width"]["pixels"] = PRINT_WIDTH_DOTS


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


def open_printer_bt() -> Serial:
    """Open and initialize via Bluetooth SPP. Exits with a helpful message on failure."""
    try:
        # dsrdtr=False: disable hardware flow control — not available over BT SPP.
        p = Serial(devfile=BT_PORT, baudrate=BT_BAUD, timeout=1, dsrdtr=False)
        p.open()
    except Exception as e:
        print(f"ERROR: could not open BT port {BT_PORT} — {e}")
        print()
        print("Checklist:")
        print("  • Printer powered on with BT enabled?")
        print("  • Paired in System Settings > Bluetooth?")
        print(f"  • Port exists? Run: ls /dev/cu.*")
        sys.exit(1)

    _apply_profile(p)
    p.hw("INIT")
    return p
