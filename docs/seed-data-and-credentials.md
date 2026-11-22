# Seed Data & Developer Credentials Reference

This document provides a comprehensive guide to database seeding, login portals, pre-configured development credentials, and CLI commands for the People HRMS codebase.

---

## 1. Does the Seed Data Start Automatically on First Server Boot?

### Short Answer:
**Only the baseline Super Admin account and Organization are created automatically on server boot.** The role-focused workforce personas (14 employees across 4 departments), units, leave balances, and flow records are seeded on-demand via a fast CLI command (`uv run python db/seed_indian_data.py --clean`).

### Detailed Lifecycle:
When you start the FastAPI backend (`uv run fastapi dev main.py`):
1. **Tables & Schema**: FastAPI lifespan checks `settings.is_development`. If true, it runs `create_db_and_tables()`, ensuring all PostgreSQL tables exist.
2. **Baseline Bootstrap ([`db/seed.py`](file:///home/adawatia/Projects/Personal/people/app/api/db/seed.py))**:
   - If `BOOTSTRAP_SEED_DATA=true` or in development mode, it calls `ensure_seed_data()`.
   - This creates **only**:
     - 1 baseline `Organization` record (`Bharat Dynamics & Tech Solutions Ltd.` or from `.env.local`)
     - 1 technical `superadmin` user account
3. **On-Demand Role Workforce Seeding**:
   - Running `uv run python db/seed_indian_data.py --clean` resets and populates the minimal role-based dataset in under 1 second.


---

## 2. Developer Login Portals & Credentials

The system divides human authentication into two separate portals:

### A. Workforce & Employee Portal
- **Web URL**: `http://localhost:3000/login`
- **API Endpoint**: `POST /api/v1/auth/employee/login`
- **Universal Dev Password**:
  ```text
  HrmsDev@2026!
  ```
  *(Every single employee, manager, HR admin, and the CEO uses this password)*
- **Accepted Identifiers**: You can log in using either the **Username** or the Indian **Mobile Number** (with `+91` or just 10 digits).

#### Pre-Configured Test Personas (14 Workforce Accounts + 1 Super Admin)

| Persona / Designation | Business Role | Access Scope | Department / Unit | Username | Mobile Number | Reports To |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **CEO / Org Owner** | `ORGANIZATION_OWNER` | Organization | Executive (`ENG-HYD`) | `rajesh.sharma` | `+919810101010` | *(None)* |
| **HR Director** | `HR_ADMIN` | Organization | HR (`HR-HYD`) | `priya.nair` | `+919820202020` | `rajesh.sharma` |
| **Hyderabad HRBP** | `HR_ADMIN` | Unit (`HYD-01`) | HR (`HR-HYD`) | `suresh.reddy` | `+919840404040` | `priya.nair` |
| **Engineering Manager** | `DEPARTMENT_MANAGER` | Dept (`ENG-HYD`) | Engineering (`ENG-HYD`) | `vikram.malhotra` | `+919850505050` | `rajesh.sharma` |
| **Bengaluru HRBP** | `HR_ADMIN` | Unit (`BLR-01`) | HR (`HR-BLR`) | `ananya.iyer` | `+919830303030` | `priya.nair` |
| **Platform Manager** | `DEPARTMENT_MANAGER` | Dept (`ENG-BLR`) | Engineering (`ENG-BLR`) | `rohit.verma` | `+919860606060` | `rajesh.sharma` |
| **Senior Software Eng** | `EMPLOYEE` | Self | Engineering (`ENG-HYD`) | `rahul.sharma` | `+919876543210` | `vikram.malhotra` |
| **Software Engineer** | `EMPLOYEE` | Self | Engineering (`ENG-HYD`) | `neha.gupta` | `+919876543211` | `vikram.malhotra` |
| **HR Operations Exec** | `EMPLOYEE` | Self | HR (`HR-HYD`) | `kavya.nair` | `+919876543212` | `suresh.reddy` |
| **HR Operations Exec** | `EMPLOYEE` | Self | HR (`HR-HYD`) | `arun.kumar` | `+919876543213` | `suresh.reddy` |
| **Senior Software Eng** | `EMPLOYEE` | Self | Engineering (`ENG-BLR`) | `priya.verma` | `+919876543214` | `rohit.verma` |
| **Software Engineer** | `EMPLOYEE` | Self | Engineering (`ENG-BLR`) | `amit.patel` | `+919876543215` | `rohit.verma` |
| **HR Operations Exec** | `EMPLOYEE` | Self | HR (`HR-BLR`) | `pooja.deshmukh` | `+919876543216` | `ananya.iyer` |
| **HR Operations Exec** | `EMPLOYEE` | Self | HR (`HR-BLR`) | `deepak.joshi` | `+919876543217` | `ananya.iyer` |


---

### B. Technical Administrator Portal
- **Web URL**: `http://localhost:3000/admin/login`
- **API Endpoint**: `POST /api/v1/auth/super-admin/login`
- **Username**: `superadmin`
- **Password**:
  ```text
  DevAdmin@123
  ```
  *(Configured via `SUPER_ADMIN_PASSWORD` in `app/api/.env.local`)*
- **Accepted Identifier**: Technical username only (email and phone number logins are blocked on this portal).
- **Purpose**: System-level controls, ERP client secret management, audit logs, and break-glass maintenance.

---

## 3. Seed Files Architecture

The project has two seeding modules located in `app/api/db/`:

```
app/api/db/
├── seed.py                # Server lifespan bootstrap & table creation
└── seed_indian_data.py    # Complete enterprise dataset generator (Faker 'en_IN')
```

### 1. `db/seed.py`
- Exposes `create_db_and_tables()`: Runs `Base.metadata.create_all` using SQLAlchemy.
- Exposes `ensure_seed_data()`: Idempotently creates the baseline Organization and Super Admin account.
- Exposes `ensure_indian_seed_data()`: Helper function that invokes `seed_indian_data()`.

### 2. `db/seed_indian_data.py`
- Streamlined, zero-bloat deterministic seed module.
- **Enterprise Entities Created**:
  - **Organization**: Bharat Dynamics & Tech Solutions Ltd. (Cyber Gateway, HITEC City, Hyderabad).
  - **2 Regional Units**: Hyderabad Tech Campus (`HYD-01`) and Bengaluru Innovation Hub (`BLR-01`).
  - **4 Departments**: Engineering & Architecture (`ENG-HYD`), HR Operations (`HR-HYD`), Platform Engineering (`ENG-BLR`), HR Operations (`HR-BLR`).
  - **Role-Focused Workforce**: Exactly 14 workforce employees (CEO, HR Director, 4 Managers, and at least 2 direct report employees per department) + 1 Super Admin (15 total users).
  - **2 Shifts**: General Day Shift (`GEN`: 09:30–18:30) and Early Morning Shift (`MORN`: 06:30–15:30).
  - **4 Gazetted Indian Holidays (2026)**: Republic Day, Independence Day, Mahatma Gandhi Jayanti, Diwali.
  - **5 Leave Types**: Casual Leave (`CL`: 12 days), Privilege Leave (`EL`: 18 days), Sick Leave (`SL`: 10 days), Compensatory Off (`COMP`: 6 days), Loss of Pay (`LOP`).
  - **Pre-Wired Flow States**:
    - PENDING Leave Applications (Rahul -> Vikram in Hyd, Neha -> Vikram in Hyd, Priya -> Rohit in Blr for cross-department visibility testing).
    - APPROVED Leave Application with balance deduction, double-entry ledger debit, and synced ERP outbox event.
    - PENDING Attendance Regularization & Discrepancy (Rahul -> Vikram).
    - PENDING Work Arrangement / WFH Request (Rahul -> Vikram).
    - PENDING Overtime Claim (Rahul -> Vikram).
    - 3-day recent attendance records with biometric IN/OUT punches.
    - Targeted manager alerts, employee approval notices, and broadcast announcements.


---

## 4. CLI Commands for Seeding Data

Always run backend seed commands from `app/api/`:

```bash
cd app/api
```

### A. Clean & Re-Seed Fresh Data (Recommended)
Wipes application records clean (cascade truncates) while preserving Alembic migration versions and the Super Admin account, then populates the lean role dataset:
```bash
uv run python db/seed_indian_data.py --clean
```

### B. Seed / Update Indian Data (Non-destructive)
Populates missing records without deleting existing data:
```bash
uv run python db/seed_indian_data.py
```



---

## 5. Cleaning & Wiping the Database

The repository includes a dedicated safety-guarded script: [`app/api/cleanup_db.py`](file:///D:/Projects/people/app/api/cleanup_db.py).

### Safety Guards Built-In:
- **Dry-Run Preview**: Running without `--execute` only prints the tables that would be deleted.
- **Explicit Confirmation**: Requires `--confirm "DELETE ALL HRMS DATA"`.
- **Environment Checks**: Refuses to run on remote hosts or non-development environments without explicit override flags (`--allow-remote`, `--allow-production`).
- **Preserved Records**: Keeps `alembic_version` (migration history) and the Super Admin account intact by default.

### Cleaning Commands (from `app/api/`):

1. **Preview what tables will be emptied (Dry Run - completely safe)**:
   ```bash
   uv run python cleanup_db.py
   ```

2. **Execute Full Database Cleanup (Leaves DB empty with Super Admin preserved)**:
   ```bash
   uv run python cleanup_db.py --execute --confirm "DELETE ALL HRMS DATA"
   ```

3. **Cleanup and Recreate Baseline Bootstrap Organization + Super Admin**:
   ```bash
   uv run python cleanup_db.py --execute --confirm "DELETE ALL HRMS DATA" --reseed-bootstrap
   ```

4. **Cleanup and Wipe Everything Including Super Admin (with fresh Super Admin creation)**:
   ```bash
   uv run python cleanup_db.py --execute --confirm "DELETE ALL HRMS DATA" --delete-super-admin --reseed-bootstrap --admin-username superadmin --admin-password "DevAdmin@123"
   ```

---

## 6. Industry Standards: Why Cleaning and Seeding Are Separated

A common question is: *Should database cleaning be part of the seed script or kept separate?*

In this codebase, we adhere to the **industry standard pattern used across modern web frameworks** (Django, Rails, Prisma, Laravel): **modular separation with an opt-in reset shortcut**.

### Framework Comparison

| Framework | Pure Clean / Wipe | Pure Seed / Populate | Combined Reset Shortcut |
| :--- | :--- | :--- | :--- |
| **Django (Python)** | `python manage.py flush` | `python manage.py loaddata` | *(manual combination)* |
| **Rails (Ruby)** | `rails db:truncate` / `db:purge` | `rails db:seed` | `rails db:reset` |
| **Prisma (Node/TS)** | `prisma migrate reset --skip-seed` | `prisma db seed` | `prisma migrate reset` |
| **Laravel (PHP)** | `php artisan db:wipe` | `php artisan db:seed` | `php artisan migrate:fresh --seed` |
| **People HRMS** | `uv run python cleanup_db.py --execute ...` | `uv run python db/seed_indian_data.py` | `uv run python db/seed_indian_data.py --clean` |

### Why This Separation Is Best Practice:

1. **Accidental Data Loss Prevention (Safety)**:
   If seeding always wiped the database, running a seed command to add missing records or update reference holidays would destroy days of manual test data that a developer or QA engineer created.
   - **Default Seeding is Idempotent**: It inserts missing records and does not delete existing user work.
   - **Wiping is Explicit**: Wiping tables requires the user to opt-in via `--clean` or `--confirm`.

2. **Testing "Zero-State" / Initial UI**:
   Developers regularly need an empty database to test:
   - What does the dashboard display when an organization has 0 employees?
   - How does the onboarding wizard or ERP sync behave on a blank installation?
   - If cleaning always auto-seeded, testing these empty states would be impossible.

3. **Environment Safety in Shared / Staging Deployments**:
   In staging or demo environments, developers may seed lookup data (e.g. 2026 holiday calendar). Having `cleanup_db.py` enforce strict `--confirm "DELETE ALL HRMS DATA"` guards prevents accidental data loss on shared databases.

---

## 7. Developer Cheat Sheet: Which Command Should I Run?

| Your Goal | Recommended Command (from `app/api/`) |
| :--- | :--- |
| **"I want a clean database with all 14 role personas and testing flows (2 employees per dept, zero bloat)"** | `uv run python db/seed_indian_data.py --clean` |
| **"I want an empty database to test empty UI states or fresh onboarding"** | `uv run python cleanup_db.py --execute --confirm "DELETE ALL HRMS DATA"` |
| **"I made manual test edits and only want to add missing seed records without losing my work"** | `uv run python db/seed_indian_data.py` |
| **"I just want to see which tables exist and would be emptied without touching anything"** | `uv run python cleanup_db.py` |




