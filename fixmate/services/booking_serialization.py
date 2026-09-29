"""Convert stored booking rows into API-safe response dictionaries."""
import json


def booking_to_dict(row) -> dict:
    booking = dict(row)
    booking["emergency"] = bool(booking["emergency"])
    try:
        booking["match_factors"] = json.loads(booking.get("match_factors") or "{}")
    except (ValueError, TypeError):
        booking["match_factors"] = {}
    try:
        booking["match_features"] = json.loads(booking.get("match_features") or "{}")
    except (ValueError, TypeError):
        booking["match_features"] = {}
    return booking
