"""
Whitelisted API used by the Visit Check-in PWA.

Endpoints  (all under /api/method/visit_checkin.api.<name>):
    get_csrf_token                 (guest allowed - used as the login probe)
    get_visit_status
    submit_visit_milestone
    get_today_visits
    get_employee_attendance_calendar
    get_employee_last_checkins
"""

import base64
from datetime import date, datetime, timedelta, timezone

import frappe
import pytz
import requests
from frappe import _
from frappe.utils import cint, get_last_day, getdate, now_datetime
from frappe.utils.file_manager import save_file

from visit_checkin.logic import (
    ALLOWED_ACTIONS,
    CUSTOMER_ARRIVAL,
    CUSTOMER_DEPARTURE,
    HOME_ARRIVAL,
    HOME_DEPARTURE,
    STATE_LABELS,
    derive_state,
    haversine_km,
    valid_coord,
)

DOCTYPE = "Customer Visit Log"
MAX_PHOTO_BYTES = 8 * 1024 * 1024


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------

def _get_employee():
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Please log in"), frappe.AuthenticationError)

    employee = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
    if not employee:
        frappe.throw(_("No active Employee is linked to your user ({0})").format(user))
    return employee


def _system_tz():
    return frappe.db.get_single_value("System Settings", "time_zone") or "Asia/Kolkata"


