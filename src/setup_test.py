"""
setup_test.py — Phase 1 printer setup and calibration script.

Tests USB connectivity, text printing, and image printing.
Prints a width calibration pattern to determine actual dot width.

Printer: CLA58 (MPT-2 / New Dragon / Hell Fox)
  VID: 0x6868  PID: 0x0200

Run:
    uv run src/setup_test.py
"""

import sys
import usb.core
from PIL import Image, ImageDraw

VENDOR_ID = 0x6868
PRODUCT_ID = 0x0200

# Theoretical max print width in dots at 203 DPI for 48mm paper.
# We'll confirm this with the calibration image.
EXPECTED_WIDTH_DOTS = 384


# ---------------------------------------------------------------------------
# Step 0: Probe the USB device before opening via escpos
# ---------------------------------------------------------------------------

def probe_usb() -> bool:
    """Find the printer and print its USB descriptor info."""
    print("=== USB Probe ===")
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if dev is None:
        print(f"ERROR: Printer not found (VID=0x{VENDOR_ID:04X}, PID=0x{PRODUCT_ID:04X})")
        print("  - Is it plugged in?")
        print("  - Did you remove it from System Settings > Printers & Scanners?")
        return False

    print(f"Found: {dev.manufacturer or 'unknown'} / {dev.product or 'unknown'}")
    print(f"  VID: 0x{dev.idVendor:04X}  PID: 0x{dev.idProduct:04X}")
    print(f"  Bus: {dev.bus}  Address: {dev.address}")

    for cfg in dev:
        print(f"  Config {cfg.bConfigurationValue}:")
        for intf in cfg:
            print(f"    Interface {intf.bInterfaceNumber} / {intf.bAlternateSetting}")
            for ep in intf:
                direction = "IN " if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN else "OUT"
                ep_type = {
                    usb.util.ENDPOINT_TYPE_BULK: "BULK",
                    usb.util.ENDPOINT_TYPE_INTR: "INTR",
                    usb.util.ENDPOINT_TYPE_ISO: "ISO",
                    usb.util.ENDPOINT_TYPE_CTRL: "CTRL",
                }.get(usb.util.endpoint_type(ep.bmAttributes), "?")
                print(f"      EP 0x{ep.bEndpointAddress:02X}  {direction}  {ep_type}  maxPacket={ep.wMaxPacketSize}")
    return True


# ---------------------------------------------------------------------------
# Step 1: Generate a width calibration image
# ---------------------------------------------------------------------------

def make_calibration_image(width: int = EXPECTED_WIDTH_DOTS) -> Image.Image:
    """
    Creates a test image that helps determine the real printable dot width.

    Layout (top to bottom):
    - Solid black top border (8px)
    - Ruler tick marks every 32 dots with labels at 64-dot intervals
    - Solid black bottom border (8px)
    - 8px gap
    - Black fill bars at multiple widths (384, 352, 320, 288, 256 dots)
      each labelled, so you can see which one reaches the paper edge
    """
    height = 160
    img = Image.new("1", (width, height), 1)  # 1 = white in mode "1"
    draw = ImageDraw.Draw(img)

    black = 0  # in mode "1", 0 = black, 1 = white

    # Top border
    draw.rectangle([0, 0, width - 1, 7], fill=black)

    # Ruler ticks every 32 dots
    for x in range(0, width, 32):
        tick_h = 16 if x % 64 == 0 else 8
        draw.rectangle([x, 8, x + 1, 8 + tick_h], fill=black)

    # Labels at 64-dot intervals
    # PIL default font is tiny (8px), good enough for calibration
    for x in range(0, width + 1, 64):
        label = str(x)
        draw.text((max(0, x - 2), 26), label, fill=black)

    # Bottom border of ruler
    draw.rectangle([0, 40, width - 1, 47], fill=black)

    # Width bars: decreasing widths so we can see which reaches the edge
    y = 56
    for bar_width in [width, width - 32, width - 64, width - 96, width - 128]:
        if bar_width <= 0:
            continue
        draw.rectangle([0, y, bar_width - 1, y + 10], fill=black)
        draw.text((bar_width + 2 if bar_width + 40 < width else bar_width - 38, y + 1), str(bar_width), fill=black)
        y += 18

    return img


# ---------------------------------------------------------------------------
# Step 2: Open printer and run tests
# ---------------------------------------------------------------------------

def run_tests():
    from escpos.printer import Usb

    print("\n=== Opening printer via python-escpos ===")
    try:
        p = Usb(VENDOR_ID, PRODUCT_ID, timeout=0)
        p.open()
    except Exception as e:
        print(f"ERROR opening printer: {e}")
        print()
        print("Common fixes on macOS:")
        print("  1. Remove the printer from System Settings > Printers & Scanners")
        print("  2. Run with sudo: sudo uv run src/setup_test.py")
        print("  3. Make sure libusb is installed: brew install libusb")
        sys.exit(1)

    # Tell the library our actual print width so image centering works
    # and to suppress the "media.width.pixel not set" warning.
    p.profile.profile_data["media"]["width"]["pixels"] = EXPECTED_WIDTH_DOTS

    print("Printer opened successfully.\n")

    # -- Text test --
    print("--- Test: text ---")
    p.hw("INIT")
    p.set(align="center", bold=True, double_height=True, double_width=True)
    p.text("DAILY PRINTER\n")
    p.set(align="center", normal_textsize=True, bold=False)  # reset size + bold
    p.text("Setup test — Phase 1\n")
    p.ln(1)

    p.set(align="left")
    p.text("Left aligned text\n")
    p.set(align="center")
    p.text("Center aligned text\n")
    p.set(align="right")
    p.text("Right aligned text\n")
    p.ln(1)

    p.set(align="left", bold=True)
    p.text("Bold text\n")
    p.set(bold=False, underline=1)
    p.text("Underlined text\n")
    p.set(underline=0)
    p.text("Normal text\n")
    p.ln(2)

    print("  Text printed.")

    # -- Calibration image --
    print("--- Test: width calibration image ---")
    p.set(align="left")
    p.text(f"Width calibration ({EXPECTED_WIDTH_DOTS}px):\n")
    img = make_calibration_image(EXPECTED_WIDTH_DOTS)
    p.image(img, impl="bitImageRaster")
    p.ln(1)
    p.text("^ Observe: does the top border span edge to edge?\n")
    p.text("  The widest bar that fits = printable dot width.\n")
    p.ln(2)

    print("  Calibration image printed.")

    # -- QR code sanity check --
    print("--- Test: QR code ---")
    p.set(align="center")
    p.qr("https://github.com/python-escpos/python-escpos", size=4)
    p.ln(2)

    print("  QR code printed.")

    # Feed and done
    print("\n=== All tests complete ===")
    print("Observe the printout and note:")
    print("  1. Does the text look correct?")
    print("  2. Which calibration bar aligns with the paper edge?")
    print("     That number is your printable dot width.")
    print("  3. Does the QR code scan?")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ok = probe_usb()
    if not ok:
        sys.exit(1)

    print()
    run_tests()
