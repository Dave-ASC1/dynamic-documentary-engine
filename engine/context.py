"""
context.py
----------
Dynamic Documentary Engine — Screening Context ("Memory Triggers")

Lets the circumstances of a screening — the date, the season, the weather —
influence which artifacts surface, the way a cold, snowy December day can
bring a veteran's own December back. A person sets the context (the engine
runs offline, so it cannot look up the weather), and artifacts carry
optional context metadata saying when they happened and in what conditions.

The context never replaces juxtaposition. It works in two ways:

    1. Gentle pull — every artifact that matches the context gets a
       selection-weight boost, so it is more likely to win among the
       strongest-contrast candidates. Contrast ranking is untouched.
    2. Guaranteed memory — the best-matching A-roll or B-roll is reserved
       and placed partway through the film, so at least one triggered
       memory always surfaces when anything matches.

With no context, or nothing matching it, the engine behaves exactly as it
does without this module.

Artifact metadata (optional, in a collection index entry):

    "context": {
        "date": "1944-12-18",      # YYYY-MM-DD, YYYY-MM, or YYYY
        "season": "winter",        # inferred from the date's month if omitted
        "weather": ["snow", "cold"]
    }

Author: Oluwafemisola David Ademoye
Supporting: Omotola Ajibike Ajao
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.0.0
"""

import datetime

SEASONS = ("winter", "spring", "summer", "autumn")

# Suggested vocabulary for the console and exhibit pickers. Artifact weather
# is matched case-insensitively against whatever words are used, so a
# collection can add its own.
WEATHER_TERMS = ("clear", "cloudy", "rain", "snow", "fog", "storm", "wind", "cold", "hot")

# Points an artifact earns for each way it matches the screening context.
# Dates match on month and day only — an anniversary, whatever the year.
ANNIVERSARY_POINTS = 3     # same month and day
SAME_MONTH_POINTS = 2      # same month, different or unknown day
SEASON_POINTS = 1          # same season
WEATHER_POINTS = 2         # at least one weather word in common

# Selection weight is multiplied by (1 + WEIGHT_BOOST_PER_POINT * points),
# so an anniversary in matching weather (6 points) is four times as likely
# to be picked among the top-contrast candidates as an unmatched clip.
WEIGHT_BOOST_PER_POINT = 0.5

# The guaranteed memory is placed at a random point between these fractions
# of the film's body, so it neither opens nor closes the film.
MEMORY_WINDOW = (0.25, 0.75)

_MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
)


def season_for_month(month):
    """Meteorological season for a month (1–12), northern hemisphere.

    Args:
        month (int): Month number.

    Returns:
        str: One of SEASONS.
    """
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "autumn"


def parse_partial_date(value):
    """Parses "YYYY-MM-DD", "YYYY-MM" or "YYYY" into (year, month, day).

    Missing parts are None. Returns None for anything that isn't a valid
    date in one of those forms, so bad metadata never breaks a run.

    Args:
        value (str): The date string.

    Returns:
        tuple: (year, month, day), or None.
    """
    if not isinstance(value, str):
        return None
    parts = value.strip().split("-")
    if not 1 <= len(parts) <= 3 or not all(p.isdigit() for p in parts):
        return None
    numbers = [int(p) for p in parts] + [None] * (3 - len(parts))
    year, month, day = numbers
    try:
        if day is not None:
            datetime.date(year, month, day)
        elif month is not None and not 1 <= month <= 12:
            return None
    except ValueError:
        return None
    return year, month, day


def _artifact_context(artifact):
    """The context block of an artifact, from the index summary or the
    detailed per-artifact format."""
    return artifact.get("context") or artifact.get("content", {}).get("context") or {}


def _weather_set(value):
    if isinstance(value, str):
        value = [value]
    return {str(w).strip().lower() for w in (value or []) if str(w).strip()}


class ScreeningContext:
    """
    The circumstances of one screening: a date, a season and the weather.

    Attributes:
        date (datetime.date): The screening date.
        season (str):         The season — given explicitly, or inferred
                              from the date.
        weather (set):        Lower-case weather words; may be empty.
    """

    def __init__(self, date=None, season=None, weather=None):
        """
        Initializes a screening context.

        Args:
            date (datetime.date | str): The screening date, as a date or a
                "YYYY-MM-DD" string. None or "today" means the computer's
                own date — no internet needed.
            season (str): Overrides the season inferred from the date.
            weather (str | list): The weather, e.g. "snow" or ["rain", "cold"].

        Raises:
            ValueError: If the date or season is not recognised.
        """
        if date is None or (isinstance(date, str) and date.strip().lower() in ("", "today")):
            date = datetime.date.today()
        elif isinstance(date, str):
            parsed = parse_partial_date(date)
            if parsed is None or parsed[2] is None:
                raise ValueError(f"Context date must be YYYY-MM-DD or 'today', got {date!r}.")
            date = datetime.date(*parsed)
        self.date = date

        if season:
            season = str(season).strip().lower()
            if season not in SEASONS:
                raise ValueError(f"Context season must be one of {', '.join(SEASONS)}; got {season!r}.")
        self.season = season or season_for_month(date.month)
        self.weather = _weather_set(weather)

    @classmethod
    def from_dict(cls, data):
        """Builds a context from a request or manifest dict.

        Args:
            data (dict): Keys "date", "season", "weather" (all optional).

        Returns:
            ScreeningContext: The context.

        Raises:
            ValueError: If a value is not recognised.
        """
        data = data or {}
        return cls(
            date=data.get("date"),
            season=data.get("season") or None,
            weather=data.get("weather"),
        )

    def as_dict(self):
        """JSON-serializable form, for manifests and the UI."""
        return {
            "date": self.date.isoformat(),
            "season": self.season,
            "weather": sorted(self.weather),
            "label": self.describe(),
        }

    def describe(self):
        """Short human-readable label, e.g. "18 December · winter · snow"."""
        parts = [f"{self.date.day} {_MONTH_NAMES[self.date.month - 1]}", self.season]
        if self.weather:
            parts.append(", ".join(sorted(self.weather)))
        return " · ".join(parts)

    def match(self, artifact):
        """Scores how strongly an artifact matches this context.

        Args:
            artifact (dict): Artifact summary dictionary.

        Returns:
            tuple: (points, reasons) — points is 0 when nothing matches;
                   reasons are short phrases for the trace, e.g.
                   ["anniversary (18 December)", "weather (snow)"].
        """
        ctx = _artifact_context(artifact)
        if not ctx:
            return 0, []

        points, reasons = 0, []
        parsed = parse_partial_date(ctx.get("date"))
        month = parsed[1] if parsed else None
        day = parsed[2] if parsed else None

        if month == self.date.month:
            month_name = _MONTH_NAMES[month - 1]
            if day == self.date.day:
                points += ANNIVERSARY_POINTS
                reasons.append(f"anniversary ({day} {month_name})")
            else:
                points += SAME_MONTH_POINTS
                reasons.append(f"same month ({month_name})")

        season = str(ctx.get("season") or "").strip().lower() or (
            season_for_month(month) if month else None
        )
        if season and season == self.season:
            points += SEASON_POINTS
            reasons.append(f"season ({season})")

        shared = self.weather & _weather_set(ctx.get("weather"))
        if shared:
            points += WEATHER_POINTS
            reasons.append(f"weather ({', '.join(sorted(shared))})")

        return points, reasons
