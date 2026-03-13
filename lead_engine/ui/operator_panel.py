from __future__ import annotations

import csv
import io
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from tkinter import END, BOTH, LEFT, RIGHT, X, Y, BooleanVar, StringVar, Tk, messagebox, ttk

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from run_lead_engine import run as run_lead_engine
from send.email_sender_agent import count_send_eligible_rows, count_sent_today, process_pending_emails

INDUSTRIES_CSV = BASE_DIR / "data" / "industries.csv"
PROSPECTS_CSV = BASE_DIR / "data" / "prospects.csv"
PENDING_EMAILS_CSV = BASE_DIR / "queue" / "pending_emails.csv"
PENDING_CONTACT_FORMS_CSV = BASE_DIR / "queue" / "pending_contact_forms.csv"
CONTACT_HISTORY_CSV = BASE_DIR / "data" / "contact_history.csv"

INDUSTRY_HEADERS = ["industry", "active", "priority", "notes"]
INDUSTRY_SEED = [
    ["HVAC", "true", "1", ""],
    ["Plumbing", "true", "2", ""],
    ["Electrician", "true", "3", ""],
    ["Roofing", "true", "4", ""],
    ["Landscaping", "true", "5", ""],
    ["Cleaning Service", "true", "6", ""],
    ["Pest Control", "true", "7", ""],
    ["Garage Door", "true", "8", ""],
    ["Tree Service", "true", "9", ""],
    ["Appliance Repair", "true", "10", ""],
]

PROSPECT_HEADERS = [
    "business_name",
    "city",
    "state",
    "website",
    "phone",
    "contact_method",
    "likely_opportunity",
    "priority_score",
]
PENDING_EMAIL_HEADERS = [
    "business_name",
    "city",
    "state",
    "website",
    "phone",
    "contact_method",
    "to_email",
    "subject",
    "body",
    "approved",
    "sent_at",
    "scoring_reason",
    "final_priority_score",
]
PENDING_FORM_HEADERS = [
    "business_name",
    "city",
    "state",
    "website",
    "phone",
    "contact_method",
    "contact_page_url",
    "approved",
    "submitted_at",
    "notes",
    "scoring_reason",
    "final_priority_score",
]
CONTACT_HISTORY_HEADERS = ["business_name", "website", "contacted_date", "contact_method", "status", "notes"]


def _ensure_csv(path: Path, header: list[str], rows: list[list[str]] | None = None) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in (rows or []):
            writer.writerow(row)


def ensure_required_files() -> None:
    _ensure_csv(INDUSTRIES_CSV, INDUSTRY_HEADERS, INDUSTRY_SEED)
    _ensure_csv(PROSPECTS_CSV, PROSPECT_HEADERS)
    _ensure_csv(PENDING_EMAILS_CSV, PENDING_EMAIL_HEADERS)
    _ensure_csv(PENDING_CONTACT_FORMS_CSV, PENDING_FORM_HEADERS)
    _ensure_csv(CONTACT_HISTORY_CSV, CONTACT_HISTORY_HEADERS)


def _csv_data_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        count = sum(1 for _ in reader)
    return max(0, count - 1)


def _load_active_industries() -> list[str]:
    ensure_required_files()
    industries: list[str] = []
    with INDUSTRIES_CSV.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if (row.get("active", "").strip().lower() or "true") == "true":
                name = (row.get("industry") or "").strip()
                if name:
                    industries.append(name)
    return industries or ["HVAC"]


def _open_file(path: Path) -> None:
    if not path.exists():
        messagebox.showwarning("Missing file", f"File does not exist: {path}")
        return
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')
    except Exception as exc:
        messagebox.showerror("Open failed", f"Could not open file: {exc}")


