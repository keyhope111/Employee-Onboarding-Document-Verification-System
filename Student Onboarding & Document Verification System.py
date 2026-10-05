import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sqlite3
import shutil
import os
import sys
import hashlib
import secrets
from pathlib import Path
from datetime import datetime


# ============================================================
# APPLICATION DIRECTORIES
# ============================================================

APP_DIR = Path(__file__).resolve().parent

DATA_DIR = APP_DIR / "employee_data"
DOC_DIR = DATA_DIR / "documents"
DB_PATH = DATA_DIR / "onboarding.db"

DATA_DIR.mkdir(exist_ok=True)
DOC_DIR.mkdir(exist_ok=True)


# ============================================================
# ONBOARDING CHECKLIST
# ============================================================

CHECKLIST_ITEMS = [
    "Submit personal information",
    "Submit valid government ID",
    "Submit NBI/Police Clearance",
    "Submit proof of address",
    "Submit educational credentials",
    "Submit employment documents",
    "Complete company orientation",
    "Sign employment agreement",
]


# ============================================================
# DOCUMENT TYPES
# ============================================================

DOCUMENT_TYPES = [
    "Government ID",
    "NBI Clearance",
    "Police Clearance",
    "Proof of Address",
    "Educational Credential",
    "Employment Document",
    "Other Compliance Document",
]


# ============================================================
# DOCUMENT -> CHECKLIST MAPPING
# ============================================================

DOCUMENT_CHECKLIST_MAP = {
    "Government ID": "Submit valid government ID",
    "NBI Clearance": "Submit NBI/Police Clearance",
    "Police Clearance": "Submit NBI/Police Clearance",
    "Proof of Address": "Submit proof of address",
    "Educational Credential": "Submit educational credentials",
    "Employment Document": "Submit employment documents",
}


# ============================================================
# PASSWORD FUNCTIONS
# ============================================================

def hash_password(password, salt=None):

    if salt is None:
        salt = secrets.token_bytes(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        100_000
    )

    return (
        password_hash.hex(),
        salt.hex()
    )


def verify_password(password, stored_hash, stored_salt):

    try:
        salt = bytes.fromhex(stored_salt)

        password_hash, _ = hash_password(
            password,
            salt
        )

        return secrets.compare_digest(
            password_hash,
            stored_hash
        )

    except Exception:
        return False


# ============================================================
# DATABASE
# ============================================================

class Database:

    def __init__(self):

        self.conn = sqlite3.connect(DB_PATH)

        self.conn.row_factory = sqlite3.Row

        self.conn.execute(
            "PRAGMA foreign_keys = ON"
        )

        self.create_tables()

        self.create_default_hr_account()

    # --------------------------------------------------------
    # CREATE TABLES
    # --------------------------------------------------------

    def create_tables(self):

        cur = self.conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_no TEXT UNIQUE NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                department TEXT,
                position TEXT,
                status TEXT NOT NULL DEFAULT 'Pending',
                hr_notes TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS checklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                item TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(employee_id)
                    REFERENCES employees(id)
                    ON DELETE CASCADE
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                document_type TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                verification_status TEXT NOT NULL DEFAULT 'Pending',
                uploaded_at TEXT NOT NULL,
                FOREIGN KEY(employee_id)
                    REFERENCES employees(id)
                    ON DELETE CASCADE
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                role TEXT NOT NULL,
                employee_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(employee_id)
                    REFERENCES employees(id)
                    ON DELETE CASCADE
            )
        """)

        self.conn.commit()

    # --------------------------------------------------------
    # DEFAULT HR ACCOUNT
    # --------------------------------------------------------

    def create_default_hr_account(self):

        existing = self.conn.execute(
            """
            SELECT id
            FROM users
            WHERE username=?
            """,
            ("admin",)
        ).fetchone()

        if existing:
            return

        password_hash, salt = hash_password(
            "admin123"
        )

        self.conn.execute("""
            INSERT INTO users
            (
                username,
                password_hash,
                password_salt,
                role,
                employee_id,
                created_at
            )
            VALUES (?, ?, ?, 'HR', NULL, ?)
        """, (
            "admin",
            password_hash,
            salt,
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        ))

        self.conn.commit()

    # --------------------------------------------------------
    # LOGIN
    # --------------------------------------------------------

    def authenticate(
        self,
        username,
        password
    ):

        user = self.conn.execute(
            """
            SELECT *
            FROM users
            WHERE username=?
            """,
            (username.strip(),)
        ).fetchone()

        if not user:
            return None

        if not verify_password(
            password,
            user["password_hash"],
            user["password_salt"]
        ):
            return None

        return user

    # --------------------------------------------------------
    # CREATE EMPLOYEE LOGIN
    # --------------------------------------------------------

    def create_employee_login(
        self,
        employee_id,
        username,
        password
    ):

        username = username.strip().lower()

        existing = self.conn.execute(
            """
            SELECT id
            FROM users
            WHERE username=?
            """,
            (username,)
        ).fetchone()

        password_hash, salt = hash_password(
            password
        )

        if existing:

            self.conn.execute("""
                UPDATE users
                SET password_hash=?,
                    password_salt=?,
                    role='Employee',
                    employee_id=?
                WHERE id=?
            """, (
                password_hash,
                salt,
                employee_id,
                existing["id"]
            ))

        else:

            self.conn.execute("""
                INSERT INTO users
                (
                    username,
                    password_hash,
                    password_salt,
                    role,
                    employee_id,
                    created_at
                )
                VALUES (?, ?, ?, 'Employee', ?, ?)
            """, (
                username,
                password_hash,
                salt,
                employee_id,
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            ))

        self.conn.commit()

    # --------------------------------------------------------
    # GET EMPLOYEE USER
    # --------------------------------------------------------

    def get_employee_user(
        self,
        employee_id
    ):

        return self.conn.execute("""
            SELECT *
            FROM users
            WHERE employee_id=?
              AND role='Employee'
            LIMIT 1
        """, (
            employee_id,
        )).fetchone()

    # --------------------------------------------------------
    # ADD EMPLOYEE
    # --------------------------------------------------------

    def add_employee(self, data):

        cur = self.conn.cursor()

        cur.execute("""
            INSERT INTO employees
            (
                employee_no,
                first_name,
                last_name,
                email,
                phone,
                department,
                position,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["employee_no"],
            data["first_name"],
            data["last_name"],
            data["email"],
            data["phone"],
            data["department"],
            data["position"],
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        ))

        employee_id = cur.lastrowid

        for item in CHECKLIST_ITEMS:

            cur.execute("""
                INSERT INTO checklist
                (
                    employee_id,
                    item
                )
                VALUES (?, ?)
            """, (
                employee_id,
                item
            ))

        self.conn.commit()

        # Automatically create employee account
        username = data["employee_no"].strip().lower()

        self.create_employee_login(
            employee_id,
            username,
            "welcome123"
        )

        return employee_id

    # --------------------------------------------------------
    # GET EMPLOYEES
    # --------------------------------------------------------

    def employees(self, search=""):

        if search.strip():

            q = f"%{search.strip()}%"

            return self.conn.execute("""
                SELECT *
                FROM employees
                WHERE employee_no LIKE ?
                   OR first_name LIKE ?
                   OR last_name LIKE ?
                   OR department LIKE ?
                   OR position LIKE ?
                ORDER BY id DESC
            """, (
                q,
                q,
                q,
                q,
                q
            )).fetchall()

        return self.conn.execute("""
            SELECT *
            FROM employees
            ORDER BY id DESC
        """).fetchall()

    # --------------------------------------------------------
    # GET SINGLE EMPLOYEE
    # --------------------------------------------------------

    def get_employee(
        self,
        employee_id
    ):

        return self.conn.execute("""
            SELECT *
            FROM employees
            WHERE id=?
        """, (
            employee_id,
        )).fetchone()

    # --------------------------------------------------------
    # CHECKLIST
    # --------------------------------------------------------

    def get_checklist(
        self,
        employee_id
    ):

        return self.conn.execute("""
            SELECT *
            FROM checklist
            WHERE employee_id=?
            ORDER BY id
        """, (
            employee_id,
        )).fetchall()

    def set_checklist(
        self,
        item_id,
        completed
    ):

        self.conn.execute("""
            UPDATE checklist
            SET completed=?
            WHERE id=?
        """, (
            1 if completed else 0,
            item_id
        ))

        self.conn.commit()

    def complete_checklist_item(
        self,
        employee_id,
        item_name
    ):

        self.conn.execute("""
            UPDATE checklist
            SET completed=1
            WHERE employee_id=?
              AND item=?
        """, (
            employee_id,
            item_name
        ))

        self.conn.commit()

    # --------------------------------------------------------
    # DOCUMENTS
    # --------------------------------------------------------

    def get_documents(
        self,
        employee_id
    ):

        return self.conn.execute("""
            SELECT *
            FROM documents
            WHERE employee_id=?
            ORDER BY id DESC
        """, (
            employee_id,
        )).fetchall()

    # --------------------------------------------------------
    # SINGLE DOCUMENT
    # --------------------------------------------------------

    def get_document(
        self,
        document_id
    ):

        return self.conn.execute("""
            SELECT *
            FROM documents
            WHERE id=?
        """, (
            document_id,
        )).fetchone()

    # --------------------------------------------------------
    # ADD DOCUMENT
    # --------------------------------------------------------

    def add_document(
        self,
        employee_id,
        document_type,
        original_name,
        stored_path
    ):

        self.conn.execute("""
            INSERT INTO documents
            (
                employee_id,
                document_type,
                original_name,
                stored_path,
                verification_status,
                uploaded_at
            )
            VALUES (?, ?, ?, ?, 'Pending', ?)
        """, (
            employee_id,
            document_type,
            original_name,
            stored_path,
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        ))

        self.conn.commit()

    # --------------------------------------------------------
    # DOCUMENT STATUS
    # --------------------------------------------------------

    def update_document_status(
        self,
        document_id,
        status
    ):

        self.conn.execute("""
            UPDATE documents
            SET verification_status=?
            WHERE id=?
        """, (
            status,
            document_id
        ))

        self.conn.commit()

    # --------------------------------------------------------
    # EMPLOYEE STATUS
    # --------------------------------------------------------

    def update_employee_status(
        self,
        employee_id,
        status,
        notes=""
    ):

        self.conn.execute("""
            UPDATE employees
            SET status=?,
                hr_notes=?
            WHERE id=?
        """, (
            status,
            notes,
            employee_id
        ))

        self.conn.commit()

    # --------------------------------------------------------
    # STATISTICS
    # --------------------------------------------------------

    def stats(self):

        total = self.conn.execute(
            "SELECT COUNT(*) FROM employees"
        ).fetchone()[0]

        pending = self.conn.execute("""
            SELECT COUNT(*)
            FROM employees
            WHERE status='Pending'
        """).fetchone()[0]

        approved = self.conn.execute("""
            SELECT COUNT(*)
            FROM employees
            WHERE status='Approved'
        """).fetchone()[0]

        revision = self.conn.execute("""
            SELECT COUNT(*)
            FROM employees
            WHERE status='Revision Requested'
        """).fetchone()[0]

        return (
            total,
            pending,
            approved,
            revision
        )


