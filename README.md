# Advent

Christmas countdown for FiestaBoard. No data to configure — it just works.

- **Dec 1–23**: a grid of 23 red/green tiles (8 · 7 · 8) — green tiles fill in from the left as each day passes, red tiles show what's remaining
- **Dec 24**: celebration — "IT'S CHRISTMAS EVE" centered with red/green/white confetti rows
- **Dec 25**: celebration — "MERRY CHRISTMAS!" centered with red/green/white confetti rows
- **Outside Dec 1–25**: plugin reports unavailable; nothing is shown

Confetti reshuffles each `refresh_seconds` on Dec 24–25 for subtle background noise.

## Settings

| Setting | Default | Description |
|---|---|---|
| `enabled` | `false` | Enable the plugin |
| `timezone` | `America/Chicago` | Decides when "today" starts and ends |
| `announce` | `true` | Take over the board during the advent season |
| `announce_mode` | `quad` | `quad` (four times a day), `daily`, or `hourly`. On Dec 25 the board is taken over all day regardless of this setting. |
| `announce_hour` | `8` | Start hour for `daily`/`hourly` modes (0–23) |
| `announce_end_hour` | `22` | Last hour for `hourly` mode |
| `announce_minutes` | `30` | How long each takeover window lasts |
| `takeover_priority` | `50` | Higher wins when two takeovers overlap |
| `refresh_seconds` | `300` | How often to recompute (and reshuffle confetti) |

## Variables

| Variable | Example | Description |
|---|---|---|
| `advent.is_active` | `true` | `"true"` Dec 1–25, `"false"` otherwise |
| `advent.is_christmas` | `false` | `"true"` on Dec 25 only |
| `advent.days` | `12` | Days until Christmas (0 on Dec 25, empty outside Dec 1–25) |
| `advent.message` | `MERRY CHRISTMAS!` | Empty Dec 1–23 · `IT'S CHRISTMAS EVE` on Dec 24 · `MERRY CHRISTMAS!` on Dec 25 |
| `advent.confetti` | `{63}{66}{69}…` | 22 red/green/white tiles, reshuffled each refresh |

## Conflict with Holidays plugin

Advent defaults to priority **50**; the Holidays plugin defaults to **40**. When both are enabled with takeover turned on, Advent wins the Dec 24–25 takeover by default. Adjust either plugin's `takeover_priority` if you prefer the Holidays plugin to win on those days.
