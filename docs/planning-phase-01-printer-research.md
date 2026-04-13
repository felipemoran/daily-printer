# Daily Printer — Planning Document

## 1. Printer Identification

Your printer is a **generic OEM 58mm thermal receipt printer**, sold under several brand names
(New Dragon, Hell Fox, and likely many others). It is physically and functionally identical to
dozens of models on the market that share the same mainboard and firmware.

| Field | Value |
|---|---|
| Marketed model | MPT-2 |
| USB product string | **CLA58** |
| USB vendor string | **TECH** |
| USB Vendor ID | **0x6868** (decimal 26728) |
| USB Product ID | **0x0200** (decimal 512) |
| Paper width | 58 mm |
| Print width | 48 mm / **384 dots** (confirmed by calibration) |
| Resolution | 203 DPI (8 dots/mm) |
| Print speed | up to 120 mm/s |
| Interfaces | USB (present) + Bluetooth (present) |
| Protocol | **ESC/POS** |

### What was `%!PS-Adobe-3.0 Query`?

When you plugged in the printer, macOS / CUPS automatically detected the new USB device and
sent a standard PostScript conformance probe (`%!PS-Adobe-3.0 Query`) to ask whether it speaks
PostScript. The printer does **not** speak PostScript — that output was macOS talking *at* the
printer, not the printer responding. CUPS then likely added it as a generic PostScript queue,
which is completely wrong for ESC/POS.

**Action item**: remove the CUPS printer from System Settings > Printers & Scanners. For this
project you will talk to the printer directly over USB, bypassing the macOS print system
entirely.

---

## 2. The Protocol: ESC/POS

ESC/POS (Epson Standard Code for Point of Sale) is a command language invented by Epson in the
1980s and now the de-facto standard for thermal receipt printers worldwide. Generic Chinese
printers implement a subset of the Epson spec.

Key facts:
- **Binary, not text**: commands are raw byte sequences sent directly to the USB device.
- **No driver needed**: you write bytes, the printer executes them.
- **Stateful**: each print session is independent; you initialize, send content, then cut/feed.

Commonly used commands for this printer:

| Purpose | ESC/POS command (hex) |
|---|---|
| Initialize printer | `1B 40` |
| Print & feed line | `0A` |
| Bold on/off | `1B 45 01` / `1B 45 00` |
| Font size | `1D 21 nn` |
| Align (L/C/R) | `1B 61 00/01/02` |
| Raster bitmap | `1D 76 30 …` |
| QR Code | `1D 28 6B …` (series of sub-commands) |
| 1D barcode | `1D 6B type len data` |
| Feed N lines | `1B 64 nn` |
| Full cut | `1D 56 00` (if cutter present) |

---

## 3. Interface Options

### 3a. Python — `python-escpos` (recommended starting point)

The mature, battle-tested ESC/POS library for Python. Active since 2012, current version **3.1**.

**Install:**
```bash
brew install libusb          # required by pyusb on macOS
pip install python-escpos[usb]
```

**Minimal usage:**
```python
from escpos.printer import Usb

p = Usb(0x6868, 0x0200, timeout=0)
p.init()
p.set(align='center', bold=True)
p.text("Daily Ticket\n")
p.ln(2)
p.cut()
```

**Key features:**
- `p.text()` / `p.textln()` — plain text
- `p.set(align, bold, width, height, ...)` — text styling
- `p.image("path.png")` — bitmap printing via Pillow (handles dithering/resizing to 384px wide)
- `p.qr("content")` — QR code via the `qrcode` library
- `p.barcode(code, type)` — 1D barcodes (EAN, CODE128, etc.)
- `p.cut()` — paper cut command

**Mac gotcha — USB access:**

macOS may have the printer claimed by its own USB stack (or CUPS). Two mitigations:

1. Remove the printer from System Settings first (most reliable).
2. If you still get a `USBError: Access denied`, run your script with `sudo` once to verify
   the connection works, then set up a libusb udev-equivalent:
   - Create `/etc/sudoers.d/usb-printer` granting your user passwordless access, **or**
   - Wrap device open with `in_ep`/`out_ep` parameters if the default endpoint detection fails.

**Finding endpoints** (if needed):
```python
import usb.core
dev = usb.core.find(idVendor=0x6868, idProduct=0x0200)
print(dev)   # shows all interfaces and endpoints
```

