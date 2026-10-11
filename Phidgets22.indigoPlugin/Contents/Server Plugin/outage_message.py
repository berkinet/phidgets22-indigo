"""Readable outage timing."""


def outage_duration(seconds):
    return "%02d:%02d hours/minutes" % divmod(max(0, int(seconds)) // 60, 60)


def reminder_cadence(seconds, first_daily=False):
    if seconds < 86400:
        return ""
    label = "First daily reminder" if first_daily else "Daily reminder"
    return label + "; subsequent reminders every 24 hours or the longer configured interval. "
