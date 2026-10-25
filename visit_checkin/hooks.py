app_name = "visit_checkin"
app_title = "Visit Checkin"
app_publisher = "Your Company"
app_description = "Geotagged customer-visit check-in (installable PWA with offline sync) for ERPNext / HRMS"
app_email = "you@example.com"
app_license = "mit"

required_apps = ["erpnext", "hrms"]

# Creates / keeps the Employee home-location custom fields in place
after_install = "visit_checkin.install.after_install"
after_migrate = ["visit_checkin.install.after_migrate"]

# Short, friendly URL for employees:  https://<site>/visit-checkin
website_redirects = [
    {"source": "/visit-checkin", "target": "/assets/visit_checkin/visit-checkin/index.html"},
]
