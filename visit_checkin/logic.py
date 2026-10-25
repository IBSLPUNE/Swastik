"""Pure helpers (no frappe import) so they can be unit-tested anywhere."""

import math

# --- visit state machine -----------------------------------------------------

HOME_DEPARTURE = "home_departure"
CUSTOMER_ARRIVAL = "customer_arrival"
CUSTOMER_DEPARTURE = "customer_departure"
CUSTOMER_ARRIVAL_OR_HOME = "customer_arrival_or_home"
HOME_ARRIVAL = "home_arrival"
DAY_ENDED = "day_ended"

# actions the server accepts while the employee is in a given state
ALLOWED_ACTIONS = {
    HOME_DEPARTURE: [HOME_DEPARTURE],
    CUSTOMER_ARRIVAL: [CUSTOMER_ARRIVAL],
    CUSTOMER_DEPARTURE: [CUSTOMER_DEPARTURE],
    CUSTOMER_ARRIVAL_OR_HOME: [CUSTOMER_ARRIVAL, HOME_ARRIVAL],
    DAY_ENDED: [],
}

STATE_LABELS = {
    HOME_DEPARTURE: "Start Day (Leaving Home)",
    CUSTOMER_ARRIVAL: "Arrived at Customer",
    CUSTOMER_DEPARTURE: "Leaving Customer",
    CUSTOMER_ARRIVAL_OR_HOME: "Next Customer / Reached Home",
    DAY_ENDED: "Day Completed",
}


def derive_state(last_row):
    """last_row: dict(milestone, status) of the employee's latest log, or None."""
    if not last_row:
        return HOME_DEPARTURE

    milestone = last_row.get("milestone")
    status = last_row.get("status")

    if milestone == "Home Departure":
        return CUSTOMER_ARRIVAL
    if milestone == "Customer Visit" and status == "Open":
        return CUSTOMER_DEPARTURE
    if milestone == "Customer Visit":
        return CUSTOMER_ARRIVAL_OR_HOME
    if milestone == "Home Arrival":
        return DAY_ENDED
    return CUSTOMER_ARRIVAL


# --- geo ----------------------------------------------------------------------

def valid_coord(value, low, high):
    """Return float(value) if it is a sane coordinate, else None."""
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < low or number > high:
        return None
    return number


def haversine_km(lat1, lon1, lat2, lon2):
    """Straight-line (great-circle) distance in km."""
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return round(radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)