**Strengths for this project:**
- Excellent for scripting: parse email → generate ticket → print
- Rich image support (great for bitmap layouts)
- Good documentation and community
- Easy to run as a cron job or daemon

---

### 3b. Node.js / TypeScript — `@node-escpos` ecosystem

A modular, TypeScript-first ESC/POS library. Latest core release: `@node-escpos/core@0.5.0`
(Jan 2024).

**Install:**
```bash
npm install @node-escpos/core @node-escpos/usb-adapter
```

**Minimal usage:**
```typescript
import { Printer } from "@node-escpos/core";
import USB from "@node-escpos/usb-adapter";

const device = new USB(0x6868, 0x0200);
device.open(async (err) => {
  if (err) throw err;
  const printer = new Printer(device, { encoding: "UTF-8" });
  printer
    .align("ct")
    .style("b")
    .text("Daily Ticket")
    .feed(2)
    .cut()
    .close();
});
```

**Key packages:**

| Package | Purpose |
|---|---|
| `@node-escpos/core` | Printer commands (text, image, QR, barcode) |
| `@node-escpos/usb-adapter` | USB connectivity via `usb` npm package |
| `@node-escpos/network-adapter` | TCP/IP if you ever need it |
| `node-thermal-printer` | Alternative — single package, broader compat, v4.6.0 |
| `escpos-buffer` | Buffer-only approach; works with WebUSB in Chrome too |

**Mac gotcha:** The `usb` npm package uses `libusb` natively. Same USB access considerations
as Python apply.

**Strengths for this project:**
- Natural fit if you want a small web UI (Express/Next.js) to trigger prints
- TypeScript gives you good autocomplete and type safety
- `escpos-buffer` is interesting if you want to generate print buffers without a live device
  connected (good for testing)

---

## 4. Recommendation

For a **pet project** focused on printing personal tickets, email digests, and to-dos:

**Start with Python.**

Rationale:
- `python-escpos` is more mature and better documented than the Node equivalents.
- Python excels at the text-processing tasks you need (email parsing with `imaplib`/`email`,
  task APIs, formatting).
- Fewer moving parts — one script, one library, one process.
- Pillow makes bitmap generation (e.g., a nicely laid-out "daily brief" image) trivial.
- Easy to run as a background service on macOS with `launchd`.

**Consider TypeScript/Node only if** you want a web dashboard or REST API for triggering prints
from other devices (phone, browser, etc.). In that case a hybrid works well:
- Node/Next.js HTTP server receives print requests
- Calls a Python subprocess or a shared ESC/POS buffer library

---

## 5. Immediate Next Steps

### Step 1: Confirm USB access
```bash
# Install libusb
brew install libusb

# Install python-escpos
pip install python-escpos[usb]

# Quick device check
python3 -c "
import usb.core
dev = usb.core.find(idVendor=0x6868, idProduct=0x0200)
print('Found:', dev)
"
```

### Step 2: Remove CUPS printer
Go to **System Settings → Printers & Scanners**, find the printer (may be named "CLA58" or
"Generic PostScript"), and remove it. This releases the USB device.

### Step 3: First print test
```python
from escpos.printer import Usb

p = Usb(0x6868, 0x0200, timeout=0)
p.init()
p.text("Hello, world!\n")
p.ln(3)
p.cut()
```

### Step 4: Determine paper width in dots
At 203 DPI, 48mm print width = **384 dots**. This is the max image width you can send.
When printing images, resize to exactly 384px wide before sending.

### Step 5: Explore Bluetooth (optional)
The printer has Bluetooth 4.0. On macOS, once paired, it appears as a serial port under
`/dev/cu.CLA58-...` or similar. `python-escpos` has a `Serial` class for this. USB is simpler
to start with.

---

## 6. Useful References

- [python-escpos GitHub](https://github.com/python-escpos/python-escpos)
- [python-escpos docs](https://python-escpos.readthedocs.io/)
- [@node-escpos driver](https://github.com/node-escpos/driver)
- [node-thermal-printer npm](https://www.npmjs.com/package/node-thermal-printer)
- [ESC/POS printer capability database](https://github.com/receipt-print-hq/escpos-printer-db)
- [Epson ESC/POS command reference](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/index.html)
- [Star Micronics ESC/POS spec PDF](https://www.starmicronics.com/support/Mannualfolder/escpos_cm_en.pdf)
