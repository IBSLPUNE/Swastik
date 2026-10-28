import frappe
from frappe import _


def execute(filters=None):
    filters = frappe._dict(filters or {})
    data = get_data(filters)
    return get_columns(), data, None, None, get_summary(data)


def get_columns():
    return [
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 110},
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 150},
        {"label": _("Date"), "fieldname": "visit_date", "fieldtype": "Date", "width": 95},
        {"label": _("Milestone"), "fieldname": "milestone", "fieldtype": "Data", "width": 130},
        {"label": _("Customer"), "fieldname": "customer_name", "fieldtype": "Data", "width": 160},
        {"label": _("Arrival"), "fieldname": "arrival_time", "fieldtype": "Datetime", "width": 150},
        {"label": _("Departure"), "fieldname": "departure_time", "fieldtype": "Datetime", "width": 150},
        {"label": _("Time Spent (min)"), "fieldname": "time_spent_minutes", "fieldtype": "Float", "precision": 1, "width": 120},
        {"label": _("Distance (km)"), "fieldname": "distance_from_home_km", "fieldtype": "Float", "precision": 2, "width": 110},
        {"label": _("Distance Type"), "fieldname": "distance_source", "fieldtype": "Data", "width": 110},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": _("Arrival Map"), "fieldname": "arrival_map", "fieldtype": "Data", "width": 90},
        {"label": _("Departure Map"), "fieldname": "departure_map", "fieldtype": "Data", "width": 100},
        {"label": _("Arrival Photo"), "fieldname": "arrival_photo", "fieldtype": "Data", "width": 100},
        {"label": _("Departure Photo"), "fieldname": "departure_photo", "fieldtype": "Data", "width": 110},
        {"label": _("Offline"), "fieldname": "is_offline_entry", "fieldtype": "Check", "width": 70},
        {"label": _("Log"), "fieldname": "name", "fieldtype": "Link", "options": "Customer Visit Log", "width": 100},
    ]


def get_data(filters):
    conditions = {}

    for key in ("employee", "status", "milestone"):
        if filters.get(key):
            conditions[key] = filters.get(key)

    if filters.get("customer_name"):
        conditions["customer_name"] = ["like", f"%{filters.customer_name}%"]

    if filters.get("only_customer_visits"):
        conditions["milestone"] = "Customer Visit"

    if filters.get("from_date") and filters.get("to_date"):
        conditions["visit_date"] = ["between", [filters.from_date, filters.to_date]]

    rows = frappe.get_all(
        "Customer Visit Log",
        filters=conditions,
        fields=[
            "name", "employee", "employee_name", "visit_date", "milestone", "customer_name",
            "arrival_time", "departure_time", "time_spent_minutes", "distance_from_home_km",
            "distance_source", "status", "is_offline_entry",
            "arrival_latitude", "arrival_longitude", "departure_latitude", "departure_longitude",
            "arrival_photo", "departure_photo",
        ],
        order_by="visit_date desc, creation asc",
    )

    for row in rows:
        row["arrival_map"] = _map_url(row.pop("arrival_latitude"), row.pop("arrival_longitude"))
        row["departure_map"] = _map_url(row.pop("departure_latitude"), row.pop("departure_longitude"))

    return rows


def _map_url(lat, lng):
    if lat and lng:
        return f"https://www.google.com/maps?q={lat},{lng}"
    return ""


def get_summary(data):
    visits = [r for r in data if r.milestone == "Customer Visit"]
    total_time = sum((r.time_spent_minutes or 0) for r in visits)
    total_km = sum((r.distance_from_home_km or 0) for r in visits)
    closed = [r for r in visits if r.status == "Completed"]

    return [
        {"value": len(visits), "label": _("Customer Visits"), "datatype": "Int", "indicator": "Blue"},
        {"value": round(total_time / 60, 1), "label": _("Hours at Customers"), "datatype": "Float", "indicator": "Orange"},
        {
            "value": round(total_time / len(closed), 1) if closed else 0,
            "label": _("Avg Minutes / Visit"),
            "datatype": "Float",
            "indicator": "Green",
        },
        {"value": round(total_km, 1), "label": _("Total Distance (km)"), "datatype": "Float", "indicator": "Purple"},
        {
            "value": len([r for r in visits if r.status == "Open"]),
            "label": _("Open Visits"),
            "datatype": "Int",
            "indicator": "Red",
        },
        {
            "value": len([r for r in data if r.is_offline_entry]),
            "label": _("Captured Offline"),
            "datatype": "Int",
            "indicator": "Grey",
        },
    ]


def get_chart(data):
    per_customer = {}
    for row in data:
        if row.milestone == "Customer Visit" and row.customer_name:
            per_customer[row.customer_name] = per_customer.get(row.customer_name, 0) + (row.time_spent_minutes or 0)

    top = sorted(per_customer.items(), key=lambda item: item[1], reverse=True)[:10]
    if not top:
        return None

    return {
        "data": {
            "labels": [name for name, _minutes in top],
            "datasets": [{"name": _("Time Spent (min)"), "values": [round(m, 1) for _name, m in top]}],
        },
        "type": "bar",
        "colors": ["#2196F3"],
        "title": _("Top Customers by Time Spent"),
    }