# ============================================================
# LOGIN WINDOW
# ============================================================

class LoginWindow(tk.Tk):

    def __init__(self):

        super().__init__()

        self.title(
            "Employee Onboarding System - Login"
        )

        self.geometry(
            "500x430"
        )

        self.resizable(
            False,
            False
        )

        self.configure(
            bg="#1f2937"
        )

        self.db = Database()

        self.build_ui()

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------

    def build_ui(self):

        container = tk.Frame(
            self,
            bg="white"
        )

        container.place(
            relx=0.5,
            rely=0.5,
            anchor="center",
            width=400,
            height=350
        )

        tk.Label(
            container,
            text="Employee Onboarding",
            bg="white",
            fg="#111827",
            font=(
                "Segoe UI",
                20,
                "bold"
            )
        ).pack(
            pady=(30, 5)
        )

        tk.Label(
            container,
            text="Document Verification System",
            bg="white",
            fg="#6b7280",
            font=(
                "Segoe UI",
                10
            )
        ).pack(
            pady=(0, 25)
        )

        form = tk.Frame(
            container,
            bg="white"
        )

        form.pack(
            padx=40,
            fill="x"
        )

        tk.Label(
            form,
            text="Username",
            bg="white",
            anchor="w"
        ).pack(
            fill="x"
        )

        self.username_var = tk.StringVar()

        username_entry = ttk.Entry(
            form,
            textvariable=self.username_var
        )

        username_entry.pack(
            fill="x",
            pady=(5, 12)
        )

        tk.Label(
            form,
            text="Password",
            bg="white",
            anchor="w"
        ).pack(
            fill="x"
        )

        self.password_var = tk.StringVar()

        password_entry = ttk.Entry(
            form,
            textvariable=self.password_var,
            show="*"
        )

        password_entry.pack(
            fill="x",
            pady=(5, 15)
        )

        password_entry.bind(
            "<Return>",
            lambda event: self.login()
        )

        ttk.Button(
            form,
            text="Login",
            command=self.login
        ).pack(
            fill="x",
            ipady=5
        )

        tk.Label(
            container,
            text=(
                "Demo HR account: admin / admin123\n"
                "Employee accounts: Employee No. / welcome123"
            ),
            bg="white",
            fg="#6b7280",
            font=(
                "Segoe UI",
                9
            )
        ).pack(
            pady=18
        )

        username_entry.focus()

    # --------------------------------------------------------
    # LOGIN
    # --------------------------------------------------------

    def login(self):

        username = self.username_var.get().strip()
        password = self.password_var.get()

        if not username or not password:

            messagebox.showwarning(
                "Missing Login",
                "Please enter your username and password."
            )

            return

        user = self.db.authenticate(
            username,
            password
        )

        if not user:

            messagebox.showerror(
                "Login Failed",
                "Invalid username or password."
            )

            return

        self.withdraw()

        if user["role"] == "HR":

            app = OnboardingApp(
                self.db,
                self
            )

        else:

            if not user["employee_id"]:

                messagebox.showerror(
                    "Account Error",
                    "This employee account is not connected "
                    "to an employee record."
                )

                self.deiconify()

                return

            app = EmployeePortal(
                self.db,
                self,
                user["employee_id"]
            )

        app.protocol(
            "WM_DELETE_WINDOW",
            app.logout
        )

        app.mainloop()


