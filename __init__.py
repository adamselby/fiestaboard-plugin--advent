"""Advent plugin for FiestaBoard — Christmas countdown Dec 1–25."""

# ---------------------------------------------------------------------------
# Shared core (generated into each plugin from src/_shared_core.py; keep in sync)
# Pure standard library: no network, no third-party packages.
# ---------------------------------------------------------------------------

from __future__ import annotations

import logging
import random
import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.plugins.base import PluginBase, PluginResult, TriggerResult

logger = logging.getLogger(__name__)

def wrap(text: str, width: int) -> list[str]:
    """Greedy word wrap; '|' forces a line break; long words are hard-cut."""
    lines: list[str] = []
    for chunk in str(text).split("|"):
        current = ""
        for word in chunk.split():
            word = word[:width]
            if not current:
                current = word
            elif len(current) + 1 + len(word) <= width:
                current += " " + word
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def info_lines(rows: list[str], width: int, height: int) -> list[str]:
    """Plain centered rows; on short boards drop blank spacer rows first."""
    if height < len(rows):
        rows = [r for r in rows if r] or rows
    rows = [r[:width].center(width) for r in rows[:height]]
    return (rows + [""] * height)[:height]


# ---------------------------------------------------------------------------
# Date-plugin helpers (from src/_shared.py)
# ---------------------------------------------------------------------------

DEFAULT_TZ = "America/Chicago"
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
COLORS = {
    "red": "{63}",
    "orange": "{64}",
    "yellow": "{65}",
    "green": "{66}",
    "blue": "{67}",
    "violet": "{68}",
    "purple": "{68}",
    "white": "{69}",
}
RAINBOW = ["red", "orange", "yellow", "green", "blue", "violet"]
CONFETTI_TILES = 22  # widest single board; a Note uses the first 15
_YMD_RE = re.compile(r"^\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s*$")


def parse_ymd(raw: Any) -> date:
    """Parse YYYY-MM-DD (slashes allowed). Raises ValueError."""
    m = _YMD_RE.match(str(raw or ""))
    if not m:
        raise ValueError(f"'{raw}' is not YYYY-MM-DD")
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def fmt_date(d: date) -> str:
    return f"{MONTHS[d.month - 1]} {d.day}"


def parse_palette(raw: Any) -> list[str]:
    """'red, white, blue' → tile markers. Unknown names are ignored."""
    names = [p.strip().lower() for p in str(raw or "").replace("/", ",").split(",")]
    return [COLORS[n] for n in names if n in COLORS]


def random_confetti(tiles: int, palette: list[str] | None = None, rng: random.Random | None = None) -> str:
    """Random color tiles; never the same color twice in a row when avoidable."""
    rng = rng or random
    pal = palette or [COLORS[c] for c in RAINBOW]
    out: list[str] = []
    for _ in range(tiles):
        choices = [c for c in pal if not out or c != out[-1]] or pal
        out.append(rng.choice(choices))
    return "".join(out)


def days_phrase(days: int) -> str:
    if days == 0:
        return "TODAY"
    if days == 1:
        return "TOMORROW"
    return f"IN {days} DAYS"


