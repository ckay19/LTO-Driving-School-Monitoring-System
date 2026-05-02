# **LTO Driving School Monitoring System - Documentation**



## Table of Contents

1. [System Overview](#system-overview)
2. [Technology Stack](#technology-stack)
3. [System Architecture](#system-architecture)
4. [Database Schema](#database-schema)
5. [User Roles & Permissions](#user-roles--permissions)
6. [Features & Functionality](#features--functionality)
7. [API Routes](#api-routes)
8. [Installation & Setup](#installation--setup)
9. [User Guide](#user-guide)
10. [Troubleshooting](#troubleshooting)

---

## System Overview

The **LTO Driving School Monitoring System** is a web-based application developed for the 
Land Transportation Office (LTO) of the Philippines. It provides a comprehensive platform 
for managing and monitoring driving schools across all regions in the Philippines.

### Purpose

- Centralized management of accredited driving schools
- Track validity and expiration of accreditations
- Monitor compliance with LTO regulations
- Generate reports (PDF/Excel) for administrative use
- Maintain audit trails for all system activities

---

## Technology Stack

### Backend
- **Framework:** Flask (Python)
- **Database:** SQLite
- **ORM:** Direct SQL queries via `sqlite3`

### Frontend
- **Template Engine:** Jinja2
- **Styling:** Custom CSS
- **Icons:** Bootstrap Icons

### Libraries/Dependencies
- `flask` - Web framework
- `sqlite3` - Database
- `bcrypt` - Password hashing
- `pandas` - Data manipulation for exports
- `openpyxl` - Excel export
- `reportlab` - PDF generation
- `smtplib` / `email.mime` - Email sending (OTP)

---

## System Architecture

```
┌───────────────────────────────────────────────────────────┐
│                        CLIENTS                            │
│  ┌──────────┐ ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  Admin   │ │   User   │  │   User   │  │   User   │    │
│  └────┬─────┘ └────┬─────┘  └────┬─────┘  └────┬─────┘    │
└───────┼────────────┼─────────────┼─────────────┼──────────┘
        │            │             │             │
        └────────────┴──────┬──────┴─────────────┘
                            │
                      ┌─────▼─────┐
                      │  FLASK    │
                      │  SERVER   │
                      └─────┬─────┘
                            │
        ┌───────────────────┼──────────────────────┐
        │                   │                      │
   ┌────▼─────┐        ┌────▼─────┐           ┌────▼─────┐
   │ Database │        │   CSV    │           │  Email   │
   │ SQLite   │        │ Import   │           │ Service  │
   └──────────┘        └──────────┘           └──────────┘
```

---

## Database Schema

### 1. Users Table

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE,
    username TEXT UNIQUE,
    password TEXT,
    role TEXT,
    otp TEXT,
    otp_expiry TEXT,
    is_active INTEGER DEFAULT 0
);
```

**Fields:**
| Field     | Type    | Description |
|-----------|---------|-----------------------------
| id        | INTEGER | Primary key, auto-increment
| email     | TEXT    | User's email (unique)
| username  | TEXT    | Unique username
| password  | TEXT    | Bcrypt hashed password
| role      | TEXT    | 'admin' or 'user'
| otp       | TEXT    | One-time password for verification
| otp_expiry| TEXT    | OTP expiration timestamp
| is_active | INTEGER | 0 = inactive, 1 = active

### 2. Driving Schools Table

```sql
CREATE TABLE driving_schools (
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
);
```

**Fields:**
| Field         | Type    | Description |
|---------------|---------|---------------------------------------
| id            | INTEGER | Primary key, auto-increment
| bus_id        | TEXT    | Business ID (unique)
| accreditation | TEXT    | LTO Accreditation Number
| bus_name      | TEXT    | Business Name
| cap1          | INTEGER | CDE (Driver's Education) count
| cap2          | INTEGER | TDC (Theoretical Driving Course) count
| cap3          | INTEGER | PDC (Practical Driving Course) count
| total         | INTEGER | Total capacities (cap1+cap2+cap3)
| org_add       | TEXT    | Full address
| org_type      | TEXT    | Organization type
| validity      | TEXT    | Validity date (YYYY-MM-DD)
| status        | TEXT    | Current status
| region        | TEXT    | Philippines region

### 3. Login Logs Table

```sql
CREATE TABLE login_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE,
    username TEXT,
    login_time TEXT
);
```

### 4. Audit Logs Table

```sql
CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT,
    username TEXT,
    action TEXT,
    timestamp TEXT
);
```

---

## User Roles & Permissions

### 1. Administrator Role
- **Username:** `admin`
- **Default Password:** `admin123`
- **Privileges:**
    - View all driving schools
    - Add/Edit/Delete driving schools
    - Export data (Excel/PDF)
    - View user accounts
    - View audit logs
    - Manage system settings

### 2. Regular User Role
- **Privileges:**
    - View driving schools (read-only)
    - Enroll new driving school
    - View own dashboard
    - Manage (filter and search)

---

## Features & Functionality

### 1. Authentication System

#### Login
- Username or email authentication
- Password verification with bcrypt
- Session management
- Role-based redirect (admin → admin panel, user → dashboard)

#### Sign Up with OTP Verification
- Email validation
- Password strength requirements:
    - Minimum 8 characters
    - At least one uppercase, lowercase, number, and special character
- OTP sent via email (valid for 5 minutes)
- OTP auto-submit on 6-digit entry

### 2. Dashboard

#### User Dashboard (`/dashboard`)
- Welcome message with username
- Quick access cards:
    - Enroll Driving School
    - Driving School Monitoring

#### Admin Dashboard
Redirects to `/admin/schools`

### 3. Driving School Management

#### Enroll Driving School (`/enroll`)
- Business ID (unique)
- Accreditation Number
- Business Name
- Capping (CDE, TDC, PDC)
- Organization Type
- Full Address (via Philippines API)
- Validity Date
- Status (Active/Expired/Pending)
- Region selection

#### Manage Driving Schools (`/manage`)
- Searchable table
- Region filter
- Pagination (50 per page)
- Auto-computed status based on validity:
  - **Active:** More than 60 days
  - **Expiring Soon:** Within 60 days
  - **Expired:** Past validity date
- Live search with debounce

### 4. Admin Panel

#### Schools Management (`/admin/schools`)
- Full CRUD operations
- Inline editing
- Add modal with address picker
- Export to Excel/PDF
- Region-specific exports

#### User Management (`/admin/users`)
- View all registered users
- Shows: Email, Username, Password (hashed)

#### Audit Logs (`/admin/logs`)
- Filter by user, role, action, date
- Search functionality
- Export to CSV

### 5. Data Import

#### CSV Import (`LTO.csv`)
- Automatic import on startup
- Column mapping:
    - `bus_id` → Business ID
    - `accreditation` → Accreditation No.
    - `bus_name` → Business Name
    - `cap1` → CDE
    - `cap2` → TDC
    - `cap3` → PDC
    - `org_add` → Organization Address
    - `org_type` → Organization Type
    - `validity` → Validity
    - `status` → Status
    - `region` → Region

### 6. Export Features

#### Excel Export (`/export/excel`)
- All data or by region
- Formatted headers
- Auto-download

#### PDF Export (`/export/pdf`)
- Landscape orientation
- Formatted table
- Professional headers
- Column auto-sizing

---

## API Routes

### Authentication Routes

| Route         | Method    | Description
|---------------|-----------|---------------------
| `/`           | GET       | Landing page
| `/login`      | GET, POST | User login
| `/signup`     | GET, POST | User registration
| `/verify_otp` | POST      | OTP verification
| `/resend_otp` | POST      | Resend OTP
| `/logout`     | GET       | Logout

### User Routes

| Route        | Method    | Description
|--------------|-----------|----------------
| `/dashboard` | GET       | User dashboard
| `/manage`    | GET       | Manage driving schools
| `/enroll`    | GET, POST | Enroll new school

### Admin Routes

| Route              | Method | Description |
|--------------------|--------|-----------------
| `/admin_dashboard` | GET    | Admin redirect
| `/admin/users`     | GET    | User management
| `/admin/logs`      | GET    | Audit logs
| `/admin/schools`   | GET    | School management

### API Endpoints

| Route                 | Method | Description |
|-----------------------|--------|--------------------
| `/add_inline`         | POST   | Add school (JSON)
| `/delete_inline/<id>` | POST   | Delete school
| `/update_inline_full` | POST   | Update school
| `/check_bus_id`       | GET    | Check ID exists
| `/export/excel`       | POST   | Export Excel
| `/export/pdf`         | POST   | Export PDF
| `/export_logs`        | GET    | Export logs CSV

---

## Installation & Setup

### Prerequisites
- Python 3.8+
- pip package manager

### Installation Steps

1. **Clone or extract the project**
    ```bash
    cd LTO
    ```

2. **Create virtual environment (optional but recommended)**
    ```bash
    python -m venv venv
    venv\Scripts\activate  # Windows
    # OR
    source venv/bin/activate  # Linux/Mac
    ```

3. **Install dependencies**
    ```bash
    pip install flask bcrypt pandas openpyxl reportlab
    ```

4. **Run the application**
    ```bash
    python app.py
    ```

5. **Access the application**
    - Open browser: `http://127.0.0.1:5000`
    - Admin login: `admin` / `admin123`

### Configuration

#### Email Settings (for OTP)
```python
sender_email = ""
app_password = ""
```

#### Secret Key
```python
app.secret_key = "secret123"  # Change in production
```

---

## User Guide

### First-Time Login

1. Navigate to `/login`
2. Enter credentials:
    - Admin: `admin` / `admin123`
3. You will be redirected to the appropriate dashboard

### Adding a New Driving School (Admin)

1. Go to **Admin Panel** → **Driving Schools**
2. Click **Add New** button
3. Fill in the form:
    - Business ID (unique)
    - Accreditation Number
    - Business Name
    - Capacities (CDE, TDC, PDC)
    - Select Region
    - Fill in address using the Philippine address picker
    - Organization Type
    - Validity Date
    - Status
4. Click **Save**

### Editing a Driving School

1. In the schools table, click the **Edit** button (✏️)
2. The row becomes editable
3. Modify the fields
4. Click **Save** to update or **Cancel** to revert

### Searching and Filtering

1. Use the **search box** to search by ID, name, address, etc.
2. Use the **region dropdown** to filter by specific region
3. Results update automatically with debounce

### Exporting Data

1. **Excel:**
   - Click **Export Excel**
    - Choose "All Data" or "By Region"
    - Click Export

2. **PDF:**
   - Click **Export PDF**
    - Choose format and region
    - Click Export

### Viewing Audit Logs

1. Go to **Admin Panel** → **Audit Logs**
2. Filter by:
    - User search
    - Role (Admin/User)
    - Date range
3. Export to CSV using the export button

---

## Troubleshooting

### Common Issues

#### 1. "Session expired" during signup
- **Cause:** OTP expired (5 minutes)
- **Solution:** Click "Resend OTP" to get a new code

#### 2. "Business ID already exists"
- **Cause:** Duplicate entry attempt
- **Solution:** Use a unique Business ID

#### 3. "Unable to verify Business ID"
- **Cause:** Network issue or server error
- **Solution:** Refresh the page and try again

#### 4. Email not received
- **Cause:** Email service issues or spam filter
- **Solution:** Check spam folder, verify email address

#### 5. Export fails
- **Cause:** Large dataset or server timeout
- **Solution:** Try exporting by region

### Database Issues

If database errors occur:
1. Delete `database.db`
2. Restart the application
3. Data will be re-imported from `LTO.csv`

### Resetting Admin Password

1. Access the database:
    ```bash
    sqlite3 database.db
    ```
2. Update password:
    ```sql
    UPDATE users SET password='$2b$12$...hashed_password...' WHERE username='admin';
    ```
3. Or recreate the admin user

---

## Security Considerations

1. **Passwords:** All passwords are hashed using bcrypt
2. **OTP:** Time-limited (5 minutes) verification
3. **Sessions:** Cleared on logout
4. **Input Validation:** Server-side validation for all inputs
5. **SQL Injection:** Parameterized queries used throughout

---

## Region Order Reference

The system uses the following regional ordering:
1. NCR - National Capital Region
2. CAR - Cordillera Administrative Region
3. Region I - Ilocos Region
4. Region II - Cagayan Valley
5. Region III - Central Luzon
6. Region IV-A - CALABARZON
7. Region IV-B - MIMAROPA
8. Region V - Bicol Region
9. Region VI - Western Visayas
10. Region VII - Central Visayas
11. Region VIII - Eastern Visayas
12. Region IX - Zamboanga Peninsula
13. Region X - Northern Mindanao
14. Region XI - Davao Region
15. Region XII - SOCCSKSARGEN
16. Region XIII - Caraga
17. BARMM - Bangsamoro Autonomous Region in Muslim Mindanao

---

## Support & Maintenance

For issues or questions:
- Check the audit logs for activity history
- Verify database integrity
- Check server logs for errors
- Ensure all dependencies are installed

---

**Document Version:** 1.0
**Last Updated:** May 2, 2026
**System:** LTO Driving School Monitoring System
