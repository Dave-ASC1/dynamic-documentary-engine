"""
context.py
----------
Dynamic Documentary Engine — Screening Context ("Memory Triggers")

Lets the circumstances of a screening — its date and season, or any word
someone types as a cue — decide how a film begins and where it goes next,
the way a December day can bring a veteran's own December back. The date
comes from the computer's own clock (the engine runs offline), the season
follows from it, and clips carry optional labels saying when they happened.

With memory triggers on, a film is built from its labels (see
Sequencer.generate):

    1. It opens on the clip that best matches the screening — an
       anniversary (same month and day, any year) first, then the same
       month, then the same season; a cue that matches a label counts most.
    2. The other matching clips follow, strongest match first.
    3. After that, each clip leads to one that shares a label with it — a
       person, a place, a tag, a theme or a mood — so the film follows a
       thread. Only when nothing shares a label does it cut to something
       different, by contrast, as it always has.
    4. B-roll with a mood is paired with audio of the same mood.

With memory triggers off, the engine works exactly as it does without this
module: fully random between the bookends, chosen for contrast.

Clip metadata (optional, in a collection index entry):

    "context": {
        "date": "1944-12-18",      # YYYY-MM-DD, YYYY-MM, YYYY,
                                   # or --MM-DD / --MM when the year is unknown
        "season": "winter"         # inferred from the date's month if omitted
    }

A cue (e.g. "Camp Swift") matches a clip when it is exactly equal —
ignoring capitals and surrounding punctuation — to one of its labels: the
title, a tag, a theme, a person, the place or the mood.

Author: Oluwafemisola David Ademoye
Supporting: Omotola Ajibike Ajao
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.1.0
"""

import datetime

SEASONS = ("winter", "spring", "summer", "autumn")

# Points an artifact earns for each way it matches the screening context.
# Dates match on month and day only — an anniversary, whatever the year.
ANNIVERSARY_POINTS = 3     # same month and day
SAME_MONTH_POINTS = 2      # same month, different or unknown day
SEASON_POINTS = 1          # same season
CUE_POINTS = 4             # per cue that exactly equals one of the artifact's labels

# Where a choice is still made by weight — between equally strong matches,
# for the bookends and for audio — the weight is multiplied by
# (1 + WEIGHT_BOOST_PER_POINT * points), so an anniversary in its season
# (4 points) is three times as likely to be drawn as an unmatched clip.
WEIGHT_BOOST_PER_POINT = 0.5

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
    """Parses "YYYY-MM-DD", "YYYY-MM" or "YYYY" into (year, month, day), and
    "--MM-DD" or "--MM" — a date whose year isn't known — into
    (None, month, day).

    Missing parts are None. Returns None for anything that isn't a valid
    date in one of those forms, so bad metadata never breaks a run.

    Args:
        value (str): The date string.

    Returns:
        tuple: (year, month, day), or None.
    """
    if not isinstance(value, str):
        return None
    value = value.strip()
    if value.startswith("--"):
        parts = value[2:].split("-")
        if not 1 <= len(parts) <= 2 or not all(p.isdigit() and len(p) == 2 for p in parts):
            return None
        month = int(parts[0])
        day = int(parts[1]) if len(parts) == 2 else None
        if not 1 <= month <= 12:
            return None
        if day is not None:
            try:
                datetime.date(2000, month, day)   # a leap year, so 29 February is allowed
            except ValueError:
                return None
        return None, month, day
    parts = value.split("-")
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


def normalize_date_input(value):
    """Turns a date as a person types it into the stored "YYYY[-MM[-DD]]" form,
    or "--MM[-DD]" when no year is given.

    Accepts "1944-12-18", "1944-12", "1944", "18 December 1944",
    "18 Dec 1944", "December 18, 1944", "December 1944" and "Dec 1944" —
    and, when the year isn't known, "18 December", "Dec 18" or "December".
    Matching ignores the year anyway, so a year-less date works the same.
    Slash forms like 12/18/1944 are refused: day and month order is
    ambiguous.

    Args:
        value (str): The typed date.

    Returns:
        str: The normalized date.

    Raises:
        ValueError: If the date is not recognised.
    """
    text = " ".join(str(value).replace(",", " ").split())
    if text.startswith("--"):
        if parse_partial_date(text):
            return text
        raise ValueError(f"{value!r} is not a real date.")
    iso = text.split("-")
    if all(p.isdigit() for p in iso) and len(iso[0]) == 4 and len(iso) <= 3:
        normalized = "-".join([iso[0]] + [p.zfill(2) for p in iso[1:]])
        if parse_partial_date(normalized):
            return normalized
        raise ValueError(f"{value!r} is not a real date.")

    months = {name.lower(): i + 1 for i, name in enumerate(_MONTH_NAMES)}
    months.update({name[:3].lower(): i + 1 for i, name in enumerate(_MONTH_NAMES)})
    words = text.lower().split()
    month = next((months[w.rstrip(".")] for w in words if w.rstrip(".") in months), None)
    numbers = [w for w in words if w.isdigit()]
    year = next((int(n) for n in numbers if len(n) == 4), None)
    day = next((int(n) for n in numbers if len(n) <= 2), None)
    if month is None or len(words) != 1 + (year is not None) + (day is not None):
        raise ValueError(
            f"{value!r} isn't a date the engine understands — try 18 December 1944, "
            "December 1944, 1944, 18 December or 1944-12-18."
        )
    prefix = f"{year:04d}" if year is not None else "-"
    normalized = f"{prefix}-{month:02d}" + (f"-{day:02d}" if day is not None else "")
    if not parse_partial_date(normalized):
        raise ValueError(f"{value!r} is not a real date.")
    return normalized


