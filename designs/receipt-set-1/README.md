# Thermal receipt set 1

Design explorations for a 58 mm thermal receipt printer (203 dpi, 384-dot printable width, 1-bit black/white).
Open `Receipt Set 1.dc.html` in a browser. Each strip is drawn at 1 CSS px = 1 printer dot.

## Medium constraints
- Width: 384 px content (448 px strip incl. 32 px margins shown as paper)
- Pure #000 / #fff only. Greys are faked with dot patterns at 2 px or larger
- Dot gain: everything prints darker and thicker. Use the Bleed tweak to preview it

## Type
- Display: Archivo, width 62% (condensed), weight 900, 40–100 px
- Body / data: IBM Plex Mono, 500 / 700, 14–20 px (minimum 14)
- Text mode (1h): JetBrains Mono, 32 columns

## Rules and strokes
- Minimum stroke 2 px. Use 2 for list dividers (dashed), 3 for section rules, 4 for boxes and tiles, 8 for the header rule
- White-on-black text must be weight 700

## Fills (stand-ins for grey)
- Solid
- 2 px checker (about 50%)
- 2 px dot on a 4 or 6 px grid (about 35% / 15%)
- Stripes, 3 on / 4 off
- Maximum three states per chart: hollow / dithered / solid

## Recurring parts
Black header bar · condensed display ID · dashed leader rows · 2-up and 3-up stat tiles with 4 px borders ·
hollow checkboxes for pen use · reversed P1/STALE tags · hazard-tape bands · tear lines · QR slot

## Strips
1a test page · 1b tasks · 1c ticket update · 1d incident alert · 1e weekly report · 1f uptime heatmap ·
1g agenda (time-to-scale) · 1h text mode · 1i review queue · 1j habit log · 1k banner sprint board ·
1l morning briefing · 1m leaderboard · 1n focus ticket
