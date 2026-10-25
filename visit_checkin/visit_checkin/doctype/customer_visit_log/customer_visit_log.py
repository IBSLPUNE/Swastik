import frappe
from frappe.model.document import Document
from frappe.utils import time_diff_in_seconds


class CustomerVisitLog(Document):
    def validate(self):
        self.set_time_spent()

    def set_time_spent(self):
        """Single source of truth for 'time at customer' (also works for manual edits in Desk)."""
        if self.milestone == "Customer Visit" and self.arrival_time and self.departure_time:
            seconds = time_diff_in_seconds(self.departure_time, self.arrival_time)
            self.time_spent_minutes = round(max(seconds, 0) / 60, 1)
