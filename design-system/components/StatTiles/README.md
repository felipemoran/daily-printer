# StatTiles

KPI tiles in a 4px-ruled grid: label, condensed value, note. One tile may be reversed to mark the headline number.

- Provide: `items` (`{label, value, note, inverted}`), `columns` (2 or 3), `valueFirst` to put the value on top (count rows like 5 OPEN), `small` for 42px values.
- 2-up for four metrics, 3-up for three counts. Values ≤ 6 characters.
