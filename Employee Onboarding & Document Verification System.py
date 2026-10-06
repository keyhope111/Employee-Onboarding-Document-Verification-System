import sqlite3
import shutil
import mimetypes
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import filedialog

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# =========================
# SETTINGS
# =========================
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "employee_data"
DOC_DIR = DATA_DIR / "documents"
DB_PATH = DATA_DIR / "onboarding.db"
CREDENTIALS_PATH = APP_DIR / "credentials.json"
TOKEN_PATH = APP_DIR / "token.json"

DATA_DIR.mkdir(exist_ok=True)
DOC_DIR.mkdir(exist_ok=True)

SCOPES = ["https://www.googleapis.com/auth/drive"]
DRIVE_ROOT = "Employee Onboarding Documents"

REQUIRED_DOCUMENTS = [
    "Government ID", "NBI Clearance", "Police Clearance",
    "Proof of Address", "Educational Credential",
    "Employment Document", "Other Compliance Document"
]

CHECKLIST_ITEMS = [
    "Submit personal information", "Submit Government ID",
    "Submit NBI Clearance", "Submit Police Clearance",
    "Submit Proof of Address", "Submit Educational Credential",
    "Submit Employment Document", "Submit Other Compliance Document",
    "Complete company orientation", "Sign employment agreement"
]

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}


# =========================
# HELPERS
# =========================
def pause():
    input("\nPress Enter to continue...")


def clear_screen():
    import os
    os.system("cls" if os.name == "nt" else "clear")


def header(title):
    clear_screen()
    print("=" * 60)
    print(title.center(60))
    print("=" * 60)
    print()


def line():
    print("-" * 60)


def get_input(prompt, required=False):
    while True:
        value = input(prompt).strip()
        if required and not value:
            print("This field is required.")
            continue
        return value


def select_file():
    root = tk.Tk()
    root.withdraw()
    try:
        return filedialog.askopenfilename(
            title="Attach Employee Credential",
            filetypes=[
                ("Images and PDF", "*.jpg *.jpeg *.png *.pdf"),
                ("JPG Image", "*.jpg"), ("JPEG Image", "*.jpeg"),
                ("PNG Image", "*.png"), ("PDF Document", "*.pdf")
            ]
        )
    finally:
        root.destroy()


def safe_name(employee):
    return "".join(
        c for c in f"{employee['employee_no']}_{employee['last_name']}"
        if c.isalnum() or c in "_-"
    )


def show_employee(employee):
    print(f"Employee No.:  {employee['employee_no']}")
    print(f"Full name:     {employee['first_name']} {employee['last_name']}")
    print(f"Email:         {employee['email'] or 'N/A'}")
    print(f"Phone number:  {employee['phone'] or 'N/A'}")
    print(f"Department:    {employee['department'] or 'N/A'}")
    print(f"Position:      {employee['position'] or 'N/A'}")
    print(f"Date of birth: {employee['date_of_birth'] or 'N/A'}")
    print(f"Home address:  {employee['address'] or 'N/A'}")
    print(f"Status:        {employee['status']}")