# ============================================================
# HR APPLICATION
# ============================================================

class OnboardingApp(tk.Tk):

    def __init__(
        self,
        db,
        login_window
    ):

        super().__init__()

        self.db = db
        self.login_window = login_window

        self.title(
            "Employee Onboarding & Document Verification System"
        )

        self.geometry(
            "1250x760"
        )

        self.minsize(
            1100,
            650
        )

        self.selected_employee_id = None

        self.configure(
            bg="#f3f4f6"
        )

        self.style = ttk.Style(self)

        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.style.configure(
            "Treeview",
            rowheight=28,
            font=("Segoe UI", 10)
        )

        self.style.configure(
            "Treeview.Heading",
            font=("Segoe UI", 10, "bold")
        )

        self.style.configure(
            "TButton",
            font=("Segoe UI", 10)
        )

        self.style.configure(
            "Header.TLabel",
            font=("Segoe UI", 18, "bold")
        )

        self.style.configure(
            "Sub.TLabel",
            font=("Segoe UI", 10)
        )

        self.create_ui()

        self.refresh_all()

    # ========================================================
    # MAIN UI
    # ========================================================

    def create_ui(self):

        header = tk.Frame(
            self,
            bg="#1f2937",
            height=70
        )

        header.pack(
            fill="x"
        )

        tk.Label(
            header,
            text="Employee Onboarding & Document Verification",
            bg="#1f2937",
            fg="white",
            font=(
                "Segoe UI",
                18,
                "bold"
            )
        ).pack(
            side="left",
            padx=22,
            pady=17
        )

        ttk.Button(
            header,
            text="Logout",
            command=self.logout
        ).pack(
            side="right",
            padx=20
        )

        tk.Label(
            header,
            text="HR Management System",
            bg="#1f2937",
            fg="#d1d5db",
            font=(
                "Segoe UI",
                10
            )
        ).pack(
            side="right",
            padx=10
        )

        self.notebook = ttk.Notebook(self)

        self.notebook.pack(
            fill="both",
            expand=True,
            padx=12,
            pady=12
        )

        self.dashboard_tab = ttk.Frame(
            self.notebook
        )

        self.employee_tab = ttk.Frame(
            self.notebook
        )

        self.details_tab = ttk.Frame(
            self.notebook
        )

        self.notebook.add(
            self.dashboard_tab,
            text="Dashboard"
        )

        self.notebook.add(
            self.employee_tab,
            text="Employees"
        )

        self.notebook.add(
            self.details_tab,
            text="Onboarding Details"
        )

        self.build_dashboard()
        self.build_employees()
        self.build_details()

    # ========================================================
    # DASHBOARD
    # ========================================================

    def build_dashboard(self):

        frame = self.dashboard_tab

        ttk.Label(
            frame,
            text="HR Dashboard",
            style="Header.TLabel"
        ).pack(
            anchor="w",
            padx=20,
            pady=(20, 4)
        )

        ttk.Label(
            frame,
            text=(
                "Monitor employee onboarding and "
                "document verification."
            ),
            style="Sub.TLabel"
        ).pack(
            anchor="w",
            padx=20,
            pady=(0, 20)
        )

        cards = tk.Frame(
            frame,
            bg="#f3f4f6"
        )

        cards.pack(
            fill="x",
            padx=20
        )

        self.stat_labels = {}

        for key, title in [
            ("total", "Total Employees"),
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("revision", "Revision Requested")
        ]:

            card = tk.Frame(
                cards,
                bg="white",
                bd=1,
                relief="solid"
            )

            card.pack(
                side="left",
                fill="x",
                expand=True,
                padx=6,
                ipady=12
            )

            tk.Label(
                card,
                text=title,
                bg="white",
                fg="#6b7280",
                font=(
                    "Segoe UI",
                    10
                )
            ).pack(
                pady=(12, 2)
            )

            label = tk.Label(
                card,
                text="0",
                bg="white",
                fg="#111827",
                font=(
                    "Segoe UI",
                    24,
                    "bold"
                )
            )

            label.pack(
                pady=(0, 12)
            )

            self.stat_labels[key] = label

        info = ttk.LabelFrame(
            frame,
            text="System Features"
        )

        info.pack(
            fill="both",
            expand=True,
            padx=26,
            pady=30
        )

        features = [
            "• HR can register new employees.",
            "• Each employee automatically receives an account.",
            "• Employees can log in and upload their own documents.",
            "• HR can inspect uploaded documents.",
            "• HR can verify or request revisions.",
            "• Employees can see verification results.",
            "• HR can approve employees after requirements are completed.",
            "• All information is stored in SQLite."
        ]

        for feature in features:

            ttk.Label(
                info,
                text=feature,
                font=(
                    "Segoe UI",
                    11
                )
            ).pack(
                anchor="w",
                padx=20,
                pady=8
            )

    # ========================================================
    # EMPLOYEE PAGE
    # ========================================================

    def build_employees(self):

        frame = self.employee_tab

        top = tk.Frame(
            frame,
            bg="#f3f4f6"
        )

        top.pack(
            fill="x",
            padx=15,
            pady=15
        )

        ttk.Label(
            top,
            text="Employee Records",
            style="Header.TLabel"
        ).pack(
            side="left"
        )

        ttk.Button(
            top,
            text="+ Add New Employee",
            command=self.add_employee_dialog
        ).pack(
            side="right"
        )

        search_frame = ttk.Frame(frame)

        search_frame.pack(
            fill="x",
            padx=15,
            pady=(0, 10)
        )

        ttk.Label(
            search_frame,
            text="Search:"
        ).pack(
            side="left"
        )

        self.search_var = tk.StringVar()

        search_entry = ttk.Entry(
            search_frame,
            textvariable=self.search_var,
            width=40
        )

        search_entry.pack(
            side="left",
            padx=8
        )

        search_entry.bind(
            "<KeyRelease>",
            lambda event:
            self.refresh_employee_table()
        )

        ttk.Button(
            search_frame,
            text="Refresh",
            command=self.refresh_all
        ).pack(
            side="left"
        )

        table_frame = ttk.Frame(frame)

        table_frame.pack(
            fill="both",
            expand=True,
            padx=15,
            pady=5
        )

        columns = (
            "id",
            "employee_no",
            "name",
            "department",
            "position",
            "status"
        )

        self.employee_tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings"
        )

        headings = {
            "id": "ID",
            "employee_no": "Employee No.",
            "name": "Employee Name",
            "department": "Department",
            "position": "Position",
            "status": "Status"
        }

        widths = {
            "id": 55,
            "employee_no": 120,
            "name": 230,
            "department": 150,
            "position": 170,
            "status": 170
        }

        for col in columns:

            self.employee_tree.heading(
                col,
                text=headings[col]
            )

            self.employee_tree.column(
                col,
                width=widths[col],
                anchor="center"
            )

        self.employee_tree.column(
            "name",
            anchor="w"
        )

        self.employee_tree.pack(
            side="left",
            fill="both",
            expand=True
        )

        self.employee_tree.bind(
            "<<TreeviewSelect>>",
            self.select_employee
        )

        self.employee_tree.bind(
            "<Double-1>",
            lambda event:
            self.open_selected_employee()
        )

        scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.employee_tree.yview
        )

        scrollbar.pack(
            side="right",
            fill="y"
        )

        self.employee_tree.configure(
            yscrollcommand=scrollbar.set
        )

        ttk.Label(
            frame,
            text=(
                "Double-click an employee to open "
                "onboarding details."
            ),
            foreground="#6b7280"
        ).pack(
            anchor="w",
            padx=15,
            pady=8
        )

    # ========================================================
    # DETAILS PAGE
    # ========================================================

    def build_details(self):

        frame = self.details_tab

        self.details_title = ttk.Label(
            frame,
            text="Select an employee",
            style="Header.TLabel"
        )

        self.details_title.pack(
            anchor="w",
            padx=20,
            pady=(15, 2)
        )

        self.details_subtitle = ttk.Label(
            frame,
            text="Choose an employee.",
            style="Sub.TLabel"
        )

        self.details_subtitle.pack(
            anchor="w",
            padx=20,
            pady=(0, 15)
        )

        body = ttk.Frame(frame)

        body.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=5
        )

        # ----------------------------------------------------
        # CHECKLIST
        # ----------------------------------------------------

        left = ttk.LabelFrame(
            body,
            text="Onboarding Checklist"
        )

        left.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(0, 8)
        )

        self.checklist_canvas = tk.Canvas(
            left,
            highlightthickness=0
        )

        self.checklist_scroll = ttk.Scrollbar(
            left,
            orient="vertical",
            command=self.checklist_canvas.yview
        )

        self.checklist_inner = ttk.Frame(
            self.checklist_canvas
        )

        self.checklist_inner.bind(
            "<Configure>",
            lambda event:
            self.checklist_canvas.configure(
                scrollregion=
                self.checklist_canvas.bbox("all")
            )
        )

        self.checklist_canvas.create_window(
            (0, 0),
            window=self.checklist_inner,
            anchor="nw"
        )

        self.checklist_canvas.configure(
            yscrollcommand=
            self.checklist_scroll.set
        )

        self.checklist_canvas.pack(
            side="left",
            fill="both",
            expand=True
        )

        self.checklist_scroll.pack(
            side="right",
            fill="y"
        )

        # ----------------------------------------------------
        # DOCUMENT VERIFICATION
        # ----------------------------------------------------

        right = ttk.LabelFrame(
            body,
            text="Document Verification"
        )

        right.pack(
            side="right",
            fill="both",
            expand=True,
            padx=(8, 0)
        )

        upload_bar = ttk.Frame(right)

        upload_bar.pack(
            fill="x",
            padx=10,
            pady=10
        )

        ttk.Button(
            upload_bar,
            text="Upload Document",
            command=self.upload_document
        ).pack(
            side="left"
        )

        ttk.Label(
            upload_bar,
            text="HR can upload a document on behalf of the employee."
        ).pack(
            side="left",
            padx=10
        )

        doc_frame = ttk.Frame(right)

        doc_frame.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=(0, 10)
        )

        doc_columns = (
            "id",
            "type",
            "file",
            "status",
            "uploaded"
        )

        self.doc_tree = ttk.Treeview(
            doc_frame,
            columns=doc_columns,
            show="headings"
        )

        doc_headings = {
            "id": "ID",
            "type": "Type",
            "file": "File",
            "status": "Verification",
            "uploaded": "Uploaded"
        }

        doc_widths = {
            "id": 45,
            "type": 150,
            "file": 180,
            "status": 130,
            "uploaded": 145
        }

        for col in doc_columns:

            self.doc_tree.heading(
                col,
                text=doc_headings[col]
            )

            self.doc_tree.column(
                col,
                width=doc_widths[col],
                anchor="center"
            )

        self.doc_tree.column(
            "file",
            anchor="w"
        )

        self.doc_tree.pack(
            side="left",
            fill="both",
            expand=True
        )

        doc_scroll = ttk.Scrollbar(
            doc_frame,
            orient="vertical",
            command=self.doc_tree.yview
        )

        doc_scroll.pack(
            side="right",
            fill="y"
        )

        self.doc_tree.configure(
            yscrollcommand=doc_scroll.set
        )

        self.doc_tree.bind(
            "<Double-1>",
            lambda event:
            self.open_document()
        )

        doc_actions = ttk.Frame(right)

        doc_actions.pack(
            fill="x",
            padx=10,
            pady=(0, 10)
        )

        ttk.Button(
            doc_actions,
            text="Open Document",
            command=self.open_document
        ).pack(
            side="left",
            padx=(0, 5)
        )

        ttk.Button(
            doc_actions,
            text="Verify Document",
            command=lambda:
            self.change_document_status(
                "Verified"
            )
        ).pack(
            side="left",
            padx=(0, 5)
        )

        ttk.Button(
            doc_actions,
            text="Request Revision",
            command=lambda:
            self.change_document_status(
                "Revision Required"
            )
        ).pack(
            side="left"
        )

        # ----------------------------------------------------
        # HR REVIEW
        # ----------------------------------------------------

        hr_frame = ttk.LabelFrame(
            frame,
            text="HR Review"
        )

        hr_frame.pack(
            fill="x",
            padx=20,
            pady=15
        )

        ttk.Label(
            hr_frame,
            text="HR Notes:"
        ).grid(
            row=0,
            column=0,
            sticky="nw",
            padx=10,
            pady=10
        )

        self.notes_text = tk.Text(
            hr_frame,
            height=4,
            width=80,
            font=(
                "Segoe UI",
                10
            )
        )

        self.notes_text.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=10,
            pady=10
        )

        hr_frame.columnconfigure(
            1,
            weight=1
        )

        action_frame = ttk.Frame(
            hr_frame
        )

        action_frame.grid(
            row=1,
            column=1,
            sticky="e",
            padx=10,
            pady=(0, 10)
        )

        ttk.Button(
            action_frame,
            text="Approve Employee",
            command=lambda:
            self.set_employee_status(
                "Approved"
            )
        ).pack(
            side="left",
            padx=4
        )

        ttk.Button(
            action_frame,
            text="Request Revision",
            command=lambda:
            self.set_employee_status(
                "Revision Requested"
            )
        ).pack(
            side="left",
            padx=4
        )

        ttk.Button(
            action_frame,
            text="Set Pending",
            command=lambda:
            self.set_employee_status(
                "Pending"
            )
        ).pack(
            side="left",
            padx=4
        )

        ttk.Button(
            action_frame,
            text="Create/Reset Employee Login",
            command=self.reset_employee_login
        ).pack(
            side="left",
            padx=4
        )

    # ========================================================
    # ADD EMPLOYEE
    # ========================================================

    def add_employee_dialog(self):

        dialog = tk.Toplevel(self)

        dialog.title(
            "Add New Employee"
        )

        dialog.geometry(
            "500x470"
        )

        dialog.resizable(
            False,
            False
        )

        dialog.transient(self)

        dialog.grab_set()

        ttk.Label(
            dialog,
            text="New Employee",
            style="Header.TLabel"
        ).pack(
            anchor="w",
            padx=25,
            pady=(20, 15)
        )

        form = ttk.Frame(dialog)

        form.pack(
            fill="both",
            expand=True,
            padx=25
        )

        variables = {}

        fields = [
            ("Employee No.*", "employee_no"),
            ("First Name*", "first_name"),
            ("Last Name*", "last_name"),
            ("Email", "email"),
            ("Phone", "phone"),
            ("Department", "department"),
            ("Position", "position")
        ]

        for row, (label, key) in enumerate(fields):

            ttk.Label(
                form,
                text=label
            ).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 12),
                pady=7
            )

            var = tk.StringVar()

            variables[key] = var

            ttk.Entry(
                form,
                textvariable=var,
                width=38
            ).grid(
                row=row,
                column=1,
                sticky="ew",
                pady=7
            )

        form.columnconfigure(
            1,
            weight=1
        )

        def save():

            required = [
                "employee_no",
                "first_name",
                "last_name"
            ]

            if any(
                not variables[key].get().strip()
                for key in required
            ):

                messagebox.showwarning(
                    "Missing Information",
                    (
                        "Employee No., First Name, "
                        "and Last Name are required."
                    ),
                    parent=dialog
                )

                return

            try:

                employee_id = self.db.add_employee(
                    {
                        key: var.get().strip()
                        for key, var
                        in variables.items()
                    }
                )

                employee_no = variables[
                    "employee_no"
                ].get().strip()

                dialog.destroy()

                self.refresh_all()

                self.select_employee_by_id(
                    employee_id
                )

                self.notebook.select(
                    self.details_tab
                )

                messagebox.showinfo(
                    "Employee Created",
                    (
                        "Employee created successfully.\n\n"
                        f"Employee Login\n"
                        f"Username: {employee_no.lower()}\n"
                        "Password: welcome123\n\n"
                        "Please provide these credentials "
                        "to the employee."
                    )
                )

            except sqlite3.IntegrityError:

                messagebox.showerror(
                    "Duplicate Employee No.",
                    (
                        "That employee number already exists."
                    ),
                    parent=dialog
                )

        ttk.Button(
            dialog,
            text="Create Employee",
            command=save
        ).pack(
            side="right",
            padx=25,
            pady=20
        )

        ttk.Button(
            dialog,
            text="Cancel",
            command=dialog.destroy
        ).pack(
            side="right",
            pady=20
        )

    # ========================================================
    # RESET EMPLOYEE LOGIN
    # ========================================================

    def reset_employee_login(self):

        if not self.selected_employee_id:

            messagebox.showwarning(
                "Select Employee",
                "Please select an employee first."
            )

            return

        employee = self.db.get_employee(
            self.selected_employee_id
        )

        if not employee:
            return

        username = employee[
            "employee_no"
        ].strip().lower()

        self.db.create_employee_login(
            employee["id"],
            username,
            "welcome123"
        )

        messagebox.showinfo(
            "Employee Login",
            (
                "Employee login created/reset.\n\n"
                f"Username: {username}\n"
                "Password: welcome123"
            )
        )

    # ========================================================
    # REFRESH
    # ========================================================

    def refresh_all(self):

        self.refresh_employee_table()

        self.refresh_dashboard()

        if self.selected_employee_id:

            employee = self.db.get_employee(
                self.selected_employee_id
            )

            if employee:

                self.load_employee_details(
                    self.selected_employee_id
                )

    # ========================================================
    # DASHBOARD STATS
    # ========================================================

    def refresh_dashboard(self):

        total, pending, approved, revision = \
            self.db.stats()

        self.stat_labels[
            "total"
        ].config(
            text=str(total)
        )

        self.stat_labels[
            "pending"
        ].config(
            text=str(pending)
        )

        self.stat_labels[
            "approved"
        ].config(
            text=str(approved)
        )

        self.stat_labels[
            "revision"
        ].config(
            text=str(revision)
        )

    # ========================================================
    # EMPLOYEE TABLE
    # ========================================================

    def refresh_employee_table(self):

        for item in self.employee_tree.get_children():

            self.employee_tree.delete(item)

        rows = self.db.employees(
            self.search_var.get()
        )

        for employee in rows:

            name = (
                f"{employee['first_name']} "
                f"{employee['last_name']}"
            )

            self.employee_tree.insert(
                "",
                "end",
                iid=str(employee["id"]),
                values=(
                    employee["id"],
                    employee["employee_no"],
                    name,
                    employee["department"],
                    employee["position"],
                    employee["status"]
                )
            )

    # ========================================================
    # SELECT EMPLOYEE
    # ========================================================

    def select_employee(
        self,
        event=None
    ):

        selection = self.employee_tree.selection()

        if not selection:
            return

        self.select_employee_by_id(
            int(selection[0])
        )

    def select_employee_by_id(
        self,
        employee_id
    ):

        self.selected_employee_id = employee_id

        self.load_employee_details(
            employee_id
        )

    # ========================================================
    # OPEN SELECTED EMPLOYEE
    # ========================================================

    def open_selected_employee(self):

        selection = self.employee_tree.selection()

        if not selection:

            messagebox.showwarning(
                "No Employee Selected",
                "Select an employee first."
            )

            return

        self.selected_employee_id = int(
            selection[0]
        )

        self.load_employee_details(
            self.selected_employee_id
        )

        self.notebook.select(
            self.details_tab
        )

    # ========================================================
    # LOAD EMPLOYEE DETAILS
    # ========================================================

    def load_employee_details(
        self,
        employee_id
    ):

        employee = self.db.get_employee(
            employee_id
        )

        if not employee:
            return

        self.details_title.config(
            text=(
                f"{employee['first_name']} "
                f"{employee['last_name']}"
            )
        )

        self.details_subtitle.config(
            text=(
                f"{employee['employee_no']} • "
                f"{employee['department']} • "
                f"{employee['position']} • "
                f"Status: {employee['status']}"
            )
        )

        # ----------------------------------------------------
        # CHECKLIST
        # ----------------------------------------------------

        for widget in \
                self.checklist_inner.winfo_children():

            widget.destroy()

        checklist_items = self.db.get_checklist(
            employee_id
        )

        for item in checklist_items:

            var = tk.BooleanVar(
                value=bool(
                    item["completed"]
                )
            )

            cb = ttk.Checkbutton(
                self.checklist_inner,
                text=item["item"],
                variable=var,
                command=lambda
                item_id=item["id"],
                v=var:
                self.update_checklist(
                    item_id,
                    v
                )
            )

            cb.pack(
                anchor="w",
                padx=12,
                pady=8
            )

        # ----------------------------------------------------
        # DOCUMENTS
        # ----------------------------------------------------

        for item in self.doc_tree.get_children():

            self.doc_tree.delete(item)

        documents = self.db.get_documents(
            employee_id
        )

        for document in documents:

            self.doc_tree.insert(
                "",
                "end",
                iid=str(
                    document["id"]
                ),
                values=(
                    document["id"],
                    document["document_type"],
                    document["original_name"],
                    document[
                        "verification_status"
                    ],
                    document["uploaded_at"]
                )
            )

        # ----------------------------------------------------
        # HR NOTES
        # ----------------------------------------------------

        self.notes_text.delete(
            "1.0",
            "end"
        )

        self.notes_text.insert(
            "1.0",
            employee["hr_notes"] or ""
        )

    # ========================================================
    # CHECKLIST UPDATE
    # ========================================================

    def update_checklist(
        self,
        item_id,
        var
    ):

        self.db.set_checklist(
            item_id,
            var.get()
        )

    # ========================================================
    # UPLOAD DOCUMENT
    # ========================================================

    def upload_document(self):

        if not self.selected_employee_id:

            messagebox.showwarning(
                "Select Employee",
                "Please select an employee first."
            )

            return

        document_type = self.choose_document_type()

        if not document_type:
            return

        file_path = filedialog.askopenfilename(
            title="Select Compliance Document",
            filetypes=[
                (
                    "Documents",
                    "*.pdf *.png *.jpg *.jpeg *.doc *.docx"
                ),
                (
                    "All files",
                    "*.*"
                )
            ]
        )

        if not file_path:
            return

        employee = self.db.get_employee(
            self.selected_employee_id
        )

        safe_employee = "".join(
            character
            for character in (
                f"{employee['employee_no']}_"
                f"{employee['last_name']}"
            )
            if character.isalnum()
            or character in "_-"
        )

        employee_folder = (
            DOC_DIR / safe_employee
        )

        employee_folder.mkdir(
            parents=True,
            exist_ok=True
        )

        original = Path(
            file_path
        ).name

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        destination = (
            employee_folder /
            f"{timestamp}_{original}"
        )

        try:

            shutil.copy2(
                file_path,
                destination
            )

            self.db.add_document(
                self.selected_employee_id,
                document_type,
                original,
                str(destination)
            )

            self.load_employee_details(
                self.selected_employee_id
            )

            messagebox.showinfo(
                "Upload Complete",
                (
                    f"{original} was uploaded successfully.\n\n"
                    "Verification status: Pending"
                )
            )

        except OSError as exc:

            messagebox.showerror(
                "Upload Failed",
                f"Could not copy the document:\n{exc}"
            )

    # ========================================================
    # CHOOSE DOCUMENT TYPE
    # ========================================================

    def choose_document_type(self):

        dialog = tk.Toplevel(self)

        dialog.title(
            "Document Type"
        )

        dialog.geometry(
            "380x220"
        )

        dialog.resizable(
            False,
            False
        )

        dialog.transient(self)

        dialog.grab_set()

        result = {
            "value": None
        }

        ttk.Label(
            dialog,
            text="Choose Document Type",
            style="Header.TLabel"
        ).pack(
            pady=(25, 15)
        )

        var = tk.StringVar(
            value=DOCUMENT_TYPES[0]
        )

        combo = ttk.Combobox(
            dialog,
            textvariable=var,
            values=DOCUMENT_TYPES,
            state="readonly",
            width=35
        )

        combo.pack(
            pady=5
        )

        def choose():

            result["value"] = var.get()

            dialog.destroy()

        ttk.Button(
            dialog,
            text="Continue",
            command=choose
        ).pack(
            pady=20
        )

        self.wait_window(
            dialog
        )

        return result["value"]

    # ========================================================
    # OPEN DOCUMENT
    # ========================================================

    def open_document(self):

        selection = self.doc_tree.selection()

        if not selection:

            messagebox.showwarning(
                "No Document Selected",
                "Please select a document first."
            )

            return

        document_id = int(
            selection[0]
        )

        document = self.db.get_document(
            document_id
        )

        if not document:

            messagebox.showerror(
                "Document Not Found",
                "The selected document could not be found."
            )

            return

        file_path = Path(
            document["stored_path"]
        )

        if not file_path.exists():

            messagebox.showerror(
                "File Not Found",
                (
                    "The document no longer exists at:\n\n"
                    f"{file_path}"
                )
            )

            return

        try:

            if sys.platform.startswith("win"):

                os.startfile(
                    str(file_path)
                )

            elif sys.platform == "darwin":

                os.system(
                    f'open "{file_path}"'
                )

            else:

                os.system(
                    f'xdg-open "{file_path}"'
                )

        except Exception as exc:

            messagebox.showerror(
                "Unable to Open Document",
                (
                    "Could not open the document:\n\n"
                    f"{exc}"
                )
            )

    # ========================================================
    # CHANGE DOCUMENT STATUS
    # ========================================================

    def change_document_status(
        self,
        status
    ):

        selection = self.doc_tree.selection()

        if not selection:

            messagebox.showwarning(
                "No Document Selected",
                "Select a document first."
            )

            return

        document_id = int(
            selection[0]
        )

        document = self.db.get_document(
            document_id
        )

        if not document:
            return

        self.db.update_document_status(
            document_id,
            status
        )

        # Automatically complete the matching checklist item
        if status == "Verified":

            checklist_item = \
                DOCUMENT_CHECKLIST_MAP.get(
                    document["document_type"]
                )

            if checklist_item:

                self.db.complete_checklist_item(
                    self.selected_employee_id,
                    checklist_item
                )

        self.load_employee_details(
            self.selected_employee_id
        )

        messagebox.showinfo(
            "Updated",
            f"Document status changed to: {status}"
        )

    # ========================================================
    # EMPLOYEE STATUS
    # ========================================================

    def set_employee_status(
        self,
        status
    ):

        if not self.selected_employee_id:

            messagebox.showwarning(
                "Select Employee",
                "Please select an employee first."
            )

            return

        notes = self.notes_text.get(
            "1.0",
            "end"
        ).strip()

        if status == "Approved":

            incomplete = [
                item["item"]
                for item in self.db.get_checklist(
                    self.selected_employee_id
                )
                if not item["completed"]
            ]

            documents = self.db.get_documents(
                self.selected_employee_id
            )

            unverified = [
                doc["original_name"]
                for doc in documents
                if doc["verification_status"]
                != "Verified"
            ]

            if incomplete:

                messagebox.showwarning(
                    "Incomplete Checklist",
                    (
                        "The employee cannot be approved yet.\n\n"
                        "Incomplete requirements:\n\n"
                        +
                        "\n".join(
                            f"• {item}"
                            for item in incomplete
                        )
                    )
                )

                return

            if not documents:

                messagebox.showwarning(
                    "No Documents",
                    (
                        "The employee cannot be approved "
                        "because no compliance documents "
                        "have been uploaded."
                    )
                )

                return

            if unverified:

                messagebox.showwarning(
                    "Unverified Documents",
                    (
                        "The employee cannot be approved yet.\n\n"
                        "Documents requiring verification:\n\n"
                        +
                        "\n".join(
                            f"• {doc}"
                            for doc in unverified
                        )
                    )
                )

                return

        self.db.update_employee_status(
            self.selected_employee_id,
            status,
            notes
        )

        self.refresh_all()

        messagebox.showinfo(
            "HR Review Saved",
            f"Employee status is now: {status}"
        )

    # ========================================================
    # LOGOUT
    # ========================================================

    def logout(self):

        self.destroy()

        self.login_window.deiconify()

        self.login_window.username_var.set("")

        self.login_window.password_var.set("")


