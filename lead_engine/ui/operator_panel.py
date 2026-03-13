from __future__ import annotations

import csv
import io
import os
import subprocess
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
START_DASHBOARD_BAT = BASE_DIR.parent / "start_dashboard.bat"
MAX_DAILY_SEND = 20
PLAYWRIGHT_HELP_TEXT = "Playwright browser is not installed.\nRun:\npip install playwright\npython -m playwright install"

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


def _open_queue_folder() -> None:
    queue_dir = PENDING_EMAILS_CSV.parent
    queue_dir.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt":
            os.startfile(str(queue_dir))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(queue_dir)], check=False)
        else:
            subprocess.run(["xdg-open", str(queue_dir)], check=False)
    except Exception as exc:
        messagebox.showerror("Open folder failed", f"Could not open queue folder: {exc}")


def _open_queue_file(path: Path) -> None:
    if not path.exists():
        messagebox.showwarning("Missing file", f"File does not exist: {path}")
        return
    try:
        if os.name == "nt":
            subprocess.run(["explorer", "/select,", str(path)], check=False)
        else:
            _open_queue_folder()
    except Exception:
        _open_queue_folder()


class OperatorPanel:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("Outreach Operator Panel")
        self.root.geometry("1100x760")

        ensure_required_files()

        self.industry_var = StringVar(value=_load_active_industries()[0])
        self.limit_var = StringVar(value="20")
        self.city_var = StringVar(value="")
        self.skip_scan_var = BooleanVar(value=False)
        self.prospects_count_var = StringVar(value="Prospects rows: 0")
        self.pending_email_count_var = StringVar(value="Pending email rows: 0")
        self.pending_form_count_var = StringVar(value="Pending contact form rows: 0")
        self.approved_ready_var = StringVar(value="Approved-ready emails: 0")
        self.sent_today_var = StringVar(value=f"Sent today / {MAX_DAILY_SEND}: 0/{MAX_DAILY_SEND}")
        self.banner_var = StringVar(value="✅ Ready — choose Industry + Quantity, then click Discover + Draft Outreach")

        self._build_ui()
        self.refresh_status(quiet=True)

    def _set_banner(self, level: str, message: str) -> None:
        prefix = {"ok": "✅", "warn": "⚠️", "error": "❌"}.get(level, "ℹ️")
        self.banner_var.set(f"{prefix} {message}")

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Section.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("Banner.TLabel", font=("Segoe UI", 10, "bold"), padding=8)

        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=BOTH, expand=True)

        title_row = ttk.Frame(main)
        title_row.pack(fill=X, pady=(0, 8))
        ttk.Label(title_row, text="Outreach Operator Panel", style="Header.TLabel").pack(side=LEFT)
        ttk.Button(title_row, text="Start Dashboard", command=self.start_dashboard).pack(side=RIGHT)

        ttk.Label(main, textvariable=self.banner_var, style="Banner.TLabel").pack(fill=X, pady=(0, 8))

        ttk.Label(main, text="Prospect Discovery", style="Section.TLabel").pack(anchor="w", pady=(0, 8))

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
        ttk.Label(row2, text="Tip: keep a populated prospects.csv as backup if discovery network is blocked.").pack(side=LEFT, padx=8)

        actions = ttk.Frame(main)
        actions.pack(fill=X, pady=(8, 10))
        ttk.Button(actions, text="Discover + Draft Outreach", command=self.discover_and_draft).pack(side=LEFT, fill=X, expand=True)
        ttk.Button(actions, text="Install Playwright Help", command=self.install_playwright_help).pack(side=RIGHT, padx=(10, 0))

        ttk.Label(main, text="Status Summary", style="Section.TLabel").pack(anchor="w", pady=(4, 8))
        counts = ttk.Frame(main)
        counts.pack(fill=X, pady=(0, 6))
        ttk.Label(counts, textvariable=self.prospects_count_var, width=24).pack(side=LEFT)
        ttk.Label(counts, textvariable=self.pending_email_count_var, width=26).pack(side=LEFT)
        ttk.Label(counts, textvariable=self.pending_form_count_var, width=32).pack(side=LEFT)
        counts2 = ttk.Frame(main)
        counts2.pack(fill=X, pady=(0, 8))
        ttk.Label(counts2, textvariable=self.approved_ready_var, width=24).pack(side=LEFT)
        ttk.Label(counts2, textvariable=self.sent_today_var, width=24).pack(side=LEFT)

        ttk.Label(main, text="Queue Review", style="Section.TLabel").pack(anchor="w", pady=(4, 8))
        qrow = ttk.Frame(main)
        qrow.pack(fill=X, pady=4)
        ttk.Button(qrow, text="Open Email Queue", command=lambda: _open_queue_file(PENDING_EMAILS_CSV)).pack(side=LEFT, padx=(0, 10))
        ttk.Button(qrow, text="Open Contact Form Queue", command=lambda: _open_queue_file(PENDING_CONTACT_FORMS_CSV)).pack(side=LEFT, padx=(0, 10))
        ttk.Button(qrow, text="Open Queue Folder", command=_open_queue_folder).pack(side=LEFT)

        ttk.Label(main, text="Sending", style="Section.TLabel").pack(anchor="w", pady=(10, 8))
        srow = ttk.Frame(main)
        srow.pack(fill=X, pady=4)
        ttk.Button(srow, text="Dry Run Send", command=self.dry_run_send).pack(side=LEFT, padx=(0, 10))
        ttk.Button(srow, text="Live Send", command=self.live_send).pack(side=LEFT, padx=(0, 10))
        ttk.Button(srow, text="Refresh Status", command=self.refresh_status).pack(side=LEFT)

        ttk.Label(main, text="Status & Activity Log", style="Section.TLabel").pack(anchor="w", pady=(10, 6))
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

    def _log_output(self, output: str, max_lines: int = 12) -> None:
        if not output:
            return
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        for line in lines[:max_lines]:
            self._log(line)
        remaining = len(lines) - max_lines
        if remaining > 0:
            self._log(f"... {remaining} additional log lines hidden for readability")

    def _looks_like_playwright_missing(self, text: str) -> bool:
        lowered = (text or "").lower()
        return "playwright" in lowered and (
            "executable doesn't exist" in lowered
            or "browser executable" in lowered
            or "please run the following command" in lowered
            or "ms-playwright" in lowered
        )

    def install_playwright_help(self) -> None:
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append("pip install playwright\npython -m playwright install")
            self._log("Playwright setup commands copied to clipboard.")
        except Exception:
            self._log("Clipboard unavailable; showing setup commands below.")
        self._set_banner("warn", "Playwright setup needed. Run the two commands shown in Status log.")
        self._log(PLAYWRIGHT_HELP_TEXT)

    def start_dashboard(self) -> None:
        try:
            if os.name == "nt" and START_DASHBOARD_BAT.exists():
                subprocess.Popen(["cmd", "/c", "start", "", str(START_DASHBOARD_BAT)], cwd=str(BASE_DIR.parent))
            else:
                subprocess.Popen([sys.executable, str(Path(__file__).resolve())], cwd=str(BASE_DIR))
            self._set_banner("ok", "Started another dashboard window.")
            self._log("Started dashboard launcher.")
        except Exception as exc:
            self._set_banner("error", "Could not start dashboard launcher.")
            self._log(f"dashboard start failed: {exc}")

    def discover_and_draft(self) -> None:
        industry = self.industry_var.get().strip()
        limit = int(self.limit_var.get())
        city = self.city_var.get().strip()
        skip_scan = bool(self.skip_scan_var.get())

        pending_before = _csv_data_rows(PENDING_EMAILS_CSV)
        forms_before = _csv_data_rows(PENDING_CONTACT_FORMS_CSV)

        self._log("--- Discover + Draft Outreach ---")
        self._set_banner("ok", f"Running discovery+drafting for {industry} (limit={limit})...")
        stats, output = self._capture_output(
            run_lead_engine,
            input_csv=PROSPECTS_CSV,
            discover=industry,
            limit=limit,
            city=city,
            skip_scan=skip_scan,
        )
        if self._looks_like_playwright_missing(output):
            self._set_banner("warn", "Playwright browser not installed. Use Install Playwright Help.")
            self._log(PLAYWRIGHT_HELP_TEXT)
        else:
            self._log_output(output)

        pending_after = _csv_data_rows(PENDING_EMAILS_CSV)
        forms_after = _csv_data_rows(PENDING_CONTACT_FORMS_CSV)
        new_email = max(0, pending_after - pending_before)
        new_forms = max(0, forms_after - forms_before)

        self._log(
            "summary: discovered={discovered} loaded={loaded} scanned={scanned} drafted={drafted} "
            "skipped={skipped} queued_email={queued_email} queued_contact_forms={queued_contact_forms}".format(**stats)
        )

        drafted = int(stats.get("drafted", 0))
        discovered = int(stats.get("discovered", 0))
        loaded = int(stats.get("loaded", 0))
        if drafted > 0:
            self._set_banner(
                "ok",
                f"Done. Drafted {drafted} outreach rows (+{new_email} email queue, +{new_forms} contact form queue).",
            )
        elif discovered == 0 and loaded > 0:
            self._set_banner(
                "warn",
                "Discovery found 0 but CSV fallback loaded rows. Check queue or dedupe/approval filters.",
            )
        else:
            self._set_banner(
                "warn",
                "No new drafts produced. Check logs for network blocks, duplicates, or missing required fields.",
            )

        self.refresh_status(quiet=True)

    def dry_run_send(self) -> None:
        self._log("--- Dry Run Send ---")
        self._set_banner("ok", "Running dry-run send (no live email will be sent).")
        stats, output = self._capture_output(
            process_pending_emails,
            pending_csv_path=PENDING_EMAILS_CSV,
            dry_run=True,
            contact_history_csv=CONTACT_HISTORY_CSV,
        )
        self._log_output(output)

        self._log(
            "summary: approved-ready={approved_ready} capped={capped} sent={sent} failed={failed} skipped={skipped}".format(
                **stats
            )
        )
        self._set_banner(
            "ok",
            f"Dry-run complete. Eligible={stats.get('approved_ready', 0)} sent(simulated)={stats.get('sent', 0)} failed={stats.get('failed', 0)}.",
        )
        self.refresh_status(quiet=True)

    def live_send(self) -> None:
        if not os.getenv("GMAIL_ADDRESS", "").strip() or not os.getenv("GMAIL_APP_PASSWORD", "").strip():
            messagebox.showerror("Missing Gmail env vars", "Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD before live send.")
            self._set_banner("error", "Live send blocked: missing GMAIL_ADDRESS / GMAIL_APP_PASSWORD.")
            self._log("live send blocked: missing Gmail env vars")
            return

        ok = messagebox.askyesno("Confirm live send", "Send approved emails now? This will send live Gmail messages.")
        if not ok:
            self._set_banner("warn", "Live send cancelled by operator.")
            self._log("live send cancelled")
            return

        self._log("--- Live Send ---")
        self._set_banner("warn", "Running LIVE send now...")
        stats, output = self._capture_output(
            process_pending_emails,
            pending_csv_path=PENDING_EMAILS_CSV,
            dry_run=False,
            contact_history_csv=CONTACT_HISTORY_CSV,
        )
        self._log_output(output)

        self._log(
            "summary: approved-ready={approved_ready} capped={capped} sent={sent} failed={failed} skipped={skipped}".format(
                **stats
            )
        )
        if int(stats.get("failed", 0)) > 0:
            self._set_banner("warn", f"Live send complete with failures. sent={stats.get('sent', 0)} failed={stats.get('failed', 0)}")
        else:
            self._set_banner("ok", f"Live send complete. sent={stats.get('sent', 0)}")
        self.refresh_status(quiet=True)

    def refresh_status(self, quiet: bool = False) -> None:
        prospects_rows = _csv_data_rows(PROSPECTS_CSV)
        pending_rows = _csv_data_rows(PENDING_EMAILS_CSV)
        form_rows = _csv_data_rows(PENDING_CONTACT_FORMS_CSV)
        approved_ready = count_send_eligible_rows(PENDING_EMAILS_CSV)
        sent_today = count_sent_today(CONTACT_HISTORY_CSV)

        self.prospects_count_var.set(f"Prospects rows: {prospects_rows}")
        self.pending_email_count_var.set(f"Pending email rows: {pending_rows}")
        self.pending_form_count_var.set(f"Pending contact form rows: {form_rows}")
        self.approved_ready_var.set(f"Approved-ready emails: {approved_ready}")
        self.sent_today_var.set(f"Sent today / {MAX_DAILY_SEND}: {sent_today}/{MAX_DAILY_SEND}")

        if quiet:
            return

        self._log("--- Refresh Status ---")
        self._log(f"prospects.csv rows: {prospects_rows}")
        self._log(f"pending_emails.csv rows: {pending_rows}")
        self._log(f"pending_contact_forms.csv rows: {form_rows}")
        self._log(f"approved-ready emails: {approved_ready}")
        self._log(f"sent today (history): {sent_today}")
        if prospects_rows == 0:
            self._set_banner("warn", "No prospects found in prospects.csv yet.")
        else:
            self._set_banner("ok", "Status refreshed.")


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
