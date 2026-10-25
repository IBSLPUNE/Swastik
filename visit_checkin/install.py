import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

EMPLOYEE_FIELDS = {
    "Employee": [
        {
            "fieldname": "custom_home_latitude",
            "label": "Home Latitude",
            "fieldtype": "Float",
            "precision": "6",
            "insert_after": "current_address",
            "description": "Optional. If empty, the location of the day's 'Home Departure' check-in is used as the origin for distance.",
        },
        {
            "fieldname": "custom_home_longitude",
            "label": "Home Longitude",
            "fieldtype": "Float",
            "precision": "6",
            "insert_after": "custom_home_latitude",
        },
    ]
}


def ensure_custom_fields():
    create_custom_fields(EMPLOYEE_FIELDS, update=True)


def after_install():
    ensure_custom_fields()


def after_migrate():
    ensure_custom_fields()
