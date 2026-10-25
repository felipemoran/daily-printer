# Fill

A block of solid ink, a grey tone, or hazard stripes. Greys are real greys (`tone-15`, `tone-35`, `tone-50`, `tone-65`); the print pipeline dithers them.

- Provide: `pattern` (`"solid"`, `"tone-15"`, `"tone-35"`, `"tone-50"` default, `"tone-65"`, `"hazard"`), `width`, `height`, `frame` (3px ink outline).
- Also available as classes: `rp-fill-<pattern>`.
- At most three states in one chart: hollow, a tone, solid. The tone values are provisional until printed (TestTones).
- Text never sits directly on a tone; put it on a paper plate (`background: paper`, 2px 8px padding).
