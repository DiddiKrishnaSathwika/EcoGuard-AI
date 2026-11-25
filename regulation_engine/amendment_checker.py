"""Staleness / amendment-awareness check.

This tool cannot confirm amendments automatically. It reports how old the
curated verification is and always states that amendment status is unverified."""
from datetime import date

STALE_AFTER_DAYS = 180


def check_amendment_status(entry, today=None):
    today = today or date.today()
    verified_on = (entry.get("verification") or {}).get("verified_on")
    age = None
    if verified_on:
        try:
            age = (today - date.fromisoformat(verified_on)).days
        except ValueError:
            age = None
    stale = age is None or age > STALE_AFTER_DAYS
    return {
        "verified_on": verified_on,
        "age_days": age,
        "stale": stale,
        "amendments_checked": False,
        "message": ("Curated summary verification is older than %d days; re-verify before relying on it." % STALE_AFTER_DAYS
                    if stale else
                    "Amendment history has not been independently checked; confirm on the official source."),
    }