def _resolve_time(client_time):
    """
    Returns (datetime_in_system_tz_naive, used_client_time: bool, note: str).

    client_time is an ISO-8601 string captured on the device when the photo was
    taken. It is only sent for entries that were queued while offline. It is
    ignored (server time used) if it is unparsable, in the future, or too old.
    """
    now = now_datetime()

    if not client_time:
        return now, False, ""

    try:
        parsed = datetime.fromisoformat(str(client_time).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            local = parsed
        else:
            utc_naive = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            local = (
                pytz.utc.localize(utc_naive)
                .astimezone(pytz.timezone(_system_tz()))
                .replace(tzinfo=None)
            )
    except Exception:
        return now, False, _("Device time was unreadable ({0}); server time used.").format(client_time)

    max_age_days = cint(frappe.conf.get("visit_checkin_max_offline_days")) or 3

    if local > now + timedelta(minutes=5):
        return now, False, _("Device time was in the future ({0}); server time used.").format(client_time)
    if local < now - timedelta(days=max_age_days):
        return now, False, _("Device time was older than {0} days ({1}); server time used.").format(
            max_age_days, client_time
        )

    return local, True, ""


def _fmt_time(value):
    return get_datetime_safe(value).strftime("%I:%M %p") if value else ""


def get_datetime_safe(value):
    if isinstance(value, datetime):
        return value
    return frappe.utils.get_datetime(value)


def _decode_photo(photo):
    if not photo:
        if frappe.conf.get("visit_checkin_photo_required", 1):
            frappe.throw(_("A live photo is required for check-in"))
        return None

    data = photo.split(",", 1)[1] if photo.startswith("data:") else photo
    try:
        raw = base64.b64decode(data)
    except Exception:
        frappe.throw(_("Invalid photo data"))

    if len(raw) > MAX_PHOTO_BYTES:
        frappe.throw(_("Photo is too large"))
    if not raw.startswith(b"\xff\xd8"):
        frappe.throw(_("Photo must be a JPEG image"))
    return raw


def _attach_photo(docname, fieldname, raw):
    if not raw:
        return
    file_doc = save_file(
        f"{fieldname}_{docname}.jpg", raw, DOCTYPE, docname, is_private=1, df=fieldname
    )
    frappe.db.set_value(DOCTYPE, docname, fieldname, file_doc.file_url, update_modified=False)


def _get_state(employee, visit_date):
    """Returns (state_key, row_dict_or_None). Handles visits that cross midnight."""
    open_row = frappe.db.get_value(
        DOCTYPE,
        {
            "employee": employee,
            "milestone": "Customer Visit",
            "status": "Open",
            "visit_date": [">=", getdate(visit_date) - timedelta(days=1)],
        },
        ["name", "milestone", "status"],
        as_dict=True,
        order_by="creation desc",
    )
    if open_row:
        return derive_state(open_row), open_row

    rows = frappe.get_all(
        DOCTYPE,
        filters={"employee": employee, "visit_date": visit_date},
        fields=["name", "milestone", "status"],
        order_by="creation desc",
        limit_page_length=1,
    )
    last = rows[0] if rows else None
    return derive_state(last), last


def _get_origin(employee, visit_date):
    """Where does 'distance from home' start?  Employee master first, else day-start location."""
    lat, lng = frappe.db.get_value(
        "Employee", employee, ["custom_home_latitude", "custom_home_longitude"]
    ) or (None, None)
    if lat and lng:
        return float(lat), float(lng), "Employee Home"

    row = frappe.db.get_value(
        DOCTYPE,
        {"employee": employee, "visit_date": visit_date, "milestone": "Home Departure"},
        ["departure_latitude", "departure_longitude"],
        order_by="creation desc",
    )
    if row and row[0] and row[1]:
        return float(row[0]), float(row[1]), "Day Start Location"

    return None


def _distance(origin_lat, origin_lng, dest_lat, dest_lng):
    """Real road distance via Google Distance Matrix if a key is configured, else straight-line."""
    key = frappe.conf.get("google_maps_api_key")
    if key:
        try:
            resp = requests.get(
                "https://maps.googleapis.com/maps/api/distancematrix/json",
                params={
                    "origins": f"{origin_lat},{origin_lng}",
                    "destinations": f"{dest_lat},{dest_lng}",
                    "units": "metric",
                    "key": key,
                },
                timeout=6,
            )
            data = resp.json()
            element = data["rows"][0]["elements"][0]
            if data.get("status") == "OK" and element.get("status") == "OK":
                return round(element["distance"]["value"] / 1000, 2), "Google Road"
        except Exception:
            frappe.log_error(
                title="Visit Checkin: Google Distance Matrix failed",
                message=frappe.get_traceback(),
            )

    return haversine_km(origin_lat, origin_lng, dest_lat, dest_lng), "Straight-line"


def _create_employee_checkin(employee, log_type, when, lat, lng):
    """Keeps standard HRMS attendance in sync (Home Departure = IN, Home Arrival = OUT)."""
    try:
        meta = frappe.get_meta("Employee Checkin")
        values = {
            "doctype": "Employee Checkin",
            "employee": employee,
            "log_type": log_type,
            "time": when,
        }
        if meta.has_field("device_id"):
            values["device_id"] = "Visit Checkin PWA"
        if lat is not None and lng is not None:
            if meta.has_field("latitude"):
                values["latitude"] = lat
            if meta.has_field("longitude"):
                values["longitude"] = lng
        frappe.get_doc(values).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(
            title="Visit Checkin: Employee Checkin creation failed",
            message=frappe.get_traceback(),
        )


# ----------------------------------------------------------------------------
# endpoints
# ----------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def get_csrf_token():
    """Used by the standalone PWA (it is a static page, so no server-rendered token)."""
    if frappe.session.user == "Guest":
        return {"error": "Not logged in"}

    from frappe.sessions import get_csrf_token as _frappe_csrf

    return {"csrf_token": _frappe_csrf(), "user": frappe.session.user}


@frappe.whitelist()
def get_visit_status():
    employee = _get_employee()
    state, _row = _get_state(employee, getdate())
    return {
        "action": state,
        "label": STATE_LABELS[state],
        "needs_customer": {CUSTOMER_ARRIVAL: True, "customer_arrival_or_home": "optional"}.get(state, False),
        "employee": employee,
    }


@frappe.whitelist()
def submit_visit_milestone(
    action=None,
    latitude=None,
    longitude=None,
    photo=None,
    customer_name=None,
    client_time=None,
    client_ref=None,
):
    employee = _get_employee()

    valid_actions = (HOME_DEPARTURE, CUSTOMER_ARRIVAL, CUSTOMER_DEPARTURE, HOME_ARRIVAL)
    if action not in valid_actions:
        frappe.throw(_("Invalid action"))

    # Idempotency: an offline entry may be re-sent if the first response was lost.
    if client_ref:
        existing = frappe.db.get_value(DOCTYPE, {"client_ref": client_ref}, "name") or frappe.db.get_value(
            DOCTYPE, {"departure_ref": client_ref}, "name"
        )
        if existing:
            return {"ok": 1, "duplicate": 1, "name": existing}

    when, used_client_time, note = _resolve_time(client_time)
    visit_date = when.date()

    state, state_row = _get_state(employee, visit_date)
    if action not in ALLOWED_ACTIONS.get(state, []):
        frappe.throw(
            _("This step is not allowed right now. Current step: {0}").format(STATE_LABELS.get(state, state))
        )

    lat = valid_coord(latitude, -90, 90)
    lng = valid_coord(longitude, -180, 180)
    if lat is None or lng is None:
        lat = lng = None

    customer_name = (customer_name or "").strip()
    if action == CUSTOMER_ARRIVAL and not customer_name:
        frappe.throw(_("Customer name is required"))

    photo_raw = _decode_photo(photo)

    common = {
        "is_offline_entry": 1 if used_client_time else 0,
        "synced_at": now_datetime() if used_client_time else None,
        "remarks": note or None,
    }

    # ---- Home Departure -------------------------------------------------
    if action == HOME_DEPARTURE:
        doc = frappe.get_doc(
            {
                "doctype": DOCTYPE,
                "employee": employee,
                "visit_date": visit_date,
                "milestone": "Home Departure",
                "status": "Completed",
                "departure_time": when,
                "departure_latitude": lat,
                "departure_longitude": lng,
                "client_ref": client_ref,
                **common,
            }
        ).insert(ignore_permissions=True)
        _attach_photo(doc.name, "departure_photo", photo_raw)
        _create_employee_checkin(employee, "IN", when, lat, lng)

    # ---- Customer arrival -----------------------------------------------
    elif action == CUSTOMER_ARRIVAL:
        values = {
            "doctype": DOCTYPE,
            "employee": employee,
            "visit_date": visit_date,
            "milestone": "Customer Visit",
            "customer_name": customer_name,
            "status": "Open",
            "arrival_time": when,
            "arrival_latitude": lat,
            "arrival_longitude": lng,
            "client_ref": client_ref,
            **common,
        }
        origin = _get_origin(employee, visit_date) if lat is not None else None
        if origin:
            km, source = _distance(origin[0], origin[1], lat, lng)
            values.update(
                {"distance_from_home_km": km, "distance_source": source, "origin_type": origin[2]}
            )
        doc = frappe.get_doc(values).insert(ignore_permissions=True)
        _attach_photo(doc.name, "arrival_photo", photo_raw)

    # ---- Customer departure ---------------------------------------------
    elif action == CUSTOMER_DEPARTURE:
        doc = frappe.get_doc(DOCTYPE, state_row["name"])
        doc.departure_time = when
        doc.departure_latitude = lat
        doc.departure_longitude = lng
        doc.status = "Completed"
        doc.departure_ref = client_ref
        if used_client_time:
            doc.is_offline_entry = 1
            doc.synced_at = now_datetime()
        if note:
            doc.remarks = ((doc.remarks + "\n") if doc.remarks else "") + note
        doc.save(ignore_permissions=True)  # controller computes time_spent_minutes
        _attach_photo(doc.name, "departure_photo", photo_raw)

    # ---- Home arrival ---------------------------------------------------
    else:
        doc = frappe.get_doc(
            {
                "doctype": DOCTYPE,
                "employee": employee,
                "visit_date": visit_date,
                "milestone": "Home Arrival",
                "status": "Completed",
                "arrival_time": when,
                "arrival_latitude": lat,
                "arrival_longitude": lng,
                "client_ref": client_ref,
                **common,
            }
        ).insert(ignore_permissions=True)
        _attach_photo(doc.name, "arrival_photo", photo_raw)
        _create_employee_checkin(employee, "OUT", when, lat, lng)

    return {
        "ok": 1,
        "name": doc.name,
        "location_missing": lat is None,
        "distance_km": doc.get("distance_from_home_km"),
        "distance_source": doc.get("distance_source"),
    }


@frappe.whitelist()
def get_today_visits():
    employee = _get_employee()
    rows = frappe.get_all(
        DOCTYPE,
        filters={"employee": employee, "visit_date": getdate()},
        fields=[
            "name",
            "milestone",
            "customer_name",
            "status",
            "arrival_time",
            "departure_time",
            "time_spent_minutes",
            "distance_from_home_km",
            "distance_source",
        ],
        order_by="creation asc",
    )
    for row in rows:
        row["arrival_time"] = _fmt_time(row.get("arrival_time"))
        row["departure_time"] = _fmt_time(row.get("departure_time"))
    return {"visits": rows}


@frappe.whitelist()
def get_employee_last_checkins():
    employee = _get_employee()
    rows = frappe.get_all(
        "Employee Checkin",
        filters={"employee": employee},
        fields=["log_type", "time"],
        order_by="time desc",
        limit_page_length=20,
    )
    return {
        "checkins": [
            {"log_type": r.log_type, "time": get_datetime_safe(r.time).strftime("%d %b, %I:%M %p")}
            for r in rows
        ]
    }


@frappe.whitelist()
def get_employee_attendance_calendar(year=None, month=None):
    employee = _get_employee()

    today = getdate()
    year = cint(year) or today.year
    month = cint(month) or today.month
    if not 1 <= month <= 12:
        frappe.throw(_("Invalid month"))

    start = date(year, month, 1)
    end = get_last_day(start)

    emp = frappe.db.get_value("Employee", employee, ["employee_name"], as_dict=True)

    # ---- attendance summary ----
    counts = {"Present": 0, "Half Day": 0, "Absent": 0, "On Leave": 0}
    day_status = {}
    attendance = frappe.get_all(
        "Attendance",
        filters={"employee": employee, "attendance_date": ["between", [start, end]], "docstatus": 1},
        fields=["attendance_date", "status"],
    )
    for rec in attendance:
        status = "Present" if rec.status == "Work From Home" else rec.status
        day_status[str(rec.attendance_date)] = status
        if status in counts:
            counts[status] += 1

    # ---- check-ins grouped by date ----
    checkins_by_date = {}
    checkins = frappe.get_all(
        "Employee Checkin",
        filters={
            "employee": employee,
            "time": ["between", [f"{start} 00:00:00", f"{end} 23:59:59"]],
        },
        fields=["log_type", "time"],
        order_by="time asc",
    )
    for c in checkins:
        when = get_datetime_safe(c.time)
        checkins_by_date.setdefault(when.strftime("%Y-%m-%d"), []).append(
            {"log_type": c.log_type, "time": when.strftime("%I:%M %p")}
        )

    return {
        "employee_name": emp.employee_name,
        "year": year,
        "month": month,
        "present_count": counts["Present"],
        "half_day_count": counts["Half Day"],
        "absent_count": counts["Absent"],
        "leave_count": counts["On Leave"],
        "day_status": day_status,
        "checkins_by_date": checkins_by_date,
        "leave_balance": _leave_balance(employee),
        "holidays": _holidays(employee, start, end),
    }


def _leave_balance(employee):
    try:
        from hrms.hr.doctype.leave_application.leave_application import get_leave_details

        details = get_leave_details(employee, frappe.utils.nowdate())
        return [
            {"leave_type": leave_type, "balance": values.get("remaining_leaves")}
            for leave_type, values in (details.get("leave_allocation") or {}).items()
        ]
    except Exception:
        frappe.log_error(title="Visit Checkin: leave balance failed", message=frappe.get_traceback())
        return []


def _holidays(employee, start, end):
    try:
        from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

        holiday_list = get_holiday_list_for_employee(employee, raise_exception=False)
    except Exception:
        holiday_list = frappe.db.get_value("Employee", employee, "holiday_list")

    if not holiday_list:
        return []

    rows = frappe.get_all(
        "Holiday",
        filters={"parent": holiday_list, "holiday_date": ["between", [start, end]]},
        fields=["holiday_date", "description"],
        order_by="holiday_date asc",
    )
    return [{"date": r.holiday_date.strftime("%d %b"), "description": r.description} for r in rows]