def normalize_label(value):
    """Lower-case, single-spaced, without surrounding punctuation — the form
    labels and cues are compared in, so "Camp Swift." matches "camp swift"."""
    return " ".join(str(value).lower().split()).strip(" .,;:!?\"'()[]")


def _artifact_labels(artifact):
    """Every label on an artifact that a cue may match exactly."""
    content = artifact.get("content", {})
    labels = set()
    for key in ("title", "mood", "geography"):
        value = artifact.get(key) or content.get(key)
        if value:
            labels.add(normalize_label(value))
    for key in ("tags", "theme", "people"):
        values = artifact.get(key) or content.get(key) or []
        if isinstance(values, str):
            values = [values]
        labels.update(normalize_label(v) for v in values)
    labels.discard("")
    return labels


def _link_label_map(artifact):
    """{compared form: label as written} for the labels that can link clips
    (see link_labels)."""
    content = artifact.get("content", {})
    labels = {}
    for key in ("tags", "theme", "people", "geography", "mood"):
        values = artifact.get(key) or content.get(key) or []
        if isinstance(values, str):
            values = [values]
        for value in values:
            if not value or str(value).startswith("color-"):
                continue
            compared = normalize_label(value)
            if compared:
                labels.setdefault(compared, " ".join(str(value).split()))
    return labels


def link_labels(artifact):
    """The labels that can connect one clip to the next in a memory film:
    its tags, themes, people, place and mood, in compared form. The title is
    left out (it names one clip), and so are the auto-detected "color-" tags,
    which describe the picture rather than what it is about."""
    return set(_link_label_map(artifact))


def shared_labels(first, second):
    """Labels two clips have in common (see link_labels), as written on the
    second clip, sorted.

    Args:
        first (dict):  A clip.
        second (dict): Another clip.

    Returns:
        list: The shared labels; empty when nothing links them.
    """
    if not first or not second:
        return []
    written = _link_label_map(second)
    common = link_labels(first) & set(written)
    return sorted((written[label] for label in common), key=str.lower)


def _cue_list(value):
    """A cue as typed ("Camp Swift, 1252nd") -> ["Camp Swift", "1252nd"]."""
    if isinstance(value, str):
        value = value.split(",")
    return [c.strip() for c in (value or []) if str(c).strip()]


def _artifact_context(artifact):
    """The context block of an artifact, from the index summary or the
    detailed per-artifact format."""
    return artifact.get("context") or artifact.get("content", {}).get("context") or {}


class ScreeningContext:
    """
    The circumstances of one screening: its date and season, plus any cues.

    Attributes:
        date (datetime.date): The screening date.
        season (str):         The season — given explicitly, or inferred
                              from the date.
        cues (list):          Words or phrases to match exactly against
                              artifact labels; may be empty.
    """

    def __init__(self, date=None, season=None, cue=None):
        """
        Initializes a screening context.

        Args:
            date (datetime.date | str): The screening date, as a date or a
                "YYYY-MM-DD" string. None or "today" means the computer's
                own date — no internet needed.
            season (str): Overrides the season inferred from the date.
            cue (str | list): Words or phrases, e.g. "Camp Swift, 1252nd".

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
        self.cues = _cue_list(cue)

    @classmethod
    def from_dict(cls, data):
        """Builds a context from a request or manifest dict.

        Args:
            data (dict): Keys "date", "season", "cue" (all optional). Any
                other key, such as the retired "weather", is ignored.

        Returns:
            ScreeningContext: The context.

        Raises:
            ValueError: If a value is not recognised.
        """
        data = data or {}
        return cls(
            date=data.get("date"),
            season=data.get("season") or None,
            cue=data.get("cue"),
        )

    def as_dict(self):
        """JSON-serializable form, for manifests and the UI."""
        return {
            "date": self.date.isoformat(),
            "season": self.season,
            "cue": list(self.cues),
            "label": self.describe(),
        }

    def describe(self):
        """Short human-readable label, e.g. "18 December · winter · “Camp Swift”"."""
        parts = [f"{self.date.day} {_MONTH_NAMES[self.date.month - 1]}", self.season]
        if self.cues:
            parts.append(", ".join(f"“{c}”" for c in self.cues))
        return " · ".join(parts)

    def match(self, artifact):
        """Scores how strongly an artifact matches this context.

        Args:
            artifact (dict): Artifact summary dictionary.

        Returns:
            tuple: (points, reasons) — points is 0 when nothing matches;
                   reasons are short phrases for the trace, e.g.
                   ["anniversary (18 December)", "season (winter)"].
        """
        points, reasons = 0, []

        if self.cues:
            labels = _artifact_labels(artifact)
            for cue in self.cues:
                if normalize_label(cue) in labels:
                    points += CUE_POINTS
                    reasons.append(f"cue (“{cue}”)")

        ctx = _artifact_context(artifact)
        if not ctx:
            return points, reasons

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

        return points, reasons
