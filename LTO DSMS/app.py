from flask import Flask, render_template, request, redirect, session, url_for, send_file, flash, jsonify
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.platypus import Image, Spacer, Paragraph
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet
from openpyxl.styles import Font
from openpyxl import Workbook
from functools import wraps
from datetime import datetime, timedelta
from flask import Response
import smtplib
from email.mime.text import MIMEText
import pandas as pd
import sqlite3
import bcrypt
import random
import csv
import re
import os
import io
import openpyxl
from functools import wraps
from collections import defaultdict

app = Flask(__name__)
app.secret_key = "secret123"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "database.db")

def get_db():
    return sqlite3.connect(DATABASE)

# ---------- INIT DB ----------
def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT,
            otp TEXT,
            otp_expiry TEXT,
            is_active INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS driving_schools (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        
        bus_id TEXT,
        accreditation TEXT,
        bus_name TEXT,
        cap1 INTEGER,
        cap2 INTEGER,
        cap3 INTEGER,
        total INTEGER,
        org_add TEXT,
        org_type TEXT,
        validity TEXT,
        status TEXT,
        region TEXT
    )
''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS login_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Email TEXT UNIQUE,
            Username TEXT,
            Login TIME TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT,
            username TEXT,
            action TEXT,
            timestamp TEXT
        )
    ''')

    # Insert default admin
    cursor.execute("SELECT * FROM users WHERE Username='admin'")
    if not cursor.fetchone():
        admin_pw = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt())

        cursor.execute("INSERT INTO users (Username, password, role, is_active) VALUES (?, ?, ?, ?)",
                    ("admin", admin_pw, "admin", 1))

    conn.commit()
    conn.close()

init_db()

def send_otp_email(receiver_email, otp):
    sender_email = "" # set an email responsible for sending otp
    app_password = "" # insert app password provided by google

    subject = "Your OTP Verification Code"
    body = f"""
    Your OTP code is: {otp}

    This code will expire in 5 minutes.
    """

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = receiver_email

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()
        print("OTP sent successfully")
    except Exception as e:
        print("Error sending email:", e)

def import_csv_to_db():
    conn = get_db()
    cursor = conn.cursor() 

    with open('LTO.csv', 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)

        for row in reader:
            
            bus_id = row.get('bus_id') or row.get('Business ID')
            accreditation = row.get('accreditation') or row.get('Accreditation No.')
            bus_name = row.get('bus_name') or row.get('Business Name')
            cap1 = int(row.get('cap1') or row.get('CDE') or 0)
            cap2 = int(row.get('cap2') or row.get('TDC') or 0)
            cap3 = int(row.get('cap3') or row.get('PDC') or 0)

            total = cap1 + cap2 + cap3
            org_add = row.get('org_add') or row.get('Organization Address')
            org_type = row.get('org_type') or row.get('Organization Types')
            validity = row.get('validity') or row.get('Validity')
            status = row.get('status') or row.get('Status')
            region = row.get('region') or row.get('Region')

            if not bus_name:
                continue
            
            # Avoid duplicates
            cursor.execute("SELECT * FROM driving_schools WHERE bus_id=?", (bus_id,))
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO driving_schools 
                    (bus_id, accreditation, bus_name, cap1, cap2, cap3, total, org_add, org_type, validity, status, region)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (bus_id, accreditation, bus_name, cap1, cap2, cap3, total, org_add, org_type, validity, status, region))
                
    conn.commit()
    conn.close()
import_csv_to_db()

def normalize_date(date_str):
    """
    Accepts:
    - mm/dd/yyyy
    - yyyy-mm-dd
    Returns: yyyy-mm-dd (DB format)
    """
    try:
        if not date_str:
            return None

        if "-" in date_str:
            # already yyyy-mm-dd
            datetime.strptime(date_str, "%Y-%m-%d")
            return date_str

        # assume mm/dd/yyyy
        dt = datetime.strptime(date_str, "%m/%d/%Y")
        return dt.strftime("%Y-%m-%d")

    except:
        return None

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'role' not in session or session['role'] != 'admin':
            return "Unauthorized access"
        return f(*args, **kwargs)
    return wrapper

def log_action(username, role, action):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("INSERT INTO audit_logs (username, role, action, timestamp) VALUES (?, ?, ?, ?)",
                (username, role, action, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()
    conn.close()

# ---------- ROUTES ----------

# Landing Page
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():

    errors = {}
    show_otp = False

    if request.method == 'POST':

        email = request.form['Email'].strip()
        username = request.form['username'].strip()
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        conn = get_db()
        cursor = conn.cursor()

        # CHECK IF USER ALREADY EXISTS AND ACTIVE
        cursor.execute("SELECT is_active FROM users WHERE email=? OR Username=?", (email, username))
        existing_user = cursor.fetchone()

        if existing_user:
            if existing_user[0] == 1:
                conn.close()
                errors['general'] = "User already exists"
                return render_template('signup.html', errors=errors, show_otp=False)
            else:
                # Optional: allow re-verification OR block
                conn.close()
                errors['general'] = "Account already registered but not verified. Please login or verify OTP."
                return render_template('signup.html', errors=errors, show_otp=False)

        conn.close()

        # --- VALIDATION ---
        if '@' not in email:
            errors['email'] = "Invalid email address."

        pattern = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&_])[A-Za-z\d@$!%*?&_]{8,}$'
        if not re.match(pattern, password):
            errors['password'] = "Weak password."

        if password != confirm_password:
            errors['confirm_password'] = "Passwords do not match."

        if errors:
            return render_template('signup.html', errors=errors, show_otp=False)

        # STORE TEMP DATA IN SESSION
        session['temp_user'] = {
            "email": email,
            "username": username,
            "password": bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode()
        }

        # CHECK IF OTP EXISTS OR EXPIRED
        otp = session.get('otp')
        expiry = session.get('otp_expiry')
        now = datetime.now()

        if not otp or not expiry or now > datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S"):
            otp = str(random.randint(100000, 999999))
            expiry_dt = now + timedelta(minutes=5)

            session['otp'] = otp
            session['otp_expiry'] = expiry_dt.strftime("%Y-%m-%d %H:%M:%S")

            send_otp_email(email, otp)

        show_otp = True

        expiry_dt = datetime.strptime(session['otp_expiry'], "%Y-%m-%d %H:%M:%S")
        remaining_time = int((expiry_dt - datetime.now()).total_seconds())

        return render_template(
            'signup.html',
            show_otp=True,
            email=session['temp_user']['email'],
            username=session['temp_user']['username'],
            otp_time_left=remaining_time
        )

    return render_template('signup.html', errors=errors, show_otp=False)

# LOGIN
@app.route('/login', methods=['GET', 'POST'])
def login():
    field_errors = {}
    username_value = ''

    if request.method == 'POST':
        login_input = request.form['username'].strip()
        password = request.form['password']
        username_value = login_input

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username=? OR email=?", (login_input, login_input))
        users = cursor.fetchone()

        # Check if user exists
        if not users:
            conn.close()
            field_errors['general'] = "Account does not exist"
            return render_template('login.html', field_errors=field_errors, username_value=username_value)
        
        # CHECK IF ACCOUNT IS ACTIVE
        if users[4] != "admin" and users[7] == 0:
            conn.close()
            field_errors['username'] = "Please verify your OTP first."
            return render_template('login.html', field_errors=field_errors, username_value=username_value)

        if not users:
            field_errors['username'] = "Account does not exist."
        else:
            stored_password = users[3]

            if isinstance(stored_password, str):
                stored_password = stored_password.encode('utf-8')

            if not bcrypt.checkpw(password.encode('utf-8'), stored_password):
                conn.close()
                field_errors['general'] = "Incorrect password"
                return render_template('login.html', field_errors=field_errors, username_value=username_value)
            else:
                session['username'] = users[2]  # username column
                session['role'] = users[4]      # role column
                log_action(users[2], users[4], "Logged in")

                cursor.execute(
                    "INSERT INTO login_logs (username, Login) VALUES (?, ?)",
                    (users[2], datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
                conn.commit()
                conn.close()

                if users[4] == "admin":
                    return redirect('/admin_dashboard')
                return redirect('/dashboard')

        conn.close()

    return render_template('login.html', field_errors=field_errors, username_value=username_value)

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    otp_input = request.form['otp']

    # Check if session still exists
    if 'temp_user' not in session:
        return render_template(
            'signup.html',
            show_otp=False,
            errors={},
            otp_error="Session expired. Please sign up again."
        )

    stored_otp = session.get('otp')
    expiry = session.get('otp_expiry')
    user = session.get('temp_user')

    # Check expiry
    expiry_time = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
    remaining_time = int((expiry_time - datetime.now()).total_seconds())

    if remaining_time <= 0:
        return render_template(
            'signup.html',
            show_otp=True,
            email=user['email'],
            username=user['username'],
            otp_error="OTP expired. Please request a new one.",
            otp_time_left=0  
        )
        
    # Wrong OTP
    if otp_input != stored_otp:
        return render_template(
            'signup.html',
            show_otp=True,
            email=user['email'],
            username=user['username'],
            otp_error="Incorrect OTP. Please try again.",
            otp_time_left=remaining_time
        )

    # OTP CORRECT → NOW SAVE USER
    user = session['temp_user']

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO users (email, username, password, role, is_active)
            VALUES (?, ?, ?, ?, ?)
        """, (
            user['email'],
            user['username'],
            user['password'],  
            "user",
            1
        ))

        conn.commit()

    except:
        conn.close()
        return render_template(
            'signup.html',
            show_otp=True,
            email=user['email'],
            username=user['username'],
            otp_error="User already exists"
        )

    conn.close()

    # Clear session after success
    session.pop('temp_user', None)
    session.pop('otp', None)
    session.pop('otp_expiry', None)

    return redirect('/login')

@app.route('/resend_otp', methods=['POST'])
def resend_otp():

    if 'temp_user' not in session:
        return {"success": False, "message": "Session expired"}

    email = session['temp_user']['email']

    # Generate NEW OTP always 
    otp = str(random.randint(100000, 999999))
    expiry = datetime.now() + timedelta(minutes=5)

    session['otp'] = otp
    session['otp_expiry'] = expiry.strftime("%Y-%m-%d %H:%M:%S")

    send_otp_email(email, otp)

    return {
        "success": True,
        "message": "OTP resent successfully",
        "expiry": int(expiry.timestamp() * 1000)  
    }

@app.route('/verify_page')
def verify_page():
    email = request.args.get('email')

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT otp_expiry FROM users WHERE email=?", (email,))
    user = cursor.fetchone()

    conn.close()

    if not user:
        return "User not found"

    expiry = user[0]
    expiry_time = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
    time_left = int((expiry_time - datetime.now()).total_seconds())

    if time_left < 0:
        time_left = 0

    return render_template("signup.html",
                        show_otp=True,
                        email=email,
                        otp_time_left=time_left,
                        errors={})

# DASHBOARD (User)
@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect('/login')
    return render_template('dashboard.html', username=session['username'])

# ADMIN DASHBOARD
@app.route('/admin_dashboard')
@admin_required
def admin_dashboard():
    return redirect('/admin/schools')

# ENROLL DRIVING SCHOOL
@app.route('/enroll', methods=['GET', 'POST'])
def enroll():
    if 'username' not in session:
        return redirect('/login')
    
    if request.method == 'POST':
        bus_id = request.form.get('bus_id')
        accreditation = request.form.get('accreditation')
        bus_name = request.form.get('bus_name')
        cap1 = request.form.get('cap1')
        cap2 = request.form.get('cap2')
        cap3 = request.form.get('cap3')
        total = request.form.get('total')
        org_add = request.form.get('org_add')
        org_type = request.form.get('org_type')
        validity = request.form.get('validity')
        status = request.form.get('status')
        region = request.form.get('region')
        
        required_fields = [
            bus_id, accreditation, bus_name,
            org_add, org_type, validity, status, region
        ]

        if any(not str(field).strip() for field in required_fields):
            flash("All fields are required!", "error")
            return render_template('enroll.html')

        conn = get_db()
        cursor = conn.cursor()
        
        try:

            cursor.execute("""
                INSERT INTO driving_schools (
                    bus_id, accreditation, bus_name,
                    cap1, cap2, cap3, total,
                    org_add, org_type, validity,
                    status, region
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                bus_id, accreditation, bus_name,
                cap1, cap2, cap3, total,
                org_add, org_type, validity,
                status, region
            ))

            conn.commit()

        except sqlite3.IntegrityError:
            conn.rollback()
            flash("Business ID already exists!", "error")
            return redirect(url_for('enroll'))

        finally:
            conn.close()
        log_action(
            session['username'],
            session['role'],
            f"Added new driving school '{bus_name}'"
        )

        flash("Driving School enrolled successfully!", "success")

        # return redirect('/manage')
        return render_template('enroll.html')

    return render_template('enroll.html')


# MANAGEMENT PAGE
@app.route('/manage')
def manage():
    if 'role' not in session:
        return redirect('/login')

    search = request.args.get('search', '').strip()
    region = request.args.get('region', '').strip()
    page = request.args.get('page', 1, type=int)

    per_page = 50
    offset = (page - 1) * per_page

    conn = get_db()
    cursor = conn.cursor()

    params = []
    conditions = []

    # ===============================
    # SEARCH (same as admin style)
    # ===============================
    if search:
        fields = [
            "bus_id",
            "accreditation",
            "bus_name",
            "org_add",
            "org_type",
            "validity",
            "status",
            "region"
        ]

        search_conditions = " OR ".join(
            [f"LOWER({field}) LIKE LOWER(?)" for field in fields]
        )

        conditions.append(f"({search_conditions})")
        params.extend([f"%{search}%"] * len(fields))

    # ===============================
    # REGION FILTER
    # ===============================
    if region:
        conditions.append("region = ?")
        params.append(region)

    # ===============================
    # WHERE CLAUSE
    # ===============================
    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # ===============================
    # COUNT ALL MATCHES
    # ===============================
    count_query = f"""
        SELECT COUNT(*)
        FROM driving_schools
        {where_clause}
    """

    cursor.execute(count_query, params)
    total_rows = cursor.fetchone()[0]

    total_pages = max(1, (total_rows + per_page - 1) // per_page)

    # If page too high after filtering
    if page > total_pages:
        page = total_pages
        offset = (page - 1) * per_page

    # ===============================
    # FETCH FILTERED RESULTS
    # ===============================
    query = f"""
        SELECT *
        FROM driving_schools
        {where_clause}

        ORDER BY
        CASE region
            WHEN 'NCR' THEN 1
            WHEN 'CAR' THEN 2
            WHEN 'Region I' THEN 3
            WHEN 'Region II' THEN 4
            WHEN 'Region III' THEN 5
            WHEN 'Region IV-A' THEN 6
            WHEN 'Region IV-B' THEN 7
            WHEN 'Region V' THEN 8
            WHEN 'Region VI' THEN 9
            WHEN 'Region VII' THEN 10
            WHEN 'Region VIII' THEN 11
            WHEN 'Region IX' THEN 12
            WHEN 'Region X' THEN 13
            WHEN 'Region XI' THEN 14
            WHEN 'Region XII' THEN 15
            WHEN 'Region XIII' THEN 16
            WHEN 'BARMM' THEN 17
            ELSE 99
        END,
        bus_id ASC

        LIMIT ? OFFSET ?
    """

    cursor.execute(query, params + [per_page, offset])
    rows = cursor.fetchall()
    conn.close()

    # ===============================
    # STATUS + DATE PROCESSING
    # ===============================
    updated_rows = []

    for row in rows:

        validity_str = row[10]
        display_validity = ""

        computed_status = "Pending"
        display_status = "Pending"

        expiry_date = None

        try:
            if validity_str:

                try:
                    expiry_date = datetime.strptime(validity_str, "%Y-%m-%d")
                except:
                    expiry_date = datetime.strptime(validity_str, "%m/%d/%Y")

                display_validity = expiry_date.strftime("%Y-%m-%d")

        except:
            display_validity = validity_str

        try:
            if expiry_date:

                days_left = (expiry_date - datetime.now()).days

                if days_left < 0:
                    computed_status = "Expired"
                    display_status = "Expired"

                elif days_left <= 60:
                    computed_status = "Expiring Soon"
                    display_status = f"Active\n \n(Expiring in {days_left} day(s))"

                else:
                    computed_status = "Active"
                    display_status = "Active"

            else:
                computed_status = "Pending"
                display_status = "Pending"

        except:
            computed_status = "Pending"
            display_status = "Invalid Date"

        updated_rows.append(
            list(row) + [
                computed_status,
                display_status,
                display_validity
            ]
        )

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({
            "schools": updated_rows,
            "page": page,
            "total_pages": total_pages
        })

    return render_template(
        "manage.html",
        schools=updated_rows,
        page=page,
        total_pages=total_pages,
        search=search,
        region=region
    )
    
@app.route('/add_inline', methods=['POST'])
def add_inline():
    if 'username' not in session:
        return jsonify({"success": False, "message": "Unauthorized"})

    data = request.get_json()

    # Extract safely
    bus_id = (data.get('bus_id') or '').strip()
    accreditation = (data.get('accreditation') or '').strip()
    bus_name = (data.get('bus_name') or '').strip()
    org_add = (data.get('org_add') or '').strip()
    org_type = (data.get('org_type') or '').strip()
    validity = normalize_date(data.get('validity')).strip()
    status = (data.get('status') or '').strip()
    region = (data.get('region') or '').strip()

    try:
        cap1 = int(data.get('cap1') or 0)
        cap2 = int(data.get('cap2') or 0)
        cap3 = int(data.get('cap3') or 0)

    except:
        return jsonify({
            "success": False,
            "message": "CDE, TDC, PDC must be numbers"
        })

    total = cap1 + cap2 + cap3

    if not all([bus_id, accreditation, bus_name, org_add, org_type, validity, status, region]):
        return jsonify({
            "success": False,
            "message": "All fields are required"
        })

    if status not in ["Active", "Expired", "Pending"]:
        return jsonify({
            "success": False,
            "message": "Invalid status value"
        })

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id FROM driving_schools
        WHERE bus_id=?
    """, (bus_id,))

    if cursor.fetchone():
        conn.close()
        return jsonify({
            "success": False,
            "message": "Business ID already exists"
        })

    try:
        cursor.execute("""
            INSERT INTO driving_schools 
            (bus_id, accreditation, bus_name,
            cap1, cap2, cap3, total,
            org_add, org_type, validity, status, region)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            bus_id, accreditation, bus_name,
            cap1, cap2, cap3, total,
            org_add, org_type, validity, status, region
        ))

        conn.commit()
        new_id = cursor.lastrowid

        try:
            log_action(
                session['username'],
                session['role'],
                f"Added new driving school '{bus_name}'"
            )
        except Exception as e:
            print(f"log_action failed: {e}")

        conn.close()

        return jsonify({
            "success": True,
            "new_row": {
                "id": new_id,
                "bus_id": bus_id,
                "accreditation": accreditation,
                "bus_name": bus_name,
                "cap1": cap1,
                "cap2": cap2,
                "cap3": cap3,
                "total": total,
                "org_add": org_add,
                "org_type": org_type,
                "validity": validity,
                "status": status,
                "region": region
            }
        })

    except sqlite3.IntegrityError:
        return jsonify({
            "success": False,
            "message": "Bus ID already exists."
        })

    except Exception as e:
        conn.close()
        print(f"Unexpected error in add_inline: {e}")
        return jsonify({
            "success": False,
            "message": "Server error during insert."
        })

@app.route('/delete_inline/<int:id>', methods=['POST'])
def delete_inline(id):
    if 'username' not in session:
        return {"success": False}
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT bus_name FROM driving_schools WHERE id = ?", (id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return {"success": False}

        bus_name = row[0]

        cursor.execute("DELETE FROM driving_schools WHERE id = ?", (id,))
        conn.commit()
        conn.close()

        log_action(
            session['username'],
            session['role'],
            f"Deleted driving school '{bus_name}'"
        )

        # return {"success": True}
        return {
            "success": True,
            "message": f"'{bus_name}' deleted successfully."
        }
    
    except Exception:
        return jsonify({
        "success": False,
        "message": "Delete failed"
    })

@app.route('/update_inline_full', methods=['POST'])
@admin_required
def update_inline_full():
    try:
        data = request.get_json()

        id = data['id']

        # Safe Conversion 
        cap1 = int(data.get('cap1') or 0)
        cap2 = int(data.get('cap2') or 0)
        cap3 = int(data.get('cap3') or 0)

        total = cap1 + cap2 + cap3

        conn = get_db()
        cursor = conn.cursor()
        
        # Get Old Data First
        cursor.execute("SELECT * FROM driving_schools WHERE id=?", (id,))
        old = cursor.fetchone()

        if not old:
            conn.close()
            return {"status": "error", "message": "Record not found"}
        
        # Map old values (adjust indexes if needed)
        old_data = {
            "bus_id": old[1],
            "accreditation": old[2],
            "bus_name": old[3],
            "cap1": old[4],
            "cap2": old[5],
            "cap3": old[6],
            "total": old[7],
            "org_add": old[8],
            "org_type": old[9],
            "validity": old[10],
            "status": old[11],
            "region": old[12]
        }

        # New Data
        new_data = {
            "bus_id": data.get('bus_id'),
            "accreditation": data.get('accreditation'),
            "bus_name": data.get('bus_name'),
            "cap1": cap1,
            "cap2": cap2,
            "cap3": cap3,
            "total": total,
            "org_add": data.get('org_add'),
            "org_type": data.get('org_type'),
            "validity": normalize_date(data.get('validity')),
            "status": data.get('status'),
            "region": data.get('region')
        }

        field_names = {
            "bus_id": "Business ID",
            "accreditation": "Accreditation",
            "bus_name": "Business Name",
            "status": "Status",
            "cap1": "CDE",
            "cap2": "TDC",
            "cap3": "PDC",
            "total": "Total",
            "org_add": "Address",
            "org_type": "Organization Type",
            "region": "Region"
        }
        
        cursor.execute("""
        SELECT id FROM driving_schools
        WHERE (bus_id=?)
        AND id != ?
        """, (
            new_data['bus_id'],
            id
        ))

        if cursor.fetchone():
            conn.close()
            return jsonify({
                "success": False,
                "message": "Business ID already used by another record"
            })
        
        # Compare Changes
        changes = []
        for key in new_data:
            if str(old_data[key]) != str(new_data[key]):
                readable = field_names.get(key, key)
                changes.append(f"{readable}: {old_data[key]} → {new_data[key]}")
        
        cursor.execute("""
            UPDATE driving_schools
            SET bus_id=?, accreditation=?, bus_name=?,
                cap1=?, cap2=?, cap3=?, total=?,
                org_add=?, org_type=?, validity=?, status=?, region=?
            WHERE id=?
            """, (
                new_data['bus_id'],
                new_data['accreditation'],
                new_data['bus_name'],
                new_data['cap1'],
                new_data['cap2'],
                new_data['cap3'],
                new_data['total'],
                new_data['org_add'],
                new_data['org_type'],
                new_data['validity'],
                new_data['status'],
                new_data['region'],
                id
        ))
        conn.commit()
        conn.close()
        
        # Smart Logging
        if changes:
            change_text = "| ".join(changes)
            message = f"Updated '{old_data['bus_name']}' ({change_text})"
            log_action(
            session['username'],
            session['role'],
            message
            )
        else:
            message = f"No changes made to '{old_data['bus_name']}'"
            log_action(session['username'], session['role'], message)

        # return {"status": "success"}
        return jsonify({
            "success": True,
            "message": "Record updated successfully!"
        })
    
    except Exception as e:
        print("UPDATE ERROR:", e)
        return jsonify({
            "success": False,
            "message": str(e)
        })

@app.route('/admin/users')
@admin_required
def admin_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    conn.close()
    return render_template('admin/users.html', users=users)

@app.route('/admin/logs')
def audit_logs():

    search = request.args.get('search', '').strip()
    role = request.args.get('role', '').strip()
    date = request.args.get('date', '').strip()

    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM audit_logs WHERE 1=1"
    params = []

    if search:
        query += " AND LOWER(username) LIKE LOWER(?)"
        params.append(f"%{search}%")

    if role:
        query += " AND role=?"
        params.append(role)

    if date:
        query += " AND DATE(timestamp)=?"
        params.append(date)

    query += " ORDER BY timestamp DESC"
    cursor.execute(query, params)
    logs = cursor.fetchall()
    
    for log in logs:
        print(log[4])
    
    logs = sorted(logs, key=lambda x: x[4], reverse=True)

    conn.close()

    return render_template("admin/logs.html", logs=logs)

@app.route('/export_logs')
def export_logs():

    conn = get_db()
    cursor = conn.cursor()

    search = request.args.get('search')
    role = request.args.get('role')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    query = "SELECT username, role, action, timestamp FROM audit_logs WHERE 1=1"
    params = []

    if search:
        query += " AND (username LIKE ? OR action LIKE ? OR role LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    if role:
        query += " AND role = ?"
        params.append(role)

    if date_from and date_to:
        query += " AND DATE(timestamp) BETWEEN ? AND ?"
        params.append(date_from)
        params.append(date_to)

    elif date_from:
        query += " AND DATE(timestamp) >= ?"
        params.append(date_from)

    elif date_to:
        query += " AND DATE(timestamp) <= ?"
        params.append(date_to)

    query += " ORDER BY datetime(timestamp) DESC"
    cursor.execute(query, params)
    logs = cursor.fetchall()
    conn.close()

    # CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['User', 'Role', 'Action', 'Time'])
    writer.writerows(logs)
    output.seek(0)

    def clean(value):
        return re.sub(r'[^a-zA-Z0-9_-]', '_', value)

    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    filename_parts = ["audit_logs"]

    # Determine Type
    if not any([search, role, date_from, date_to]):
        filename_parts.append("ALL")
    else:
        filename_parts.append("filtered")

        if search:
            filename_parts.append(f"search_{clean(search)}")

        if role:
            filename_parts.append(clean(role))

        if date_from and date_to:
            filename_parts.append(f"{date_from}_to_{date_to}")
        elif date_from:
            filename_parts.append(f"from_{date_from}")
        elif date_to:
            filename_parts.append(f"to_{date_to}")

    filename_parts.append(today)

    filename = "_".join(filename_parts) + ".csv"

    return Response(
        output,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )

@app.route('/admin/schools')
@admin_required
def admin_schools(): 
    if 'role' not in session:
        return redirect('/login')

    search = request.args.get('search', '').strip()
    region = request.args.get('region', '').strip()
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    
    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page

    conn = get_db()
    cursor = conn.cursor()

    # -----------------------
    # BASE FILTER (USED TWICE)
    # -----------------------
    params = []
    conditions = []

    if search:
        fields = [
            "bus_id",
            "accreditation",
            "bus_name",
            "org_add",
            "org_type",
            "validity",
            "status", 
            "region"
        ]

        search_conditions = " OR ".join([f"{field} LIKE ?" for field in fields])
        conditions.append(f"({search_conditions})")

        params.extend(['%' + search + '%'] * len(fields)) 
 
    if region:
        conditions.append("region = ?")
        params.append(region)

    # Combine into WHERE clause
    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # -----------------------
    # COUNT (FILTERED)
    # -----------------------
    cursor.execute(f"""
        SELECT COUNT(*) FROM driving_schools
        {where_clause}
    """, params)

    total_rows = cursor.fetchone()[0]
    total_pages = max(1, (total_rows + per_page - 1) // per_page)
    
    query = f"""
        SELECT * FROM driving_schools
        {where_clause}
        ORDER BY 
        CASE region
            WHEN 'NCR' THEN 1
            WHEN 'CAR' THEN 2
            WHEN 'Region I' THEN 3
            WHEN 'Region II' THEN 4
            WHEN 'Region III' THEN 5
            WHEN 'Region IV-A' THEN 6
            WHEN 'Region IV-B' THEN 7
            WHEN 'Region V' THEN 8
            WHEN 'Region VI' THEN 9
            WHEN 'Region VII' THEN 10
            WHEN 'Region VIII' THEN 11
            WHEN 'Region IX' THEN 12
            WHEN 'Region X' THEN 13
            WHEN 'Region XI' THEN 14
            WHEN 'Region XII' THEN 15
            WHEN 'Region XIII' THEN 16
            WHEN 'BARMM' THEN 17
            ELSE 99
        END,
        bus_id ASC
        LIMIT ? OFFSET ?
    """

    cursor.execute(query, params + [per_page, offset])
    rows = cursor.fetchall()
    conn.close()
        
    updated_rows = []
    for row in rows: 

        validity_str = row[10]
        display_validity = ""

        computed_status = "Pending"
        display_status = "Pending"
        days_left = None

        expiry_date = None

        # -------------------------
        # NORMALIZE DATE FORMAT
        # -------------------------
        try:
            if validity_str:
                # Try DB format first (YYYY-MM-DD)
                try:
                    expiry_date = datetime.strptime(validity_str, "%Y-%m-%d")
                except:
                    # fallback old format (MM/DD/YYYY)
                    expiry_date = datetime.strptime(validity_str, "%m/%d/%Y")

                display_validity = expiry_date.strftime("%Y-%m-%d")

        except:
            display_validity = validity_str

        # -------------------------
        # STATUS LOGIC
        # -------------------------
        try:
            if expiry_date:

                days_left = (expiry_date - datetime.now()).days

                if days_left < 0:
                    computed_status = "Expired"
                    display_status = "Expired"

                elif days_left <= 60:
                    computed_status = "Expiring Soon"
                    display_status = f"Active\n \n(Expiring in {days_left} day(s))"

                else:
                    computed_status = "Active"
                    display_status = "Active"

            else:
                computed_status = "Pending"
                display_status = "Pending"

        except:
            computed_status = "Pending"
            display_status = "Invalid Date"
                

        updated_rows.append(list(row) + [
            computed_status,
            display_status,
            display_validity
        ])

    # AFTER building updated_rows...

    if is_ajax:
        return jsonify({
            "schools": updated_rows,
            "page": page,
            "total_pages": total_pages,
            "success": True,
            "message": "Updated successfully"
        })

    return render_template(
        'admin/schools.html',
        schools=updated_rows,
        page=page,
        total_pages=total_pages,
        search=search,
        region=region
    )
        
@app.route("/check_bus_id")
def check_bus_id():
    bus_id = request.args.get("bus_id")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM driving_schools WHERE bus_id=?", (bus_id,))
    exists = cursor.fetchone() is not None

    conn.close()

    return jsonify({"exists": exists})

def generate_filename_from_data(mode, region=None):
    now = datetime.now().strftime("%Y-%m-%d_%H-%M")

    if mode == "region" and region:
        safe_region = re.sub(r'[^A-Za-z0-9_]', '', region.replace(" ", "_"))
        return f"{safe_region}_{now}"

    return f"Driving_Schools_{now}"

@app.route('/export/excel', methods=['POST'])
def export_excel():

    mode = request.json.get("mode", "all")
    region = request.json.get("region")

    query = "SELECT * FROM driving_schools"
    params = []

    # ==============================
    # FILTER
    # ==============================
    if mode == "region":
        if not region or str(region).strip() == "":
            return {"error": "Region is required"}, 400

        query += " WHERE region = ?"
        params.append(region)

    # ==============================
    # ORDER
    # ==============================
    query += """
    ORDER BY
        CASE region
            WHEN 'NCR' THEN 1
            WHEN 'CAR' THEN 2
            WHEN 'Region I' THEN 3
            WHEN 'Region II' THEN 4
            WHEN 'Region III' THEN 5
            WHEN 'Region IV-A' THEN 6
            WHEN 'Region IV-B' THEN 7
            WHEN 'Region V' THEN 8
            WHEN 'Region VI' THEN 9
            WHEN 'Region VII' THEN 10
            WHEN 'Region VIII' THEN 11
            WHEN 'Region IX' THEN 12
            WHEN 'Region X' THEN 13
            WHEN 'Region XI' THEN 14
            WHEN 'Region XII' THEN 15
            WHEN 'Region XIII' THEN 16
            WHEN 'BARMM' THEN 17
            ELSE 99
        END ASC,
        CAST(SUBSTR(bus_id, -7) AS INTEGER) ASC
    """

    conn = get_db()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    # ----------------------------
    # COLUMN HEADER MAPPING
    # ----------------------------
    export_column_map = {
        "bus_id": "Business ID",
        "accreditation": "Accreditation No.",
        "bus_name": "Business Name",

        "cap1": "CDE",
        "cap2": "TDC",
        "cap3": "PDC",
        "total": "Total", 

        "org_add": "Organization Address",
        "org_type": "Organization Types",
        "validity": "Validity",
        "status": "Status",
        "region": "Region"
    }

    df.rename(columns=export_column_map, inplace=True)

    df.drop(columns=["id"], inplace=True, errors="ignore") 

    # ----------------------------
    # EXPORT FILE
    # ----------------------------
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    filename = generate_filename_from_data(mode, region)
 
    if mode == "region":
        log_msg = f"Exported Excel (Region: {region})"
    else:
        log_msg = "Exported Excel (All Regions)"

    log_action(
        session['username'],
        session['role'],
        log_msg
    )

    return send_file(
        output,
        download_name=filename + ".xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route('/export/pdf', methods=['POST'])
def export_pdf():

    mode = request.json.get("mode", "all")
    region = request.json.get("region")

    # ==============================
    # QUERY
    # ==============================
    query = "SELECT * FROM driving_schools"
    params = []

    # FILTER
    if mode == "region":
        if not region or str(region).strip() == "":
            return {"error": "Region is required"}, 400

        query += " WHERE region = ?"
        params.append(region)

    # ORDER
    query += """
    ORDER BY
        CASE region
            WHEN 'NCR' THEN 1
            WHEN 'CAR' THEN 2
            WHEN 'Region I' THEN 3
            WHEN 'Region II' THEN 4
            WHEN 'Region III' THEN 5
            WHEN 'Region IV-A' THEN 6
            WHEN 'Region IV-B' THEN 7
            WHEN 'Region V' THEN 8
            WHEN 'Region VI' THEN 9
            WHEN 'Region VII' THEN 10
            WHEN 'Region VIII' THEN 11
            WHEN 'Region IX' THEN 12
            WHEN 'Region X' THEN 13
            WHEN 'Region XI' THEN 14
            WHEN 'Region XII' THEN 15
            WHEN 'Region XIII' THEN 16
            WHEN 'BARMM' THEN 17
            ELSE 99
        END ASC,
        CAST(SUBSTR(bus_id, -7) AS INTEGER) ASC
    """

    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    # ==============================
    # COLUMN MAPPING (DB → UI)
    # ==============================
    export_column_map = {
        "bus_id": "Business ID",
        "accreditation": "Accreditation No.",
        "bus_name": "Business Name",

        "cap1": "CDE",
        "cap2": "TDC",
        "cap3": "PDC",
        "total": "Total", 

        "org_add": "Organization Address",
        "org_type": "Organization Types",
        "validity": "Validity",
        "status": "Status",
        "region": "Region"
    }

    # ==============================
    # BUILD CLEAN DATA
    # ==============================
    data = []

    if rows:

        dict_rows = [dict(row) for row in rows]

        # DROP ID
        for r in dict_rows:
            r.pop("id", None)

        # RENAME COLUMNS
        cleaned_rows = []
        for r in dict_rows:
            cleaned_rows.append({
                export_column_map.get(k, k): v
                for k, v in r.items()
            })

        headers = list(cleaned_rows[0].keys())
        data.append(headers)

        for r in cleaned_rows:
            data.append(list(r.values()))

    else:
        data.append(["No data found"])

    # ==============================
    # PDF SETUP
    # ==============================
    buffer = io.BytesIO()

    pdf = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=20,
        leftMargin=20,
        topMargin=20,
        bottomMargin=20
    )

    styles = getSampleStyleSheet()

    title_style = styles["Title"]
    title_style.alignment = 1

    normal_style = styles["Normal"]

    header_style = styles["Normal"]
    header_style.fontSize = 7
    header_style.leading = 8

    # ==============================
    # HEADER
    # ==============================
    title = Paragraph("""
        <b style="font-size:16px;">DRIVING SCHOOLS REPORT</b><br/>
        <font size="9">Land Transportation Office - Central Office</font>
    """, title_style)

    header = Table([[Table([[title]])]], colWidths=[pdf.width])

    header.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))

    spacer = Spacer(1, 12)

    # ==============================
    # NO-WRAP COLUMNS (IMPORTANT FIX)
    # ==============================
    no_wrap_columns = {
        "Business ID",
        "Accreditation No.",
        "Validity",   
        "Region"
    }

    # ==============================
    # WRAP DATA
    # ==============================
    wrapped_data = []

    for i, row in enumerate(data):
        new_row = []

        for col_index, cell in enumerate(row):
            text = str(cell)
            col_name = data[0][col_index]

            if i == 0:
                new_row.append(Paragraph(f"<b>{text}</b>", header_style))
            else:
                if col_name in no_wrap_columns:
                    # FORCE SINGLE LINE (IMPORTANT)
                    new_row.append(Paragraph(f"<nobr>{text}</nobr>", normal_style))
                else:
                    new_row.append(Paragraph(text, normal_style))

        wrapped_data.append(new_row)

    # ==============================
    # SMART COLUMN WIDTHS
    # ==============================
    available_width = pdf.width - 10

    col_max_len = defaultdict(int)

    for row in wrapped_data:
        for i, cell in enumerate(row):
            col_max_len[i] = max(col_max_len[i], len(str(cell)))

    num_cols = len(wrapped_data[0])

    MIN_WEIGHT = 8
    weights = []

    for i in range(num_cols):
        w = col_max_len[i]

        header_name = str(wrapped_data[0][i])

        if "Address" in header_name:
            w *= 1.5
        elif "Organization" in header_name:
            w *= 1.5
        elif "Name" in header_name:
            w *= 1.3
        elif header_name in ["Business ID", "Accreditation No.", "Validity"]:
            w *= 0.90   

        if w < MIN_WEIGHT:
            w = MIN_WEIGHT

        weights.append(w)

    total_weight = sum(weights)

    col_widths = [
        (w / total_weight) * available_width
        for w in weights
    ]

    # ==============================
    # TABLE
    # ==============================
    table = Table(
        wrapped_data,
        colWidths=col_widths,
        repeatRows=1
    )

    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.skyblue),  
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),

        ('FONTSIZE', (0,0), (-1,-1), 7),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),

        ('GRID', (0,0), (-1,-1), 0.5, colors.black),

        ('LEFTPADDING', (0,0), (-1,-1), 3),
        ('RIGHTPADDING', (0,0), (-1,-1), 3),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))

    # ==============================
    # BUILD PDF
    # ==============================
    elements = [header, spacer, table]

    pdf.build(elements)
    buffer.seek(0)

    filename = generate_filename_from_data(mode, region) 

    # ==============================
    # LOGGING
    # ============================== 
    if mode == "region":
        log_msg = f"Exported PDF (Region: {region})"
    else:
        log_msg = "Exported PDF (All Regions)"

    log_action(
        session['username'],
        session['role'],
        log_msg
    )

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename + ".pdf",
        mimetype="application/pdf"
    )

# LOGOUT
@app.route('/logout')
def logout():
    username = session.get('username')

    if username:
        log_action(session['username'], session['role'], "Logged out")

    session.clear()
    return redirect(url_for('login'))

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

if __name__ == "__main__":
    app.run(debug=True)


