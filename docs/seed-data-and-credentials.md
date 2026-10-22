# Seed Data & Developer Credentials Reference

This document provides a comprehensive guide to database seeding, login portals, pre-configured development credentials, and CLI commands for the People HRMS codebase.

---

## 1. Does the Seed Data Start Automatically on First Server Boot?

### Short Answer:
**Only the baseline Super Admin account and Organization are created automatically.** The rich 45+ employee workforce, departments, units, leave ledgers, and attendance data are **not** seeded automatically on startup—they are seeded on-demand via a CLI command.

### Detailed Lifecycle:
When you start the FastAPI backend (`uv run fastapi dev main.py`):
1. **Tables & Schema**: FastAPI lifespan checks `settings.is_development`. If true, it runs `create_db_and_tables()`, ensuring all PostgreSQL tables exist.
2. **Baseline Bootstrap ([`db/seed.py`](file:///D:/Projects/people/app/api/db/seed.py))**:
   - If `BOOTSTRAP_SEED_DATA=true` or in development mode, it calls `ensure_seed_data()`.
   - This creates **only**:
     - 1 baseline `Organization` record (`Bharat Dynamics & Tech Solutions Ltd.` or from `.env.local`)
     - 1 technical `superadmin` user account
3. **Why the Full Workforce Isn't Auto-Seeded on Startup**:
   - Populating 45+ employees with biometric punches, double-entry leave ledgers, and audit logs takes a few seconds. Running it automatically on every restart would slow down developer reload and `pytest` runs.
   - Therefore, the complete Indian enterprise dataset is triggered with a single CLI command whenever needed.

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

#### Key Pre-Configured Personas

| Persona / Designation | Business Role | Access Scope | Username | Mobile Number | Official Email |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CEO / Org Owner** | `ORGANIZATION_OWNER` | Organization | `rajesh.sharma` | `+919810101010` | `rajesh.sharma@bharatdynamics.co.in` |
| **HR Director** | `HR_ADMIN` | Organization | `priya.nair` | `+919820202020` | `priya.nair@bharatdynamics.co.in` |
| **Bengaluru HRBP** | `HR_ADMIN` | Unit (`BLR-01`) | `ananya.iyer` | `+919830303030` | `ananya.iyer@bharatdynamics.co.in` |
| **Hyderabad HRBP** | `HR_ADMIN` | Unit (`HYD-01`) | `suresh.reddy` | `+919840404040` | `suresh.reddy@bharatdynamics.co.in` |
| **Engineering Manager** | `DEPARTMENT_MANAGER` | Dept (`ENG-HYD`) | `vikram.malhotra` | `+919850505050` | `vikram.malhotra@bharatdynamics.co.in` |
| **Platform Manager** | `DEPARTMENT_MANAGER` | Dept (`ENG-BLR`) | `rohit.verma` | `+919860606060` | `rohit.verma@bharatdynamics.co.in` |
| **Product Manager** | `DEPARTMENT_MANAGER` | Dept (`PRD-BLR`) | `sneha.rao` | `+919870707070` | `sneha.rao@bharatdynamics.co.in` |
| **QA Lead** | `DEPARTMENT_MANAGER` | Dept (`QA-HYD`) | `arjun.kapoor` | `+919880808080` | `arjun.kapoor@bharatdynamics.co.in` |
| **Finance Manager** | `DEPARTMENT_MANAGER` | Dept (`FIN-BOM`) | `kavita.deshmukh` | `+919890909090` | `kavita.deshmukh@bharatdynamics.co.in` |
| **Sales Director** | `DEPARTMENT_MANAGER` | Dept (`SLS-BOM`) | `amit.sen` | `+919900000000` | `amit.sen@bharatdynamics.co.in` |
| **Operations Lead** | `DEPARTMENT_MANAGER` | Dept (`OPS-GGN`) | `deepak.joshi` | `+919911111111` | `deepak.joshi@bharatdynamics.co.in` |
| **Sample Team Member** | `EMPLOYEE` | Self | `xavier.solanki.112` | `+916910116526` | `xavier.solanki.112@bharatdynamics.co.in` |

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
- Built using Python's `Faker("en_IN")` with seed `42` for 100% deterministic, reproducible data.
- **Enterprise Entities Created**:
  - **Organization**: Bharat Dynamics & Tech Solutions Ltd. (Cyber Gateway, HITEC City, Hyderabad).
  - **5 Regional Units**: Hyderabad, Bengaluru, Mumbai, Pune, and Gurugram.
  - **16 Departments**: Engineering, Product, QA, HR, Finance, Operations, Sales across units.
  - **Designation Ladder**: Standard Indian IT & corporate hierarchy (CEO, CTO, DIR-HR, DIR-ENG, LEAD-PM, SR-SE, QA-ENG, etc.).
  - **4 Shifts**: General (`GEN`: 09:00–18:00), Morning (`MORN`), Evening (`EVE`), Night (`NGT`).
  - **17 Gazetted Indian Holidays (2026)**: Republic Day, Maha Shivratri, Holi, Eid, Independence Day, Diwali, Christmas, etc.
  - **7 Leave Types**: Casual Leave (`CL`), Privilege Leave (`EL`), Sick Leave (`SL`), Compensatory Off (`COMP`), Maternity (`ML`), Paternity (`PL`), Loss of Pay (`LOP`).
  - **Statutory Profiles**: Authentic Indian PAN (`ABCDE1234F`), 12-digit Aadhaar, and bank accounts across SBI, HDFC, ICICI, Axis, and Kotak with valid IFSC codes.
  - **Operational Records**: Biometric attendance punches (`BIO-BDTS-xxxx`), attendance regularizations, overtime records, and realistic leave applications (e.g., weddings in Jaipur, Diwali, seasonal fever).

---

## 4. CLI Commands for Seeding Data

Always run backend seed commands from `app/api/`:

```bash
cd app/api
```

### A. Seed / Update Indian Data (Non-destructive)
Populates missing records without deleting existing data:
```bash
uv run python db/seed_indian_data.py
```

### B. Clean & Re-Seed Fresh Data (Recommended)
Wipes application records clean (cascade truncates) while preserving Alembic migration versions and the Super Admin account, then populates a clean dataset:
```bash
uv run python db/seed_indian_data.py --clean
```

### C. Seed with Custom Workforce Size
Generate a larger or smaller employee pool:
```bash
uv run python db/seed_indian_data.py --clean --num-employees 60
```
