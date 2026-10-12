# Documentation

| Document | What it’s for |
|----------|----------------|
| [`planning-phase-01-printer-research.md`](planning-phase-01-printer-research.md) | Printer hardware, ESC/POS, USB/BLE basics |
| [`planning-print-system-architecture.md`](planning-print-system-architecture.md) | Design: home server, device protocol, job lifecycle, senders |
| [`planning-react-headless-raster-print.md`](planning-react-headless-raster-print.md) | Design: JSON → Vite/React → screenshot → raster print |
| [`feature-receipt-print-cli.md`](feature-receipt-print-cli.md) | **`receipt_print.py`**: run, flags, artifacts, quirks |
| [`feature-photo-print.md`](feature-photo-print.md) | **`photo_print.py`**: dither and print photos |
| [`feature-page-print.md`](feature-page-print.md) | **`page_print.py`**: render any page with the print profile; flags and page rules |
| [`feature-design-system.md`](feature-design-system.md) | Thermal design system: mirror of Claude Design, sync, porting, printing |
| [`feature-ticket-templates.md`](feature-ticket-templates.md) | Print templates: the 14 templates, payload, Python API, native text, adding a template, **`print_template.py`** |
| [`research-print-quality.md`](research-print-quality.md) | Every print-quality test (2026-10): results, picks, open questions, redo checklist |
| [`feature-todoist-tasks.md`](feature-todoist-tasks.md) | Todoist: API research and the integration that feeds the daily receipt and the `tasks` template |
| [`setup-bluetooth-investigation.md`](setup-bluetooth-investigation.md) | How to connect (USB for images, never connect in Settings); BLE notes |

UI quick start: [`../web/README.md`](../web/README.md).
