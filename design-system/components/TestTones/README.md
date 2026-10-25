# TestTones

Paper test for the grey tones after dithering and dot gain (item 9 of the To verify list).

- A ramp of 10% steps, the four `tone-*` tokens as large blocks and as heatmap-sized cells (11 × 22 and 10 × 20) between empty and solid, and text on a paper plate over `tone-50`.
- Look for: which steps are distinguishable on paper; whether `tone-15` survives (Atkinson discards part of the error, so light greys may print near-white); whether `tone-65` stays distinct from solid in small cells; whether 3 states (empty / tone / solid) read at a glance.
- Result decides the `tone-*` values.
