"""
context.py
----------
Dynamic Documentary Engine — Film Plan ("Memory Triggers", dates and order)

Lets the clips' labels shape a film: what it includes and in what order.
Two settings combine:

    Which clips — all of them, or only clips from a year or range of years
                  (1944, 1942–1945), from a season, or labelled with a word
                  or phrase (Camp Swift, G. Moore). Filters apply to the
                  pictures (A-roll and B-roll); audio is always free to pair.

    What order  — one of ORDERS:
        "today"     Today's date leads. The screening's date (the computer's
                    own clock) picks the opening clip — an anniversary (same
                    day and month, any year) first, then the same month,
                    then the same season. The other matching clips follow,
                    strongest first; then the other dated clips, following
                    the calendar onward from the screening date and wrapping
                    past December into January, whatever the year. After
                    that each undated clip leads to one sharing a person,
                    place, tag, theme or mood with it, and only when nothing
                    shares a label does the engine cut to something
                    different by contrast. When nothing matches today, the
                    film opens on the next date in the calendar instead.
                    See Sequencer.generate.
        "oldest"    Timeline, oldest first.
        "newest"    Timeline, newest first.
        "calendar"  Through the year, January to December, whatever the year.
        "contrast"  Random contrast — the engine as it always was.

In every order but "contrast", B-roll with a mood is paired with audio of
the same mood. With no film plan at all the engine works exactly as before.

Every date label is a stretch of time (see TimeSpan): "9 May 1950" is that
day, "December 1944" the month, "1944" the year, "winter" December to
February in any year, and "winter" with the year 1944 December 1944 to
February 1945. A season on its own is placed at the start of its months for
ordering — spring 1 March, summer 1 June, autumn 1 September, winter
1 December — so give the month when it is known.

Clip metadata (optional, in a collection index entry):

    "context": {
        "date": "1944-12-18",      # YYYY-MM-DD, YYYY-MM, YYYY,
                                   # or --MM-DD / --MM when the year is unknown
        "season": "winter"         # inferred from the date's month if omitted
    }

A label filter matches a clip when it is exactly equal — ignoring capitals
and surrounding punctuation — to one of its labels: the title, a tag, a
theme, a person, the place or the mood.

Author: Oluwafemisola David Ademoye
Supporting: Omotola Ajibike Ajao
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 2.0.0
"""

import datetime

SEASONS = ("winter", "spring", "summer", "autumn")

# The month each season starts in, for placing a season-only label in order.
SEASON_START_MONTH = {"spring": 3, "summer": 6, "autumn": 9, "winter": 12}

# What order a film is built in, with the words the pages show for each.
ORDERS = {
    "today": "Today's date leads",
    "oldest": "Timeline, oldest first",
    "newest": "Timeline, newest first",
    "calendar": "Through the year",
    "contrast": "Random contrast",
}
# The orders that place clips by their dates rather than choosing them.
DATE_ORDERS = ("oldest", "newest", "calendar")