def celebration_lines(message: str, width: int, height: int, palette: list[str] | None = None) -> list[str]:
    """Message centered, with confetti rows above (and below when there's room)."""
    body = wrap(message, width)[:height]
    top = [random_confetti(width, palette)] if height >= len(body) + 1 else []
    bottom = [random_confetti(width, palette)] if height > 3 and height >= len(body) + len(top) + 1 else []
    free = height - len(top) - len(bottom) - len(body)
    middle = [""] * max(free // 2, 0) + [line.center(width) for line in body]
    middle += [""] * (height - len(top) - len(bottom) - len(middle))
    return (top + middle + bottom + [""] * height)[:height]


def flanked(text: str, width: int, palette: list[str] | None = None) -> str:
    """Message centered with confetti filling both sides."""
    text = text[: max(width - 2, 0)]
    spare = width - len(text) - 2
    left = spare // 2
    return random_confetti(left, palette) + " " + text + " " + random_confetti(spare - left, palette)


def announce_settings(default_priority: int, what: str) -> dict[str, Any]:
    """Settings-schema fragment for the takeover ("announce") feature."""
    return {
        "announce": {
            "type": "boolean",
            "title": "Take Over the Board",
            "description": f"Interrupt your normal pages to show {what}, then hand the board back.",
            "default": False,
        },
        "announce_mode": {
            "type": "string",
            "title": "Takeover Style",
            "description": "Once a day for a set length, or the first few minutes of every hour.",
            "enum": ["daily", "hourly"],
            "enumNames": ["Once a day", "Start of every hour"],
            "default": "daily",
        },
        "announce_hour": {
            "type": "integer",
            "title": "Start Hour",
            "description": "0-23, local time. Once a day: when it starts. Every hour: the first hour it runs.",
            "default": 8,
            "minimum": 0,
            "maximum": 23,
        },
        "announce_end_hour": {
            "type": "integer",
            "title": "End Hour (every-hour style)",
            "description": "0-24. The takeover doesn't start in this hour or later.",
            "default": 22,
            "minimum": 1,
            "maximum": 24,
        },
        "announce_minutes": {
            "type": "integer",
            "title": "Takeover Length (minutes)",
            "description": "Once a day: up to 1440. Every hour: capped at 60.",
            "default": 30,
            "minimum": 1,
            "maximum": 1440,
        },
        "takeover_priority": {
            "type": "integer",
            "title": "Takeover Priority",
            "description": "When two takeovers overlap, the higher number wins.",
            "default": default_priority,
            "minimum": 1,
            "maximum": 99,
        },
    }


class Takeover:
    """Mixin (deliberately NOT a PluginBase subclass, so the loader finds exactly
    one plugin class per module) providing timezone handling and trigger logic.

    Subclasses set ACTIVE_FLAG (the data key that must be "true" to take over)
    and DEFAULT_PRIORITY.
    """

    ACTIVE_FLAG = "active"
    DEFAULT_PRIORITY = 50

    def _tz(self) -> ZoneInfo:
        name = self.config.get("timezone") or DEFAULT_TZ
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            return ZoneInfo(DEFAULT_TZ)

    def _now(self) -> datetime:
        return datetime.now(self._tz())

    def _validate_common(self, config: dict[str, Any]) -> list[str]:
        errors = list(self._validate_refresh_seconds(config))
        tz = config.get("timezone") or DEFAULT_TZ
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            errors.append(f"Invalid timezone: {tz}")
        if config.get("announce_mode", "daily") not in ("daily", "hourly"):
            errors.append("Takeover style must be 'daily' or 'hourly'")
        if config.get("announce_mode") == "hourly" and int(config.get("announce_end_hour", 22)) <= int(
            config.get("announce_hour", 8)
        ):
            errors.append("End hour must be after the start hour")
        return errors

    def announce_window(self, now: datetime) -> tuple[datetime, str] | None:
        """(window end, stable window key) if a takeover window is open now."""
        cfg = self.config
        if not cfg.get("announce"):
            return None
        start_hour = int(cfg.get("announce_hour", 8))
        minutes = int(cfg.get("announce_minutes", 30))
        if cfg.get("announce_mode") == "hourly":
            end_hour = int(cfg.get("announce_end_hour", 22))
            if not (start_hour <= now.hour < end_hour):
                return None
            start = now.replace(minute=0, second=0, microsecond=0)
            end = start + timedelta(minutes=min(minutes, 60))
            key = now.strftime("%Y-%m-%d-%H")
        else:
            start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
            end = start + timedelta(minutes=minutes)
            key = now.strftime("%Y-%m-%d")
        if start <= now < end:
            return end, key
        return None

    def check_triggers(self) -> list[TriggerResult]:
        now = self._now()
        window = self.announce_window(now)
        if window is None:
            return []
        # Use the cached fetch (refreshed every refresh_seconds). Recomputing
        # here would reshuffle confetti on every engine tick and re-flap the board.
        result = self.get_data()
        if not result.available or not result.data or result.data.get(self.ACTIVE_FLAG) != "true":
            return []
        end, key = window
        return [
            TriggerResult(
                triggered=True,
                # One id per window: re-returning it each tick just refreshes it,
                # and a manual page change suppresses it for the rest of the window.
                trigger_id=f"{self.plugin_id}_{key}",
                priority=int(self.config.get("takeover_priority", self.DEFAULT_PRIORITY)),
                duration_seconds=max(int((end - now).total_seconds()), 30),
                data=result.data,
                formatted_lines=result.formatted_lines,
                message=result.data.get("message") or None,
            )
        ]

    def _size(self) -> tuple[int, int]:
        board = self.board
        return (board.width if board else 22), (board.height if board else 6)

    def get_formatted_display(self) -> list[str] | None:
        result = self.fetch_data()
        if not result.available or not result.data:
            return None
        return result.formatted_lines


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------

CHRISTMAS_PALETTE = [COLORS["red"], COLORS["green"], COLORS["white"]]


class AdventPlugin(Takeover, PluginBase):
    """Christmas countdown, Dec 1–25."""

    ACTIVE_FLAG = "is_active"
    DEFAULT_PRIORITY = 50

    @property
    def plugin_id(self) -> str:
        return "advent"

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = self._validate_common(config)
        # _validate_common only knows daily/hourly; remove its mode error and re-check with quad
        errors = [e for e in errors if "Takeover style" not in e]
        mode = config.get("announce_mode", "quad")
        if mode not in ("daily", "hourly", "quad"):
            errors.append("Takeover style must be 'daily', 'hourly', or 'quad'")
        return errors

    def announce_window(self, now: datetime) -> tuple[datetime, str] | None:
        if not self.config.get("announce"):
            return None
        # Christmas Day: take over the entire day
        if now.month == 12 and now.day == 25:
            midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            return midnight, now.strftime("%Y-%m-%d")
        # Quad mode: fire at 6am, noon, 6pm, midnight
        if self.config.get("announce_mode", "quad") == "quad":
            if now.hour not in (0, 6, 12, 18):
                return None
            minutes = int(self.config.get("announce_minutes", 30))
            start = now.replace(minute=0, second=0, microsecond=0)
            end = start + timedelta(minutes=min(minutes, 60))
            key = now.strftime("%Y-%m-%d-%H")
            if start <= now < end:
                return end, key
            return None
        return super().announce_window(now)

    def compute(self, today: date) -> dict[str, Any]:
        if today.month == 12 and 1 <= today.day <= 25:
            christmas = date(today.year, 12, 25)
            days = (christmas - today).days
            is_christmas = today.day == 25
            if is_christmas:
                message = "MERRY CHRISTMAS!"
            elif days == 1:
                message = "IT'S CHRISTMAS EVE"
            else:
                message = ""
            return {
                "is_active": "true",
                "is_christmas": "true" if is_christmas else "false",
                "days": str(days),
                "message": message,
                "confetti": random_confetti(CONFETTI_TILES, CHRISTMAS_PALETTE),
            }
        return {
            "is_active": "false",
            "is_christmas": "false",
            "days": "",
            "message": "",
            "confetti": "",
        }

    def fetch_data(self) -> PluginResult:
        try:
            data = self.compute(self._now().date())
            if data["is_active"] != "true":
                return PluginResult(available=False, error="Outside Dec 1–25")
            return PluginResult(available=True, data=data, formatted_lines=self._format_display(data))
        except Exception as e:  # pragma: no cover - defensive
            logger.exception("Error computing advent")
            return PluginResult(available=False, error=str(e))

    def _advent_grid(self, elapsed: int, width: int, height: int) -> list[str]:
        """Grid of 23 tiles (Dec 1–23). Green = past, red = remaining.
        Layout: rows of 8, 7, 8 tiles, each centered in the available width.
        """
        row_counts = [8, 7, 8]
        grid_rows = []
        day = 0
        for count in row_counts:
            pad = (width - count) // 2
            right_pad = width - count - pad
            row = "".join(
                COLORS["green"] if day + i < elapsed else COLORS["red"]
                for i in range(count)
            )
            grid_rows.append(" " * pad + row + " " * right_pad)
            day += count
        top_pad = max((height - len(grid_rows)) // 2, 0)
        result = [""] * top_pad + grid_rows + [""] * height
        return result[:height]

    def _format_display(self, data: dict[str, Any]) -> list[str]:
        width, height = self._size()
        if data["is_christmas"] == "true":
            return celebration_lines("MERRY CHRISTMAS!", width, height, CHRISTMAS_PALETTE)
        days = int(data["days"])
        if days == 1:
            return celebration_lines("IT'S CHRISTMAS EVE", width, height, CHRISTMAS_PALETTE)
        # Dec 1–23: advent grid
        # elapsed = today.day = tiles to show green (Dec 1 → 1 green, Dec 23 → 23 green)
        elapsed = 25 - days
        return self._advent_grid(elapsed, width, height)


Plugin = AdventPlugin