# ============================================================
# EMPLOYEE PORTAL
# ============================================================

class EmployeePortal(tk.Tk):

    def __init__(
        self,
        db,
        login_window,
        employee_id
    ):

        super().__init__()

        self.db = db
        self.login_window = login_window
        self.employee_id = employee_id

        self.title(
            "Employee Onboarding Portal"
        )

        self.geometry(
            "1150x720"
        )

        self.minsize(
            1000,
            650
        )

        self.configure(
            bg="#f3f4f6"
        )

        self.style = ttk.Style(self)

        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.style.configure(
            "Treeview",
            rowheight=30,
            font=("Segoe UI", 10)
        )

        self.style.configure(
            "Treeview.Heading",
            font=(
                "Segoe UI",
                10,
                "bold"
            )
        )

        self.create_ui()

        self.refresh()

    # ========================================================
    # MAIN UI
    # ========================================================

    def create_ui(self):

        header = tk.Frame(
            self,
            bg="#1f2937",
            height=70
        )

        header.pack(
            fill="x"
        )

        tk.Label(
            header,
            text="Employee Onboarding Portal",
            bg="#1f2937",
            fg="white",
            font=(
                "Segoe UI",
                18,
                "bold"
            )
        ).pack(
            side="left",
            padx=22,
            pady=17
        )

        ttk.Button(
            header,
            text="Logout",
            command=self.logout
        ).pack(
            side="right",
            padx=20
        )

        self.notebook = ttk.Notebook(
            self
        )

        self.notebook.pack(
            fill="both",
            expand=True,
            padx=12,
            pady=12
        )

        self.dashboard_tab = ttk.Frame(
            self.notebook
        )

        self.documents_tab = ttk.Frame(
            self.notebook
        )

        self.profile_tab = ttk.Frame(
            self.notebook
        )

        self.notebook.add(
            self.dashboard_tab,
            text="My Dashboard"
        )

        self.notebook.add(
            self.documents_tab,
            text="My Documents"
        )

        self.notebook.add(
            self.profile_tab,
            text="My Information"
        )

        self.build_dashboard()
        self.build_documents()
        self.build_profile()

    # ========================================================
    # DASHBOARD
    # ========================================================

    def build_dashboard(self):

        frame = self.dashboard_tab

        self.welcome_label = ttk.Label(
            frame,
            text="Welcome",
            style="Header.TLabel"
        )

        self.welcome_label.pack(
            anchor="w",
            padx=25,
            pady=(20, 4)
        )

        self.status_label = ttk.Label(
            frame,
            text="Status: Pending",
            font=(
                "Segoe UI",
                11,
                "bold"
            )
        )

        self.status_label.pack(
            anchor="w",
            padx=25,
            pady=(0, 20)
        )

        # ----------------------------------------------------
        # PROGRESS
        # ----------------------------------------------------

        progress_frame = ttk.LabelFrame(
            frame,
            text="Onboarding Progress"
        )

        progress_frame.pack(
            fill="x",
            padx=25,
            pady=5
        )

        self.progress_label = ttk.Label(
            progress_frame,
            text="0%"
        )

        self.progress_label.pack(
            anchor="w",
            padx=15,
            pady=(15, 5)
        )

        self.progress_bar = ttk.Progressbar(
            progress_frame,
            orient="horizontal",
            mode="determinate"
        )

        self.progress_bar.pack(
            fill="x",
            padx=15,
            pady=(0, 15)
        )

        # ----------------------------------------------------
        # REQUIREMENTS
        # ----------------------------------------------------

        requirements_frame = ttk.LabelFrame(
            frame,
            text="My Onboarding Requirements"
        )

        requirements_frame.pack(
            fill="both",
            expand=True,
            padx=25,
            pady=15
        )

        self.requirements_tree = ttk.Treeview(
            requirements_frame,
            columns=(
                "requirement",
                "status"
            ),
            show="headings"
        )

        self.requirements_tree.heading(
            "requirement",
            text="Requirement"
        )

        self.requirements_tree.heading(
            "status",
            text="Status"
        )

        self.requirements_tree.column(
            "requirement",
            anchor="w",
            width=550
        )

        self.requirements_tree.column(
            "status",
            anchor="center",
            width=220
        )

        self.requirements_tree.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10
        )

        # ----------------------------------------------------
        # HR MESSAGE
        # ----------------------------------------------------

        notes_frame = ttk.LabelFrame(
            frame,
            text="HR Message / Feedback"
        )

        notes_frame.pack(
            fill="x",
            padx=25,
            pady=(0, 15)
        )

        self.hr_message = ttk.Label(
            notes_frame,
            text="No HR feedback yet.",
            wraplength=900
        )

        self.hr_message.pack(
            anchor="w",
            padx=15,
            pady=15
        )

    # ========================================================
    # DOCUMENTS
    # ========================================================

    def build_documents(self):

        frame = self.documents_tab

        ttk.Label(
            frame,
            text="My Documents",
            style="Header.TLabel"
        ).pack(
            anchor="w",
            padx=20,
            pady=(20, 5)
        )

        ttk.Label(
            frame,
            text=(
                "Upload your onboarding and compliance documents here."
            )
        ).pack(
            anchor="w",
            padx=20,
            pady=(0, 15)
        )

        # ----------------------------------------------------
        # UPLOAD
        # ----------------------------------------------------

        upload_frame = ttk.LabelFrame(
            frame,
            text="Upload Document"
        )

        upload_frame.pack(
            fill="x",
            padx=20,
            pady=5
        )

        ttk.Label(
            upload_frame,
            text="Document Type:"
        ).grid(
            row=0,
            column=0,
            padx=10,
            pady=12
        )

        self.employee_document_type = tk.StringVar(
            value=DOCUMENT_TYPES[0]
        )

        ttk.Combobox(
            upload_frame,
            textvariable=
            self.employee_document_type,
            values=DOCUMENT_TYPES,
            state="readonly",
            width=30
        ).grid(
            row=0,
            column=1,
            padx=10,
            pady=12
        )

        ttk.Button(
            upload_frame,
            text="Select File & Upload",
            command=self.upload_document
        ).grid(
            row=0,
            column=2,
            padx=10,
            pady=12
        )

        # ----------------------------------------------------
        # DOCUMENT TABLE
        # ----------------------------------------------------

        table_frame = ttk.Frame(
            frame
        )

        table_frame.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=15
        )

        columns = (
            "id",
            "type",
            "file",
            "status",
            "uploaded"
        )

        self.document_tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings"
        )

        headings = {
            "id": "ID",
            "type": "Document Type",
            "file": "File",
            "status": "Verification Status",
            "uploaded": "Uploaded"
        }

        for column in columns:

            self.document_tree.heading(
                column,
                text=headings[column]
            )

        self.document_tree.column(
            "id",
            width=50,
            anchor="center"
        )

        self.document_tree.column(
            "type",
            width=180,
            anchor="center"
        )

        self.document_tree.column(
            "file",
            width=300,
            anchor="w"
        )

        self.document_tree.column(
            "status",
            width=180,
            anchor="center"
        )

        self.document_tree.column(
            "uploaded",
            width=180,
            anchor="center"
        )

        self.document_tree.pack(
            side="left",
            fill="both",
            expand=True
        )

        scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.document_tree.yview
        )

        scrollbar.pack(
            side="right",
            fill="y"
        )

        self.document_tree.configure(
            yscrollcommand=scrollbar.set
        )

        self.document_tree.bind(
            "<Double-1>",
            lambda event:
            self.open_document()
        )

        buttons = ttk.Frame(frame)

        buttons.pack(
            fill="x",
            padx=20,
            pady=(0, 15)
        )

        ttk.Button(
            buttons,
            text="Open Selected Document",
            command=self.open_document
        ).pack(
            side="left"
        )

    # ========================================================
    # PROFILE
    # ========================================================

    def build_profile(self):

        frame = self.profile_tab

        ttk.Label(
            frame,
            text="My Information",
            style="Header.TLabel"
        ).pack(
            anchor="w",
            padx=25,
            pady=(25, 20)
        )

        self.profile_text = tk.Text(
            frame,
            height=15,
            font=(
                "Segoe UI",
                11
            ),
            state="disabled"
        )

        self.profile_text.pack(
            fill="both",
            expand=True,
            padx=25,
            pady=10
        )

    # ========================================================
    # REFRESH
    # ========================================================

    def refresh(self):

        employee = self.db.get_employee(
            self.employee_id
        )

        if not employee:
            return

        self.refresh_dashboard(
            employee
        )

        self.refresh_documents()

        self.refresh_profile(
            employee
        )

    # ========================================================
    # DASHBOARD REFRESH
    # ========================================================

    def refresh_dashboard(
        self,
        employee
    ):

        full_name = (
            f"{employee['first_name']} "
            f"{employee['last_name']}"
        )

        self.welcome_label.config(
            text=f"Welcome, {full_name}"
        )

        self.status_label.config(
            text=f"Status: {employee['status']}"
        )

        checklist = self.db.get_checklist(
            self.employee_id
        )

        completed = sum(
            1
            for item in checklist
            if item["completed"]
        )

        total = len(checklist)

        if total:
            percentage = int(
                completed / total * 100
            )
        else:
            percentage = 0

        self.progress_bar["value"] = percentage

        self.progress_label.config(
            text=(
                f"{percentage}% complete "
                f"({completed}/{total})"
            )
        )

        for item in self.requirements_tree.get_children():

            self.requirements_tree.delete(
                item
            )

        documents = self.db.get_documents(
            self.employee_id
        )

        verified_types = {
            doc["document_type"]
            for doc in documents
            if doc["verification_status"]
            == "Verified"
        }

        for item in checklist:

            status = (
                "Completed"
                if item["completed"]
                else "Pending"
            )

            # Show document revision status
            for doc in documents:

                mapped_item = \
                    DOCUMENT_CHECKLIST_MAP.get(
                        doc["document_type"]
                    )

                if (
                    mapped_item == item["item"]
                    and doc["verification_status"]
                    == "Revision Required"
                ):

                    status = "Revision Required"

            self.requirements_tree.insert(
                "",
                "end",
                values=(
                    item["item"],
                    status
                )
            )

        notes = employee["hr_notes"]

        if notes and notes.strip():

            self.hr_message.config(
                text=notes
            )

        else:

            self.hr_message.config(
                text="No HR feedback yet."
            )

    # ========================================================
    # DOCUMENT REFRESH
    # ========================================================

    def refresh_documents(self):

        for item in self.document_tree.get_children():

            self.document_tree.delete(
                item
            )

        documents = self.db.get_documents(
            self.employee_id
        )

        for document in documents:

            self.document_tree.insert(
                "",
                "end",
                iid=str(
                    document["id"]
                ),
                values=(
                    document["id"],
                    document["document_type"],
                    document["original_name"],
                    document[
                        "verification_status"
                    ],
                    document["uploaded_at"]
                )
            )

    # ========================================================
    # PROFILE REFRESH
    # ========================================================

    def refresh_profile(
        self,
        employee
    ):

        text = (
            f"Employee No.: "
            f"{employee['employee_no']}\n\n"

            f"First Name: "
            f"{employee['first_name']}\n\n"

            f"Last Name: "
            f"{employee['last_name']}\n\n"

            f"Email: "
            f"{employee['email'] or '-'}\n\n"

            f"Phone: "
            f"{employee['phone'] or '-'}\n\n"

            f"Department: "
            f"{employee['department'] or '-'}\n\n"

            f"Position: "
            f"{employee['position'] or '-'}\n\n"

            f"Onboarding Status: "
            f"{employee['status']}\n\n"

            f"Account Created: "
            f"{employee['created_at']}"
        )

        self.profile_text.config(
            state="normal"
        )

        self.profile_text.delete(
            "1.0",
            "end"
        )

        self.profile_text.insert(
            "1.0",
            text
        )

        self.profile_text.config(
            state="disabled"
        )

    # ========================================================
    # EMPLOYEE UPLOAD
    # ========================================================

    def upload_document(self):

        document_type = \
            self.employee_document_type.get()

        if not document_type:
            return

        file_path = filedialog.askopenfilename(
            title="Select Your Document",
            filetypes=[
                (
                    "Documents",
                    "*.pdf *.png *.jpg *.jpeg *.doc *.docx"
                ),
                (
                    "All files",
                    "*.*"
                )
            ]
        )

        if not file_path:
            return

        employee = self.db.get_employee(
            self.employee_id
        )

        safe_employee = "".join(
            character
            for character in (
                f"{employee['employee_no']}_"
                f"{employee['last_name']}"
            )
            if character.isalnum()
            or character in "_-"
        )

        employee_folder = (
            DOC_DIR / safe_employee
        )

        employee_folder.mkdir(
            parents=True,
            exist_ok=True
        )

        original = Path(
            file_path
        ).name

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        destination = (
            employee_folder /
            f"{timestamp}_{original}"
        )

        try:

            shutil.copy2(
                file_path,
                destination
            )

            self.db.add_document(
                self.employee_id,
                document_type,
                original,
                str(destination)
            )

            self.refresh()

            messagebox.showinfo(
                "Upload Complete",
                (
                    f"{original} uploaded successfully.\n\n"
                    "HR will review the document."
                )
            )

        except OSError as exc:

            messagebox.showerror(
                "Upload Failed",
                f"Could not upload the document:\n{exc}"
            )

    # ========================================================
    # OPEN DOCUMENT
    # ========================================================

    def open_document(self):

        selection = self.document_tree.selection()

        if not selection:

            messagebox.showwarning(
                "No Document Selected",
                "Please select a document first."
            )

            return

        document_id = int(
            selection[0]
        )

        document = self.db.get_document(
            document_id
        )

        if not document:

            messagebox.showerror(
                "Document Not Found",
                "The document could not be found."
            )

            return

        # Security check
        if document["employee_id"] != \
                self.employee_id:

            messagebox.showerror(
                "Access Denied",
                "You cannot access this document."
            )

            return

        file_path = Path(
            document["stored_path"]
        )

        if not file_path.exists():

            messagebox.showerror(
                "File Not Found",
                (
                    "The document no longer exists:\n\n"
                    f"{file_path}"
                )
            )

            return

        try:

            if sys.platform.startswith("win"):

                os.startfile(
                    str(file_path)
                )

            elif sys.platform == "darwin":

                os.system(
                    f'open "{file_path}"'
                )

            else:

                os.system(
                    f'xdg-open "{file_path}"'
                )

        except Exception as exc:

            messagebox.showerror(
                "Unable to Open",
                f"Could not open document:\n{exc}"
            )

    # ========================================================
    # LOGOUT
    # ========================================================

    def logout(self):

        self.destroy()

        self.login_window.deiconify()

        self.login_window.username_var.set("")

        self.login_window.password_var.set("")


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    login = LoginWindow()

    login.mainloop()