class OperatorPanel:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("Outreach Operator Panel")
        self.root.geometry("980x700")

        ensure_required_files()

        self.industry_var = StringVar(value=_load_active_industries()[0])
        self.limit_var = StringVar(value="20")
        self.city_var = StringVar(value="")
        self.skip_scan_var = BooleanVar(value=False)

        self._build_ui()
        self.refresh_status()

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=BOTH, expand=True)

        ttk.Label(main, text="Prospect Discovery", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 8))

        row1 = ttk.Frame(main)
        row1.pack(fill=X, pady=4)
        ttk.Label(row1, text="Industry", width=18).pack(side=LEFT)
        industries = _load_active_industries()
        ttk.Combobox(row1, textvariable=self.industry_var, values=industries, state="readonly", width=30).pack(side=LEFT, padx=6)

        ttk.Label(row1, text="Quantity", width=12).pack(side=LEFT, padx=(20, 0))
        ttk.Combobox(row1, textvariable=self.limit_var, values=["5", "10", "20", "30", "50"], state="readonly", width=8).pack(side=LEFT, padx=6)

        row2 = ttk.Frame(main)
        row2.pack(fill=X, pady=4)
        ttk.Label(row2, text="Optional City", width=18).pack(side=LEFT)
        ttk.Entry(row2, textvariable=self.city_var, width=35).pack(side=LEFT, padx=6)
        ttk.Checkbutton(row2, text="Skip scan", variable=self.skip_scan_var).pack(side=LEFT, padx=14)

        ttk.Button(main, text="Discover + Draft Outreach", command=self.discover_and_draft).pack(fill=X, pady=(8, 10))

        ttk.Label(main, text="Queue Review", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(4, 8))
        qrow = ttk.Frame(main)
        qrow.pack(fill=X, pady=4)
        ttk.Button(qrow, text="Open Email Queue", command=lambda: _open_file(PENDING_EMAILS_CSV)).pack(side=LEFT, padx=(0, 10))
        ttk.Button(qrow, text="Open Contact Form Queue", command=lambda: _open_file(PENDING_CONTACT_FORMS_CSV)).pack(side=LEFT)

        ttk.Label(main, text="Sending", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(10, 8))
        srow = ttk.Frame(main)
        srow.pack(fill=X, pady=4)
        ttk.Button(srow, text="Dry Run Send", command=self.dry_run_send).pack(side=LEFT, padx=(0, 10))
        ttk.Button(srow, text="Live Send", command=self.live_send).pack(side=LEFT, padx=(0, 10))
        ttk.Button(srow, text="Refresh Status", command=self.refresh_status).pack(side=LEFT)

        ttk.Label(main, text="Status", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(10, 6))
        self.status = ttk.Treeview(main, columns=("message",), show="tree", height=17)
        self.status.pack(fill=BOTH, expand=True)

    def _log(self, msg: str) -> None:
        self.status.insert("", END, text=msg)
        self.status.yview_moveto(1.0)

    def _capture_output(self, func, *args, **kwargs):
        buff = io.StringIO()
        with redirect_stdout(buff):
            result = func(*args, **kwargs)
        output = buff.getvalue().strip()
        return result, output

    def discover_and_draft(self) -> None:
        industry = self.industry_var.get().strip()
        limit = int(self.limit_var.get())
        city = self.city_var.get().strip()
        skip_scan = bool(self.skip_scan_var.get())

        self._log("--- Discover + Draft Outreach ---")
        stats, output = self._capture_output(
            run_lead_engine,
            input_csv=PROSPECTS_CSV,
            discover=industry,
            limit=limit,
            city=city,
            skip_scan=skip_scan,
        )
        if output:
            for line in output.splitlines():
                self._log(line)

        self._log(
            "summary: discovered={discovered} loaded={loaded} scanned={scanned} drafted={drafted} "
            "skipped={skipped} queued_email={queued_email} queued_contact_forms={queued_contact_forms}".format(**stats)
        )
        self.refresh_status()

    def dry_run_send(self) -> None:
        self._log("--- Dry Run Send ---")
        stats, output = self._capture_output(
            process_pending_emails,
            pending_csv_path=PENDING_EMAILS_CSV,
            dry_run=True,
            contact_history_csv=CONTACT_HISTORY_CSV,
        )
        if output:
            for line in output.splitlines():
                self._log(line)

        self._log(
            "summary: approved-ready={approved_ready} capped={capped} sent={sent} failed={failed} skipped={skipped}".format(
                **stats
            )
        )
        self.refresh_status()

    def live_send(self) -> None:
        if not os.getenv("GMAIL_ADDRESS", "").strip() or not os.getenv("GMAIL_APP_PASSWORD", "").strip():
            messagebox.showerror("Missing Gmail env vars", "Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD before live send.")
            self._log("live send blocked: missing Gmail env vars")
            return

        ok = messagebox.askyesno("Confirm live send", "Send approved emails now? This will send live Gmail messages.")
        if not ok:
            self._log("live send cancelled")
            return

        self._log("--- Live Send ---")
        stats, output = self._capture_output(
            process_pending_emails,
            pending_csv_path=PENDING_EMAILS_CSV,
            dry_run=False,
            contact_history_csv=CONTACT_HISTORY_CSV,
        )
        if output:
            for line in output.splitlines():
                self._log(line)

        self._log(
            "summary: approved-ready={approved_ready} capped={capped} sent={sent} failed={failed} skipped={skipped}".format(
                **stats
            )
        )
        self.refresh_status()

    def refresh_status(self) -> None:
        self._log("--- Refresh Status ---")
        prospects_rows = _csv_data_rows(PROSPECTS_CSV)
        pending_rows = _csv_data_rows(PENDING_EMAILS_CSV)
        form_rows = _csv_data_rows(PENDING_CONTACT_FORMS_CSV)
        approved_ready = count_send_eligible_rows(PENDING_EMAILS_CSV)
        sent_today = count_sent_today(CONTACT_HISTORY_CSV)

        self._log(f"prospects.csv rows: {prospects_rows}")
        self._log(f"pending_emails.csv rows: {pending_rows}")
        self._log(f"pending_contact_forms.csv rows: {form_rows}")
        self._log(f"approved-ready emails: {approved_ready}")
        self._log(f"sent today (history): {sent_today}")


def run_self_test() -> None:
    ensure_required_files()
    print("self-test ok")
    print(f"industries={len(_load_active_industries())}")
    print(f"prospects_rows={_csv_data_rows(PROSPECTS_CSV)}")
    print(f"pending_email_rows={_csv_data_rows(PENDING_EMAILS_CSV)}")
    print(f"pending_form_rows={_csv_data_rows(PENDING_CONTACT_FORMS_CSV)}")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        run_self_test()
        return

    root = Tk()
    OperatorPanel(root)
    root.mainloop()


if __name__ == "__main__":
    main()
