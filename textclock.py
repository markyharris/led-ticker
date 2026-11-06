# Text-form clock phrasing for the ticker (pure Python, no imports -
# unit-tested on the desktop before it ever reaches the board).
#
# Style follows Mark's example: 12:15 PM -> "Quarter after Twelve in
# the Afternoon". Minutes up to 30 are "after" the current hour, 31-59
# are "to" the next hour; 15/30/45 use Quarter/Half.

_HOURS = ["Twelve", "One", "Two", "Three", "Four", "Five", "Six",
          "Seven", "Eight", "Nine", "Ten", "Eleven"]

_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven",
         "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen",
         "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen",
         "Nineteen"]


def _minute_words(m):
    """1..29 -> 'One'..'Twenty-Nine' (15 and 30 are handled by caller)."""
    if m < 20:
        return _ONES[m]
    if m == 20:
        return "Twenty"
    return "Twenty-" + _ONES[m - 20]


def _period(hour24):
    """(name, preposition phrase) for the time of day."""
    if 5 <= hour24 < 12:
        return "in the Morning"
    if 12 <= hour24 < 17:
        return "in the Afternoon"
    if 17 <= hour24 < 21:
        return "in the Evening"
    return "at Night"


def text_time(hour24, minute):
    """Spoken-style time, e.g. text_time(12, 15) ->
    'Quarter after Twelve in the Afternoon'."""
    hour24 %= 24
    minute %= 60
    period = _period(hour24)
    hour_word = _HOURS[hour24 % 12]
    next_word = _HOURS[((hour24 % 12) + 1) % 12]

    if minute == 0:
        return "%s o'Clock %s" % (hour_word, period)
    if minute == 15:
        return "Quarter after %s %s" % (hour_word, period)
    if minute == 30:
        return "Half after %s %s" % (hour_word, period)
    if minute == 45:
        return "Quarter to %s %s" % (next_word, period)
    if minute < 30:
        return "%s after %s %s" % (_minute_words(minute), hour_word, period)
    return "%s to %s %s" % (_minute_words(60 - minute), next_word, period)


def normal_time(hour24, minute):
    """'12:15 PM' style."""
    hour24 %= 24
    suffix = "AM" if hour24 < 12 else "PM"
    h = hour24 % 12
    if h == 0:
        h = 12
    return "%d:%02d %s" % (h, minute % 60, suffix)