# =========================
# GOOGLE DRIVE
# =========================
class GoogleDriveManager:
    def __init__(self):
        self.service = None
        self.root_folder_id = None

    def connect(self):
        if self.service:
            return True
        if not CREDENTIALS_PATH.exists():
            print("\nGoogle Drive is not configured.")
            print(f"Place credentials.json here:\n{CREDENTIALS_PATH}")
            return False

        creds = None
        if TOKEN_PATH.exists():
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            except Exception:
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None
            if not creds:
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(CREDENTIALS_PATH), SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                except Exception as exc:
                    print("\nGoogle authorization failed.")
                    print(exc)
                    return False
            try:
                TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            except OSError as exc:
                print(f"Warning: Could not save token.json: {exc}")

        try:
            self.service = build("drive", "v3", credentials=creds)
            self.root_folder_id = self.get_or_create_folder(DRIVE_ROOT)
            return True
        except Exception as exc:
            print("\nCould not connect to Google Drive.")
            print(exc)
            self.service = None
            return False

    def get_or_create_folder(self, name, parent_id=None):
        if not self.service:
            raise RuntimeError("Google Drive is not connected.")
        safe = name.replace("'", "\\'")
        query = (
            f"name = '{safe}' and "
            "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        if parent_id:
            query += f" and '{parent_id}' in parents"

        result = self.service.files().list(
            q=query, spaces="drive", fields="files(id,name)", pageSize=10
        ).execute()
        files = result.get("files", [])
        if files:
            return files[0]["id"]

        metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            metadata["parents"] = [parent_id]
        return self.service.files().create(body=metadata, fields="id").execute()["id"]

    def get_employee_folder(self, employee):
        if not self.connect():
            return None
        return self.get_or_create_folder(safe_name(employee), self.root_folder_id)

    def upload_file(self, file_path, employee):
        if not self.connect():
            return None, None
        folder_id = self.get_employee_folder(employee)
        if not folder_id:
            return None, None

        source = Path(file_path)
        mime_type = mimetypes.guess_type(str(source))[0] or "application/octet-stream"
        name = f"{datetime.now():%Y%m%d_%H%M%S}_{source.name}"
        metadata = {"name": name, "parents": [folder_id]}
        media = MediaFileUpload(str(source), mimetype=mime_type, resumable=True)

        try:
            uploaded = self.service.files().create(
                body=metadata, media_body=media,
                fields="id,name,webViewLink"
            ).execute()
            file_id = uploaded["id"]
            url = uploaded.get(
                "webViewLink",
                f"https://drive.google.com/file/d/{file_id}/view"
            )
            return file_id, url
        except (HttpError, Exception) as exc:
            print("\nCould not upload the file to Google Drive.")
            print(exc)
            return None, None


# =========================
# DATABASE
# =========================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.create_tables()

    def create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_no TEXT UNIQUE NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT, phone TEXT, department TEXT, position TEXT,
                date_of_birth TEXT, address TEXT,
                status TEXT NOT NULL DEFAULT 'Pending',
                hr_notes TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                item TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                document_type TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                google_drive_file_id TEXT DEFAULT '',
                google_drive_url TEXT DEFAULT '',
                verification_status TEXT NOT NULL DEFAULT 'Pending',
                uploaded_at TEXT NOT NULL,
                FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
            );
        """)
        self.add_missing_columns()
        self.remove_duplicate_checklist_items()
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_checklist_employee_item ON checklist(employee_id, item)
        """)
        self.add_missing_checklist_items()

    def add_missing_columns(self):
        columns = {
            "employees": {"date_of_birth": "TEXT", "address": "TEXT"},
            "documents": {
                "google_drive_file_id": "TEXT DEFAULT ''",
                "google_drive_url": "TEXT DEFAULT ''"
            }
        }
        for table, fields in columns.items():
            existing = {
                row["name"]
                for row in self.conn.execute(f"PRAGMA table_info({table})")
            }
            for name, data_type in fields.items():
                if name not in existing:
                    try:
                        self.conn.execute(
                            f"ALTER TABLE {table} ADD COLUMN {name} {data_type}"
                        )
                    except sqlite3.OperationalError:
                        pass
        self.conn.commit()

    def remove_duplicate_checklist_items(self):
        duplicates = self.conn.execute("""
            SELECT employee_id, item, MIN(id) AS keep_id
            FROM checklist
            GROUP BY employee_id, item
            HAVING COUNT(*) > 1
        """).fetchall()
        for row in duplicates:
            self.conn.execute(
                "DELETE FROM checklist WHERE employee_id=? AND item=? AND id<>?",
                (row["employee_id"], row["item"], row["keep_id"])
            )
        self.conn.commit()

    def add_missing_checklist_items(self):
        employees = self.conn.execute("SELECT id FROM employees").fetchall()
        for employee in employees:
            existing = {
                row["item"] for row in self.conn.execute(
                    "SELECT item FROM checklist WHERE employee_id=?",
                    (employee["id"],)
                )
            }
            for item in CHECKLIST_ITEMS:
                if item not in existing:
                    self.conn.execute(
                        "INSERT INTO checklist(employee_id,item) VALUES(?,?)",
                        (employee["id"], item)
                    )
        self.conn.commit()

    # ---------- Employees ----------
    def add_employee(self, data):
        cur = self.conn.execute("""
            INSERT INTO employees
            (employee_no, first_name, last_name, email, phone, department,
             position, date_of_birth, address, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["employee_no"], data["first_name"], data["last_name"],
            data["email"], data["phone"], data["department"], data["position"],
            data["date_of_birth"], data["address"],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        for item in CHECKLIST_ITEMS:
            self.conn.execute(
                "INSERT INTO checklist(employee_id,item) VALUES(?,?)",
                (cur.lastrowid, item)
            )
        self.conn.commit()
        return cur.lastrowid

    def update_employee(self, employee_id, data):
        self.conn.execute("""
            UPDATE employees SET first_name=?, last_name=?, email=?, phone=?,
            department=?, position=?, date_of_birth=?, address=? WHERE id=?
        """, (
            data["first_name"], data["last_name"], data["email"], data["phone"],
            data["department"], data["position"], data["date_of_birth"],
            data["address"], employee_id
        ))
        self.conn.commit()

    def delete_employee(self, employee_id):
        # Deletes only database records. Google Drive and local files remain.
        self.conn.execute("DELETE FROM employees WHERE id=?", (employee_id,))
        self.conn.commit()

    def employees(self, search=""):
        if search.strip():
            q = f"%{search.strip()}%"
            return self.conn.execute("""
                SELECT * FROM employees
                WHERE employee_no LIKE ? OR first_name LIKE ? OR last_name LIKE ?
                OR department LIKE ? OR position LIKE ?
                ORDER BY id DESC
            """, (q, q, q, q, q)).fetchall()
        return self.conn.execute(
            "SELECT * FROM employees ORDER BY id DESC"
        ).fetchall()

    def get_employee(self, employee_id):
        return self.conn.execute(
            "SELECT * FROM employees WHERE id=?", (employee_id,)
        ).fetchone()

    def get_employee_by_number(self, employee_no):
        return self.conn.execute(
            "SELECT * FROM employees WHERE employee_no=?", (employee_no,)
        ).fetchone()

    def update_status(self, employee_id, status, notes=""):
        self.conn.execute(
            "UPDATE employees SET status=?, hr_notes=? WHERE id=?",
            (status, notes, employee_id)
        )
        self.conn.commit()

    # ---------- Checklist ----------
    def get_checklist(self, employee_id):
        return self.conn.execute(
            "SELECT * FROM checklist WHERE employee_id=? ORDER BY id",
            (employee_id,)
        ).fetchall()

    def set_checklist(self, item_id, completed):
        self.conn.execute(
            "UPDATE checklist SET completed=? WHERE id=?",
            (int(completed), item_id)
        )
        self.conn.commit()

    # ---------- Documents ----------
    def get_documents(self, employee_id):
        return self.conn.execute(
            "SELECT * FROM documents WHERE employee_id=? ORDER BY id DESC",
            (employee_id,)
        ).fetchall()

    def get_document(self, document_id):
        return self.conn.execute(
            "SELECT * FROM documents WHERE id=?", (document_id,)
        ).fetchone()

    def add_document(self, employee_id, document_type, original_name,
                     stored_path, drive_id="", drive_url=""):
        self.conn.execute("""
            INSERT INTO documents
            (employee_id, document_type, original_name, stored_path,
             google_drive_file_id, google_drive_url,
             verification_status, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, 'Pending', ?)
        """, (
            employee_id, document_type, original_name, stored_path,
            drive_id, drive_url, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        self.conn.commit()

    def update_document_status(self, document_id, status):
        self.conn.execute(
            "UPDATE documents SET verification_status=? WHERE id=?",
            (status, document_id)
        )
        self.conn.commit()

    def stats(self):
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS count FROM employees GROUP BY status"
        ).fetchall()
        stats = {row["status"]: row["count"] for row in rows}
        return (
            sum(stats.values()), stats.get("Pending", 0),
            stats.get("Approved", 0), stats.get("Revision Requested", 0)
        )


# =========================
# APPLICATION
# =========================
class OnboardingCLI:
    def __init__(self):
        self.db = Database()
        self.drive = GoogleDriveManager()

    def run(self):
        actions = {
            "1": self.view_credentials,
            "2": self.complete_update_credentials,
            "3": self.onboarding_checklist,
            "4": self.credential_id_menu,
            "5": self.hr_review,
            "6": self.dashboard,
            "7": self.remove_employee
        }
        while True:
            header("EMPLOYEE ONBOARDING & DOCUMENT VERIFICATION")
            print("1. View credentials")
            print("2. Complete/update credentials")
            print("3. Onboarding checklist")
            print("4. Credential ID")
            print("5. HR review")
            print("6. Dashboard")
            print("7. Remove employee")
            print("8. Sign out")
            choice = input("\nChoose an option: ").strip()

            if choice == "8":
                self.sign_out()
                break
            action = actions.get(choice)
            if action:
                action()
            else:
                print("\nInvalid option.")
                pause()

    # ---------- Employee Selection ----------
    def select_employee(self):
        employees = self.db.employees()
        if not employees:
            print("No employees have been registered yet.")
            pause()
            return None

        print("\n--- Employee List ---")
        for employee in employees:
            print(
                f"{employee['id']}. {employee['employee_no']} - "
                f"{employee['first_name']} {employee['last_name']}"
            )
        value = input("\nEnter Employee No. or ID: ").strip()

        employee = self.db.get_employee_by_number(value)
        if employee:
            return employee
        if value.isdigit():
            employee = self.db.get_employee(int(value))
            if employee:
                return employee
        print("\nEmployee not found.")
        pause()
        return None

    # ---------- Remove Employee ----------
    def remove_employee(self):
        header("REMOVE EMPLOYEE")
        employee = self.select_employee()
        if not employee:
            return

        print("\nEmployee selected:")
        show_employee(employee)
        print("\nWARNING: This removes the employee from the local database.")
        print("Google Drive files will NOT be deleted.")
        print("Local document files will NOT be deleted.")

        if input("\nType REMOVE to confirm: ").strip() != "REMOVE":
            print("\nEmployee removal cancelled.")
            pause()
            return

        try:
            self.db.delete_employee(employee["id"])
            print("\nEmployee removed successfully.")
            print("Google Drive files were not deleted.")
            print("Local document files were not deleted.")
        except sqlite3.Error as exc:
            print("\nERROR: Could not remove employee.")
            print(exc)
        pause()

    # ---------- Credentials ----------
    def view_credentials(self):
        header("VIEW CREDENTIALS")
        employee = self.select_employee()
        if not employee:
            return
        header("YOUR CREDENTIALS")
        print("--- Employee Information ---\n")
        show_employee(employee)
        print("\n--- Credential Documents ---")
        self.print_documents(employee["id"])
        pause()

    def complete_update_credentials(self):
        header("COMPLETE / UPDATE CREDENTIALS")
        employee = self.select_employee()
        if employee:
            self.update_employee(employee)
        elif input("\nWould you like to create a new employee? (y/n): ").strip().lower() == "y":
            self.add_employee()

    def add_employee(self):
        header("NEW EMPLOYEE")
        print("Enter employee information.\n")
        data = {
            "employee_no": get_input("Employee No.: ", True),
            "first_name": get_input("First name: ", True),
            "last_name": get_input("Last name: ", True),
            "email": get_input("Email: "),
            "phone": get_input("Phone number: "),
            "department": get_input("Department: "),
            "position": get_input("Position: "),
            "date_of_birth": get_input("Date of birth (YYYY-MM-DD): "),
            "address": get_input("Home address: ")
        }
        try:
            employee_id = self.db.add_employee(data)
            print("\nEmployee successfully registered.")
            print(f"Employee ID: {employee_id}")
            print("\nRequired documents:")
            for doc in REQUIRED_DOCUMENTS:
                print(f"- {doc}")
        except sqlite3.IntegrityError:
            print("\nERROR: That Employee No. already exists.")
        pause()

    def update_employee(self, employee):
        header("UPDATE EMPLOYEE")
        print(f"Employee: {employee['first_name']} {employee['last_name']}\n")
        print("Press Enter to keep the existing value.\n")
        fields = [
            ("first_name", "First name"), ("last_name", "Last name"),
            ("email", "Email"), ("phone", "Phone"),
            ("department", "Department"), ("position", "Position"),
            ("date_of_birth", "Date of birth"), ("address", "Home address")
        ]
        data = {}
        for key, label in fields:
            old = employee[key] or "N/A"
            value = input(f"{label} [{old}]: ").strip()
            data[key] = value or employee[key]
        self.db.update_employee(employee["id"], data)
        print("\nEmployee information updated successfully.")
        pause()

    # ---------- Checklist ----------
    def onboarding_checklist(self):
        employee = self.select_employee()
        if not employee:
            return
        while True:
            header("ONBOARDING CHECKLIST")
            print(f"Employee: {employee['first_name']} {employee['last_name']}\n")
            checklist = self.db.get_checklist(employee["id"])
            for i, item in enumerate(checklist, 1):
                mark = "X" if item["completed"] else " "
                print(f"{i}. [{mark}] {item['item']}")
            print("\nEnter the item number to change.")
            print("0. Back")
            choice = input("\nChoose an option: ").strip()
            if choice == "0":
                break
            if not choice.isdigit() or not 1 <= int(choice) <= len(checklist):
                print("Invalid checklist item.")
                pause()
                continue
            item = checklist[int(choice) - 1]
            new_status = not bool(item["completed"])
            self.db.set_checklist(item["id"], new_status)
            print(
                f"\n{'Marked complete' if new_status else 'Marked incomplete'}: "
                f"{item['item']}"
            )
            pause()

    # ---------- Documents ----------
    def credential_id_menu(self):
        employee = self.select_employee()
        if not employee:
            return
        while True:
            header("CREDENTIAL ID")
            print(f"Employee: {employee['first_name']} {employee['last_name']}\n")
            documents = self.db.get_documents(employee["id"])
            if documents:
                for doc in documents:
                    print(f"{doc['id']}. {doc['document_type']} - {doc['verification_status']}")
            else:
                print("No credential documents have been submitted.")
            print("\n1. View credential")
            print("2. Attach Image/PDF")
            print("3. Back")
            choice = input("\nChoose an option: ").strip()

            if choice == "1":
                if not documents:
                    print("\nThere are no credentials to view.")
                    pause()
                    continue
                value = input("Enter Credential ID: ").strip()
                if value.isdigit():
                    self.view_credential(int(value))
                else:
                    print("Invalid Credential ID.")
                    pause()
            elif choice == "2":
                self.upload_document(employee)
            elif choice == "3":
                break
            else:
                print("Invalid option.")
                pause()

    def print_documents(self, employee_id):
        documents = self.db.get_documents(employee_id)
        if not documents:
            print("No documents have been submitted.")
            return
        for doc in documents:
            print(f"\nCredential ID: {doc['id']}")
            print(f"Type:           {doc['document_type']}")
            print(f"File:           {doc['original_name']}")
            print(f"Status:         {doc['verification_status']}")
            print(f"Submitted:      {doc['uploaded_at']}")
            if doc["google_drive_url"]:
                print(f"Google Drive:   {doc['google_drive_url']}")

    def view_credential(self, document_id):
        document = self.db.get_document(document_id)
        if not document:
            print("\nCredential ID not found.")
            pause()
            return
        header("CREDENTIAL ID")
        print(f"Credential ID: {document['id']}")
        print(f"Status:        {document['verification_status']}")
        print(f"Type:          {document['document_type']}")
        print(f"Submitted:     {document['uploaded_at']}")
        print(f"File:          {document['original_name']}")
        print(f"Local path:    {document['stored_path']}")
        if document["google_drive_url"]:
            print(f"Google Drive:  {document['google_drive_url']}")
        print("\n1. Attach a clearer/replacement file")
        print("2. Back")
        if input("\nChoose an option: ").strip() == "1":
            employee = self.db.get_employee(document["employee_id"])
            self.upload_document(employee)

    def upload_document(self, employee):
        header("ATTACH IMAGE / PDF")
        print(f"Employee: {employee['first_name']} {employee['last_name']}\n")
        print("--- Required Document Type ---")
        for i, doc_type in enumerate(REQUIRED_DOCUMENTS, 1):
            print(f"{i}. {doc_type}")
        choice = input("\nChoose document type: ").strip()
        if not choice.isdigit() or not 1 <= int(choice) <= len(REQUIRED_DOCUMENTS):
            print("Invalid document type.")
            pause()
            return

        document_type = REQUIRED_DOCUMENTS[int(choice) - 1]
        print("\nOpening file picker...")
        file_path = select_file()
        if not file_path:
            print("\nNo file selected.")
            pause()
            return

        source = Path(file_path)
        if not source.exists() or not source.is_file():
            print("\nERROR: The selected file is invalid.")
            pause()
            return
        if source.suffix.lower() not in ALLOWED_EXTENSIONS:
            print("\nERROR: Only JPG, JPEG, PNG and PDF files are allowed.")
            pause()
            return

        folder = DOC_DIR / safe_name(employee)
        folder.mkdir(parents=True, exist_ok=True)
        original_name = source.name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = folder / f"{timestamp}_{original_name}"

        try:
            shutil.copy2(source, destination)
        except OSError as exc:
            print("\nERROR: Could not copy the document.")
            print(exc)
            pause()
            return

        drive_id = drive_url = ""
        print("\nUploading document to Google Drive...")
        try:
            drive_id, drive_url = self.drive.upload_file(destination, employee)
        except Exception as exc:
            print("\nGoogle Drive upload failed.")
            print(exc)

        try:
            self.db.add_document(
                employee["id"], document_type, original_name,
                str(destination), drive_id or "", drive_url or ""
            )
            print("\nCredential uploaded successfully.")
            print(f"Credential Type: {document_type}")
            print(f"File: {original_name}")
            print("Verification Status: Pending")
            if drive_url:
                print("\nGoogle Drive upload: SUCCESS")
                print(f"Drive URL: {drive_url}")
            else:
                print("\nGoogle Drive upload: NOT AVAILABLE")
                print("The local copy was still saved.")
        except sqlite3.Error as exc:
            print("\nERROR: Could not save document record.")
            print(exc)
        pause()

    # ---------- HR Review ----------
    def hr_review(self):
        employee = self.select_employee()
        if not employee:
            return
        while True:
            header("HR REVIEW")
            print(f"Employee: {employee['first_name']} {employee['last_name']}")
            print(f"Current status: {employee['status']}\n")
            print("1. View documents")
            print("2. Verify document")
            print("3. Request document revision")
            print("4. Approve employee")
            print("5. Request onboarding revision")
            print("6. Set Pending")
            print("7. Add HR notes")
            print("8. Back")
            choice = input("\nChoose an option: ").strip()

            if choice == "1":
                self.view_employee_documents(employee)
            elif choice == "2":
                self.verify_document(employee, "Verified")
            elif choice == "3":
                self.verify_document(employee, "Revision Required")
            elif choice == "4":
                self.approve_employee(employee)
            elif choice == "5":
                self.change_status(employee, "Revision Requested")
            elif choice == "6":
                self.change_status(employee, "Pending")
            elif choice == "7":
                self.add_hr_notes(employee)
            elif choice == "8":
                break
            else:
                print("Invalid option.")
                pause()
            employee = self.db.get_employee(employee["id"])

    def view_employee_documents(self, employee):
        header("EMPLOYEE DOCUMENTS")
        self.print_documents(employee["id"])
        pause()

    def verify_document(self, employee, status):
        documents = self.db.get_documents(employee["id"])
        if not documents:
            print("\nThis employee has no documents.")
            pause()
            return

        print()
        for doc in documents:
            print(
                f"{doc['id']}. {doc['document_type']} - "
                f"{doc['original_name']} - {doc['verification_status']}"
            )
        value = input("\nEnter Credential ID: ").strip()
        if not value.isdigit():
            print("Invalid Credential ID.")
            pause()
            return

        document = self.db.get_document(int(value))
        if not document:
            print("Credential ID not found.")
            pause()
            return
        if document["employee_id"] != employee["id"]:
            print("That credential does not belong to this employee.")
            pause()
            return

        self.db.update_document_status(document["id"], status)
        print(f"\nCredential ID {document['id']} status updated to: {status}")
        pause()

    def approve_employee(self, employee):
        checklist = self.db.get_checklist(employee["id"])
        documents = self.db.get_documents(employee["id"])
        incomplete = [item for item in checklist if not item["completed"]]
        submitted = {doc["document_type"] for doc in documents}
        missing = [doc for doc in REQUIRED_DOCUMENTS if doc not in submitted]
        unverified = [
            doc for doc in documents
            if doc["document_type"] in REQUIRED_DOCUMENTS
            and doc["verification_status"] != "Verified"
        ]

        if incomplete:
            print(f"\n{len(incomplete)} checklist item(s) are incomplete.")
        if missing:
            print("\nMissing required documents:")
            for doc in missing:
                print(f"- {doc}")
        if unverified:
            print("\nDocuments that still need verification:")
            for doc in unverified:
                print(f"- {doc['document_type']} (Credential ID: {doc['id']})")

        if incomplete or missing or unverified:
            print("\nEmployee cannot be approved yet.")
            print("All required documents must be submitted and verified.")
            pause()
            return

        self.db.update_status(
            employee["id"], "Approved", employee["hr_notes"] or ""
        )
        print("\nEmployee has been approved.")
        print("All required documents have been submitted and verified.")
        pause()

    def change_status(self, employee, status):
        self.db.update_status(
            employee["id"], status, employee["hr_notes"] or ""
        )
        print(f"\nEmployee status changed to: {status}")
        pause()

    def add_hr_notes(self, employee):
        header("HR NOTES")
        print("Current notes:")
        print(employee["hr_notes"] or "No notes available.")
        notes = input("\nEnter new HR notes: ").strip()
        self.db.update_status(employee["id"], employee["status"], notes)
        print("\nHR notes saved.")
        pause()

    # ---------- Dashboard ----------
    def dashboard(self):
        header("DASHBOARD")
        total, pending, approved, revision = self.db.stats()
        print(f"Total Employees:       {total}")
        print(f"Pending:               {pending}")
        print(f"Approved:              {approved}")
        print(f"Revision Requested:    {revision}")
        print(
            "\nEmployee onboarding system is active."
            if total else "\nNo employees have been registered."
        )
        pause()

    # ---------- Sign Out ----------
    def sign_out(self):
        header("SIGN OUT")
        print("You have successfully signed out.")
        print("\nThank you for using the Employee Onboarding System.")


# =========================
# START
# =========================
if __name__ == "__main__":
    try:
        OnboardingCLI().run()
    except KeyboardInterrupt:
        print("\n\nProgram closed.")