# Points a clip earns for each way it matches the screening date, in the
# "today" order. Dates match on month and day only — an anniversary,
# whatever the year.
ANNIVERSARY_POINTS = 3     # same month and day
SAME_MONTH_POINTS = 2      # same month, different or unknown day
SEASON_POINTS = 1          # same season

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
    labels and label filters are compared in, so "Camp Swift." matches "camp swift"."""
    return " ".join(str(value).lower().split()).strip(" .,;:!?\"'()[]")


def _artifact_labels(artifact):
    """Every label on an artifact that a label filter may match exactly."""
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


def _label_list(value):
    """Labels as typed ("Camp Swift, 1252nd") -> ["Camp Swift", "1252nd"]."""
    if isinstance(value, str):
        value = value.split(",")
    return [c.strip() for c in (value or []) if str(c).strip()]


def _artifact_context(artifact):
    """The context block of an artifact, from the index summary or the
    detailed per-artifact format."""
    return artifact.get("context") or artifact.get("content", {}).get("context") or {}


def _clip_season(artifact):
    """A clip's season: the one labelled, or the one its date's month falls
    in. None when neither is known."""
    ctx = _artifact_context(artifact)
    season = str(ctx.get("season") or "").strip().lower()
    if season in SEASONS:
        return season
    parsed = parse_partial_date(ctx.get("date"))
    return season_for_month(parsed[1]) if parsed and parsed[1] else None


class TimeSpan:
    """
    The stretch of time a clip's date label covers.

    Attributes:
        year (int):       Year it starts in, or None for a label that holds
                          in any year ("winter", "26 October").
        month (int):      Month it starts in, or None for a whole year.
        day (int):        Day it starts on, or None for a whole month,
                          season or year.
        precision (str):  "day", "month", "season" or "year".
        season (str):     The season, for a season label; else None.
    """

    def __init__(self, year, month, day, precision, season=None):
        self.year, self.month, self.day = year, month, day
        self.precision, self.season = precision, season

    @classmethod
    def of(cls, artifact):
        """The span a clip's labels describe, or None when it has no date
        and no season.

        Args:
            artifact (dict): Artifact summary dictionary.

        Returns:
            TimeSpan: The span, or None.
        """
        ctx = _artifact_context(artifact)
        parsed = parse_partial_date(ctx.get("date"))
        season = str(ctx.get("season") or "").strip().lower()
        season = season if season in SEASONS else None
        year, month, day = parsed if parsed else (None, None, None)
        if day is not None:
            return cls(year, month, day, "day")
        if month is not None:
            return cls(year, month, None, "month")
        if season is not None:
            return cls(year, SEASON_START_MONTH[season], None, "season", season)
        if year is not None:
            return cls(year, None, None, "year")
        return None

    def timeline_key(self):
        """Sort key for a timeline (oldest first), or None when the span
        has no year and so no place on one."""
        if self.year is None:
            return None
        return (self.year, self.month or 0, self.day or 0)

    def calendar_key(self):
        """Sort key for "through the year" (January to December, any year),
        or None for a span that is only a year."""
        if self.month is None:
            return None
        return (self.month, self.day or 0)

    def days_ahead_key(self, today):
        """Sort key for following the calendar onward from the screening
        date, whatever the year: how many days after today this span next
        begins, wrapping past December into January. A month or season sits
        at its start, before the exact days in it — as on a timeline.

        Args:
            today (datetime.date): The screening date.

        Returns:
            tuple: (days ahead, 0 for a month or season / 1 for a day), or
                   None for a span that is only a year.
        """
        if self.month is None:
            return None
        # 2000 is a leap year, so 29 February has a place.
        start = datetime.date(2000, self.month, self.day or 1)
        ahead = (start - datetime.date(2000, today.month, today.day)).days % 366
        return ahead, 0 if self.day is None else 1

    def describe(self):
        """Plain words, e.g. "9 May 1950", "December 1944",
        "winter 1944 (December 1944 – February 1945)", "26 October"."""
        year = f" {self.year}" if self.year is not None else ""
        if self.precision == "day":
            return f"{self.day} {_MONTH_NAMES[self.month - 1]}{year}"
        if self.precision == "month":
            return f"{_MONTH_NAMES[self.month - 1]}{year}"
        if self.precision == "season":
            start = SEASON_START_MONTH[self.season]
            end = (start + 1) % 12 + 1
            if self.year is None:
                return f"{self.season} ({_MONTH_NAMES[start - 1]} – {_MONTH_NAMES[end - 1]})"
            end_year = self.year + (1 if end < start else 0)
            return (f"{self.season} {self.year} ({_MONTH_NAMES[start - 1]} {self.year} – "
                    f"{_MONTH_NAMES[end - 1]} {end_year})")
        return str(self.year)


def parse_years(value):
    """Turns "1944", "1942-1945" or "1942–1945" into (first, last).

    Args:
        value (str | int): The year or range as typed; empty means any.

    Returns:
        tuple: (first, last), or None for any year.

    Raises:
        ValueError: If it isn't a year or a range of years.
    """
    if value is None:
        return None
    text = str(value).strip().replace("–", "-").replace("—", "-").replace(" to ", "-")
    if not text:
        return None
    parts = [p.strip() for p in text.split("-")]
    if not 1 <= len(parts) <= 2 or not all(p.isdigit() and len(p) == 4 for p in parts):
        raise ValueError(f"{value!r} isn't a year — try 1944 or 1942–1945.")
    first, last = int(parts[0]), int(parts[-1])
    if first > last:
        first, last = last, first
    return first, last


class ScreeningContext:
    """
    The plan for one film: the screening's date and season, which clips may
    appear, and the order they come in. (The name dates from when this only
    held the screening's circumstances.)

    Attributes:
        date (datetime.date): The screening date.
        season (str):         The screening's season — given explicitly, or
                              inferred from the date.
        order (str):          One of ORDERS.
        years (tuple):        (first, last) year a clip's date must start
                              in, or None for any.
        only_season (str):    A season a clip must belong to, or None.
        labels (list):        Words or phrases; a clip must carry one of
                              them exactly. Empty for any clip.
    """

    def __init__(self, date=None, season=None, order=None, years=None,
                 only_season=None, labels=None):
        """
        Initializes a film plan.

        Args:
            date (datetime.date | str): The screening date, as a date or a
                "YYYY-MM-DD" string. None or "today" means the computer's
                own date — no internet needed.
            season (str): Overrides the season inferred from the date.
            order (str): One of ORDERS. Defaults to "oldest" when years are
                given and "today" otherwise.
            years (str | tuple): Only clips dated in this year or range,
                e.g. "1944" or "1942-1945".
            only_season (str): Only clips from this season.
            labels (str | list): Only clips labelled with one of these,
                e.g. "Camp Swift, 1252nd".

        Raises:
            ValueError: If a value is not recognised.
        """
        if date is None or (isinstance(date, str) and date.strip().lower() in ("", "today")):
            date = datetime.date.today()
        elif isinstance(date, str):
            parsed = parse_partial_date(date)
            if parsed is None or parsed[0] is None or parsed[2] is None:
                raise ValueError(f"Screening date must be YYYY-MM-DD or 'today', got {date!r}.")
            date = datetime.date(*parsed)
        self.date = date

        self.season = _check_season(season) or season_for_month(date.month)
        self.years = tuple(years) if isinstance(years, (tuple, list)) else parse_years(years)
        self.only_season = _check_season(only_season)
        self.labels = _label_list(labels)

        order = str(order or "").strip().lower() or ("oldest" if self.years else "today")
        if order not in ORDERS:
            raise ValueError(f"Order must be one of {', '.join(ORDERS)}; got {order!r}.")
        self.order = order

    @classmethod
    def from_dict(cls, data):
        """Builds a plan from a request or manifest dict.

        Args:
            data (dict): Keys "date", "season", "order", "years",
                "only_season", "labels" (all optional). "year" is read as
                "years" and "cue" — its earlier name — as "labels". Any other
                key, such as the retired "weather", is ignored.

        Returns:
            ScreeningContext: The plan.

        Raises:
            ValueError: If a value is not recognised.
        """
        data = data or {}
        labels = data.get("labels")
        order = data.get("order") or None
        if order == "from_today":
            # Briefly a separate order on 9 November 2026; it is now part of
            # "today", so settings saved then still work.
            order = "today"
        return cls(
            date=data.get("date"),
            season=data.get("season") or None,
            order=order,
            years=data.get("years") or data.get("year") or None,
            only_season=data.get("only_season") or None,
            labels=labels if labels is not None else data.get("cue"),
        )

    def as_dict(self):
        """JSON-serializable form, for manifests and the UI."""
        return {
            "date": self.date.isoformat(),
            "season": self.season,
            "order": self.order,
            "order_label": ORDERS[self.order],
            "years": list(self.years) if self.years else None,
            "only_season": self.only_season,
            "labels": list(self.labels),
            "filters": self.describe_filters(),
            "label": self.describe(),
        }

    def describe_filters(self):
        """Which clips may appear, in plain words, e.g. "1944 · winter ·
        “Camp Swift”" — or "" when every clip may."""
        parts = []
        if self.years:
            first, last = self.years
            parts.append(str(first) if first == last else f"{first}–{last}")
        if self.only_season:
            parts.append(self.only_season)
        if self.labels:
            parts.append(" or ".join(f"“{c}”" for c in self.labels))
        return " · ".join(parts)

    def describe(self):
        """Short human-readable label, e.g. "18 December · winter" or
        "Timeline, oldest first · 1944"."""
        if self.order == "today":
            parts = [f"{self.date.day} {_MONTH_NAMES[self.date.month - 1]}", self.season]
        else:
            parts = [ORDERS[self.order]]
        filters = self.describe_filters()
        if filters:
            parts.append(f"only {filters}")
        return " · ".join(parts)

    def has_filters(self):
        """True when only some clips may appear."""
        return bool(self.years or self.only_season or self.labels)

    def allows(self, artifact):
        """Whether a clip may appear in this film. Audio (X-roll) always
        may; the filters are about what is on screen.

        Args:
            artifact (dict): Artifact summary dictionary.

        Returns:
            bool: True if it passes every filter that is set.
        """
        if artifact.get("artifact_type") == "X-roll":
            return True
        if self.years:
            span = TimeSpan.of(artifact)
            if span is None or span.year is None:
                return False
            if not self.years[0] <= span.year <= self.years[1]:
                return False
        if self.only_season and _clip_season(artifact) != self.only_season:
            return False
        if self.labels:
            labels = _artifact_labels(artifact)
            if not any(normalize_label(c) in labels for c in self.labels):
                return False
        return True

    def match(self, artifact):
        """Scores how strongly a clip matches the screening date.

        Args:
            artifact (dict): Artifact summary dictionary.

        Returns:
            tuple: (points, reasons) — points is 0 when nothing matches;
                   reasons are short phrases for the trace, e.g.
                   ["anniversary (18 December)", "season (winter)"].
        """
        points, reasons = 0, []
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

        season = _clip_season(artifact)
        if season and season == self.season:
            points += SEASON_POINTS
            reasons.append(f"season ({season})")

        return points, reasons


def _check_season(value):
    """A season name in lower case, or None for none; raises ValueError for
    anything else."""
    if not value:
        return None
    season = str(value).strip().lower()
    if season not in SEASONS:
        raise ValueError(f"Season must be one of {', '.join(SEASONS)}; got {value!r}.")
    return season
