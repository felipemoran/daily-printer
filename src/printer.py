"""
printer.py — Shared printer config and setup routines.

Import this module in any script that needs to talk to the printer.
"""

import sys
from escpos.printer import Usb

# ---------------------------------------------------------------------------
# Hardware constants
# ---------------------------------------------------------------------------

VENDOR_ID = 0x6868
PRODUCT_ID = 0x0200

# Print width: confirmed 384 dots by physical calibration (48 mm at 203 DPI).
PRINT_WIDTH_DOTS = 384


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def open_printer() -> Usb:
    """Open and initialize the USB printer. Exits with a helpful message on failure."""
    try:
        p = Usb(VENDOR_ID, PRODUCT_ID, timeout=0)
        p.open()
    except Exception as e:
        print(f"ERROR: could not open printer — {e}")
        print()
        print("Checklist:")
        print("  • Printer plugged in via USB?")
        print("  • Removed from System Settings > Printers & Scanners?")
        print("  • libusb installed? (brew install libusb)")
        print("  • Try: sudo uv run <script>")
        sys.exit(1)

    # Inform the library of our print width so image ops work correctly.
    p.profile.profile_data["media"]["width"]["pixels"] = PRINT_WIDTH_DOTS

    p.hw("INIT")
    return p
