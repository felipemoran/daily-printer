# BarList

Horizontal bars with labels and values. Compares two series as solid (current) over a thin tone bar (previous), or marks a target with a 4px line.

- Provide: `rows` (`{label, value, a, b?, solid?}` with `a`, `b` as 0–1 fractions of the widest), `legend` (`[current, previous]`), `marker` (0–1, e.g. quota), `tone` (default `tone-50`), `labelWidth`, `width` (default 384).
- Bar lengths are rounded to whole pixels.
- Set `solid: false` on rows below target so they print in the tone. Always print the value; there are no gridlines to read against.
