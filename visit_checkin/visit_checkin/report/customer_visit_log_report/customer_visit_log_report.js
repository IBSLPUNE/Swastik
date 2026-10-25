frappe.query_reports["Customer Visit Log Report"] = {
	filters: [
		{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
		{ fieldname: "customer_name", label: __("Customer Name"), fieldtype: "Data" },
		{ fieldname: "milestone", label: __("Milestone"), fieldtype: "Select", options: "\nHome Departure\nCustomer Visit\nHome Arrival" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nOpen\nCompleted" },
		{ fieldname: "only_customer_visits", label: __("Only Customer Visits"), fieldtype: "Check", default: 1 },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.month_end(), reqd: 1 },
	],

	formatter: function (value, row, column, data, default_formatter) {
		const esc = frappe.utils.escape_html;
		const badge = (text, bg) =>
			`<span style="background:${bg};color:#fff;padding:2px 10px;border-radius:10px;font-size:11px;font-weight:600;">${esc(text)}</span>`;

		if (!data) {
			return default_formatter(value, row, column, data);
		}

		switch (column.fieldname) {
			case "status":
				return badge(data.status, data.status === "Open" ? "#FF9800" : "#4CAF50");

			case "milestone": {
				const colors = { "Home Departure": "#2196F3", "Customer Visit": "#9C27B0", "Home Arrival": "#4CAF50" };
				return `<b style="color:${colors[data.milestone] || "#777"}">${esc(data.milestone)}</b>`;
			}

			case "time_spent_minutes":
				return data.time_spent_minutes ? `<b>${data.time_spent_minutes}</b> min` : "";

			case "distance_from_home_km":
				return data.distance_from_home_km ? `<b>${data.distance_from_home_km}</b> km` : "";

			case "distance_source":
				if (!data.distance_source) return "";
				return badge(data.distance_source, data.distance_source === "Google Road" ? "#009688" : "#9E9E9E");

			case "customer_name":
				return data.customer_name ? esc(data.customer_name) : '<span style="color:#bbb">—</span>';

			case "arrival_map":
			case "departure_map":
				return value
					? `<a href="${esc(value)}" target="_blank" rel="noopener">📍 Map</a>`
					: '<span style="color:#F44336">no GPS</span>';

			case "arrival_photo":
			case "departure_photo":
				return value ? `<a href="${esc(value)}" target="_blank" rel="noopener">🖼 View</a>` : "";

			case "is_offline_entry":
				return data.is_offline_entry ? badge("Offline", "#607D8B") : "";
		}

		return default_formatter(value, row, column, data);
	},
};
