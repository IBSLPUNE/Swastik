# Visit Checkin (Frappe v15 app)

Geotagged **customer-visit check-in** for field employees, as an installable **PWA that works offline**.

Flow per day: `Start Day (Leaving Home)` -> `Arrived at Customer` (customer name) -> `Leaving Customer` -> ... -> `Reached Home`.
Every step captures a **live camera photo + GPS + time**. Time spent at each customer and distance from home are computed automatically.
Home Departure / Home Arrival also create the standard HRMS **Employee Checkin** (IN / OUT).

## What is inside

| Piece | Where |
|---|---|
| DocType **Customer Visit Log** | `visit_checkin/visit_checkin/doctype/customer_visit_log` |
| Script Report **Customer Visit Log Report** (cards, chart, map + photo links) | `visit_checkin/visit_checkin/report/...` |
| API (replaces all the Server Scripts) | `visit_checkin/api.py` |
| Employee custom fields `custom_home_latitude / longitude` (created on install + migrate) | `visit_checkin/install.py` |
| PWA (page, manifest, service worker, icons) | `visit_checkin/public/visit-checkin/` |

URL for employees: `https://<your-site>/visit-checkin`
(redirects to `/assets/visit_checkin/visit-checkin/index.html`)

## Install (self-hosted bench)

```bash
cd ~/frappe-bench
cp -r /path/to/visit_checkin apps/visit_checkin
cd apps/visit_checkin && git init -q && git add -A && git commit -qm "init" && cd ../..
./env/bin/pip install -e apps/visit_checkin
grep -qx visit_checkin sites/apps.txt || echo visit_checkin >> sites/apps.txt
bench --site <site> install-app visit_checkin
bench build --app visit_checkin
bench --site <site> migrate
bench restart
```

**Frappe Cloud:** push this folder to a (private) GitHub repo -> Dashboard -> Apps -> Add App -> deploy to the bench -> install on the site.

## BEFORE installing: remove the earlier hand-made test objects

The first prototype created a DocType / report by console. They clash with the ones in this app.
Run once in `bench --site <site> console` (test data in the old doctype is lost):

```python
import frappe
if frappe.db.exists("Report", "Customer Visit Log Report"):
    frappe.delete_doc("Report", "Customer Visit Log Report", force=1)
if frappe.db.exists("DocType", "Customer Visit Log"):
    frappe.delete_doc("DocType", "Customer Visit Log", force=1)
frappe.db.commit()
```

The old Server Scripts (`get_visit_status`, `submit_visit_milestone`, ...) and the Web Page block are no longer used - disable them.
The Employee custom fields already created are reused (same field names).

## Site config (optional but recommended)

`sites/<site>/site_config.json` (Frappe Cloud: Site -> Config):

```json
{
  "google_maps_api_key": "AIza...",
  "visit_checkin_max_offline_days": 3,
  "visit_checkin_photo_required": 1
}
```

* `google_maps_api_key` - Distance Matrix API key -> **real road distance** (`Distance Type = Google Road`).
  Without it the app falls back to **straight-line distance** (`Distance Type = Straight-line`), always labelled in the report.
* `visit_checkin_max_offline_days` - an offline entry older than this is stored with server time and a remark.
* `visit_checkin_photo_required` - set `0` to allow check-in without photo.

Distance origin = Employee master home coordinates if filled, otherwise the location of that day's **Home Departure**.

## Using it on phones

1. Open `https://<site>/visit-checkin` **once with internet**, log in.
2. **Android (Chrome):** menu -> *Install app / Add to Home screen*.
   **iPhone (Safari only):** Share -> *Add to Home Screen*. Open it from the new icon and log in once more
   (iOS keeps a separate login for the home-screen app) - do this with internet.
3. From then on the icon opens even with **no network**. Check-ins are stored on the phone (photo, GPS, device time)
   and sync automatically when the phone is online again. A badge shows how many are waiting.

### Offline notes
* GPS works without internet but a fresh satellite fix can take up to ~1 minute (the app waits up to 60 s offline).
  If no fix is obtained the entry is saved without location and shown as `no GPS` in the report.
* iOS has no background sync: the app syncs when it is opened (or comes back to the foreground) with internet.
* Entries captured offline are marked **Captured Offline** with the sync time; device time is accepted only within sane limits.
* Re-sent entries are de-duplicated (`client_ref`), so a lost response never creates a duplicate visit.
* If an entry is rejected by the server (e.g. wrong step) it is parked under a red badge -> tap to Retry / Discard.

## API (`/api/method/visit_checkin.api.<name>`)

`get_csrf_token` (guest allowed, used as login probe) | `get_visit_status` | `submit_visit_milestone` |
`get_today_visits` | `get_employee_attendance_calendar` | `get_employee_last_checkins`

## Not included yet

Face recognition match, late-mark / payroll-deduction policy and category-wise milestone sets are separate phases.
# Swastik
