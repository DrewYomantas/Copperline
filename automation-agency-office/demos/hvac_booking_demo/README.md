# Summit HVAC Booking Automation Demo

## What this demo shows
This demo presents a simple booking automation flow for a local home-service company (Summit HVAC):
1. Customer submits a service request.
2. System captures key request details.
3. Appointment is scheduled.
4. Confirmation is generated.
5. Reminder workflow is queued.

It is intentionally lightweight and credible: no backend, no inflated claims, and no guaranteed revenue language.

## How to open locally
From the repository root:

```bash
cd automation-agency-office/demos/hvac_booking_demo
python3 -m http.server 8000
```

Then open: `http://localhost:8000`

(You can also open `index.html` directly in a browser.)

## Suggested 60-second Loom walkthrough script
"Here’s a quick look at Summit HVAC’s booking automation demo. On the left, a customer submits a standard service request with name, phone, service type, preferred date, and issue. When I click **Run Booking Automation**, the workflow panel shows each step in sequence: lead captured, appointment scheduled, confirmation generated, and reminder queued. On the right, we get a confirmation card with the appointment summary. For a local service team, this means fewer missed bookings, faster response time, and less manual scheduling work, while still keeping human follow-up available when needed."
