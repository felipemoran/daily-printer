"""
print_test.py — Basic print test. Auto-selects USB or BLE.

Run:
    uv run python src/print_test.py
"""

from printer import open_printer

with open_printer() as p:
    p.set(align="center", bold=True)
    p.text("Print test\n")
    p.set(align="left", bold=False)
    p.text("Hello from daily-printer\n")
    p.ln(3)

print("Done.")
