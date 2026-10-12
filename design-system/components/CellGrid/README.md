# CellGrid

Small-multiple cells for heatmaps and calendars: hollow (`empty`), a tone (`tone` = `tone-65`, `light` = `tone-35`), solid (`solid`).

- Provide: `rows` (`{label, cells}`; `cells` an array of states or a string of `1` solid, `0` empty, `-` light, `~` tone), `cellWidth`/`cellHeight`, `gap` (default 3), `ticks`, `legend` (`[[state, label]]`), `spread` to spread cells across the width with whole-pixel gaps, `labelWidth={0}` to put labels above each row with `right` as a count.
- Whether `tone-65` stays distinct from solid in small cells is untested (TestTones).
- 24 cells of 11px fit an hourly day; 30 of 10px a month. Never more than three states.
