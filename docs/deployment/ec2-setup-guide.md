# AWS EC2 Deployment Guide — People HRMS

A complete, production-grade guide for deploying the **People HRMS (Emploi)** monorepo on an **AWS EC2 `t3.small`** instance for testing and staging.

---

## 1. Architecture Overview

```
                                      ┌────────────────────────────────────────────────────────┐
                                      │                     Public Client                      │
                                      │              (Browser, Mobile PWA, Postman)            │
                                      └───────────────────────────┬────────────────────────────┘
                                                                  │
                                                    HTTPS (Port 443, Let's Encrypt TLS)
                                                                  │
                                                                  ▼
┌─────────────────────────────────────────────────────────────────┴────────────────────────────────────────┐
│ AWS EC2 (t3.small: 2 vCPUs, 2 GiB RAM, 4 GiB Swap, Ubuntu 24.04 LTS)                                     │
│                                                                                                          │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                                       Nginx Reverse Proxy                                        │   │
│   └───────────────────────┬──────────────────────────────────────────────────┬───────────────────────┘   │
│                           │                                                  │                           │
│     /docs, /redoc,        │                                                  │  /, /login, /api/session, │
│     /openapi.json,        │                                                  │  /api/hrms, UI assets     │
│     /api/v1/integrations  │                                                  │                           │
│                           ▼                                                  ▼                           │
│   ┌──────────────────────────────────────────────┐   ┌───────────────────────────────────────────────┐   │
│   │           FastAPI Backend Engine             │   │             Nuxt 4 Frontend & BFF             │   │
│   │          (127.0.0.1:8000 via Uvicorn)        │   │           (127.0.0.1:3000 via Nitro)          │   │
│   │  - Python 3.14 (managed by Astral uv)        │   │  - Node.js 22 LTS, Vue 3, Tailwind CSS        │   │
│   │  - SQLAlchemy 2.0 Async, Alembic             │   │  - Cookie Session Store (__Host- HttpOnly)    │   │
│   │  - Argon2 Password Hash, TOTP MFA AES-256    │   │  - CSRF Origin Guard, Outbox Feed UI          │   │
│   └──────────────────────┬───────────────────────┘   └───────────────────────┬───────────────────────┘   │
│                          │                                                   │                           │
│                          │                                                   │ Loopback BFF Proxy        │
│                          ▼                                                   │ (never exposes raw JWT)   │
│   ┌──────────────────────────────────────────────────────────────────────────┴───────────────────────┐   │
│   │                                    PostgreSQL 16 Database                                        │   │
│   │                                       (127.0.0.1:5432)                                           │   │
│   │  - Organizations, Units, Departments, Designations, Shifts, Punches, Leaves, Outbox Events       │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Inventory of Tools, Services & Technologies

| Category | Technology | Version / Spec | Purpose in this Stack |
| :--- | :--- | :--- | :--- |
| **Cloud Compute** | **AWS EC2** | `t3.small` | Burstable 2-vCPU, 2-GiB RAM virtual server hosting all application components. |
| **Block Storage** | **AWS EBS** | `gp3` (30 GiB) | General-purpose solid-state storage volume for OS, database, caches, and repository. |
| **Firewall** | **AWS Security Group** | Inbound: 22, 80, 443 | Restricts network entry to secure management (SSH) and standard web traffic. |
| **Virtual Memory** | **Linux Swap** | 4 GiB | Disk-backed virtual memory paging file (`/swapfile`) to prevent OOM errors during Vite/Nuxt builds. |
| **Operating System** | **Ubuntu Linux** | 24.04 LTS | Long-Term Support Linux server operating system. |
| **Dynamic DNS** | **`sslip.io`** | Wildcard DNS | Zero-configuration DNS resolving dashed IPs (e.g. `16-179-29-185.sslip.io`) to public IPv4. |
| **Web Server & Proxy**| **Nginx** | 1.28+ | High-performance reverse proxy handling SSL termination and port multiplexing (:8000 and :3000). |
| **SSL / TLS Certificate**| **Certbot & Let's Encrypt** | ACME v2 | Automated toolchain provisioning and renewing free, trusted HTTPS certificates. |
| **Database** | **PostgreSQL** | 16 | Relational ACID database holding all schemas, sessions, transactions, and audit logs. |
| **Database Driver** | **`psycopg`** | 3.3+ | Asynchronous native PostgreSQL connection driver for Python. |
| **Python Toolchain** | **`uv` (Astral)** | Latest | High-performance Python package installer, lockfile resolver, and toolchain manager. |
| **Python Runtime** | **Python** | 3.14 | Standalone Python runtime provisioned automatically by `uv` based on `.python-version`. |
| **Backend Framework**| **FastAPI** | 0.141+ | Asynchronous web framework serving REST endpoints and OpenAPI documentation. |
| **ASGI Server** | **Uvicorn** | 0.52+ | High-throughput async web server running the FastAPI app. |
| **ORM & Migrations** | **SQLAlchemy & Alembic** | 2.0+ / 1.19+ | Async relational data models and version-controlled database schema migrations. |
| **Node.js Runtime** | **Node.js** | v22 LTS | JavaScript server-side runtime engine. |
| **Package Manager** | **`pnpm`** | v12+ | Fast, disk-space efficient Node package manager. |
| **Frontend Framework**| **Nuxt 4** | 4.6+ | Vue 3 meta-framework handling SSR and BFF security routing. |
| **BFF Server Engine** | **Nitro** | Embedded | Edge-ready server managing `__Host-` HttpOnly cookies and internal FastAPI proxying. |
| **UI Components & CSS**| **Nuxt UI & Tailwind CSS** | v4.11+ / v4+ | Accessible Vue UI library and modern utility-first stylesheet framework. |
| **Process Daemon** | **`systemd`** | Built-in | Linux service manager keeping backend and frontend daemons active with boot-time startup. |
| **Log Streaming** | **`journalctl`** | Built-in | Linux systemd log aggregator for streaming application logs in real time. |

---

## 3. Step-by-Step Deployment Walkthrough

### Phase 1: Launch EC2 Instance & Allocate Swap Memory

1. **Launch EC2 Instance**:
   - **AMI**: Ubuntu Server 24.04 LTS (x86_64).
   - **Instance Type**: `t3.small` (2 vCPU, 2 GiB Memory).
   - **Storage**: 30 GiB gp3 root volume.
   - **Security Group Inbound Rules**:
     - `SSH (22)`: Your IP (or `0.0.0.0/0`)
     - `HTTP (80)`: `0.0.0.0/0`
     - `HTTPS (443)`: `0.0.0.0/0`

2. **Connect via SSH**:
   ```bash
   ssh -i /path/to/key.pem ubuntu@<EC2-PUBLIC-IP>
   ```

3. **Configure 4GB Swap Space (Mandatory)**:
   > [!IMPORTANT]
   > Nuxt 4 compilation (`pnpm build`) requires more than 1.5 GiB of RAM. Without a swap file on a 2 GiB instance, the Linux kernel OOM killer will terminate the build with `Killed`.
   ```bash
   sudo fallocate -l 4G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   free -h
   ```

---

### Phase 2: Install Base Packages & PostgreSQL 16

1. **Update system packages and install tools**:
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y git curl ufw build-essential libpq-dev nginx certbot python3-certbot-nginx
   ```

2. **Install and configure PostgreSQL 16**:
   ```bash
   sudo apt install -y postgresql postgresql-contrib
   sudo systemctl enable --now postgresql
   ```

3. **Create Database and User**:
   > [!TIP]
   > Use an alphanumeric password (e.g. `AdminPassword2026`) without special characters (`@`, `:`, `/`) to prevent URL parsing errors in `DATABASE_URL`.
   ```bash
   sudo -u postgres psql <<EOF
   CREATE USER "hrms-user" WITH PASSWORD 'AdminPassword2026';
   CREATE DATABASE "hrms-db" OWNER "hrms-user";
   GRANT ALL PRIVILEGES ON DATABASE "hrms-db" TO "hrms-user";
   \q
EOF
   ```

---

### Phase 3: Install Node.js 22 LTS, pnpm & uv

1. **Install Node.js 22 and pnpm**:
   ```bash
   curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
   sudo apt install -y nodejs
   sudo npm install -g pnpm
   ```

2. **Install Astral `uv` (Python Package Manager)**:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   source $HOME/.local/bin/env
   ```

---

### Phase 4: Git Authentication for Private Repository

Choose one of these methods to clone your private repository:

#### Method A: SSH Deploy Key (Recommended for Dedicated Servers)
1. Generate an SSH key on EC2:
   ```bash
   ssh-keygen -t ed25519 -C "ec2-people-test"
   # Press Enter for defaults and no passphrase
   ```
2. Display the public key:
   ```bash
   cat ~/.ssh/id_ed25519.pub
   ```
3. Add the key in GitHub/GitLab:
   - Repository **Settings** → **Deploy keys** → **Add deploy key**.
   - Title: `EC2 Testing Server`, paste key, leave "Allow write access" unchecked.

#### Method B: GitHub Personal Access Token (PAT)
Generate a fine-grained token with `Contents: Read` permission on GitHub, then clone with:
```bash
git clone https://<USERNAME>:<TOKEN>@github.com/<org>/<repo>.git people
```

---

### Phase 5: Clone Repository to `/var/www`

We use `/var/www` to comply with the Linux Filesystem Hierarchy Standard (FHS), ensuring Nginx service daemons have reliable read permissions without conflicting with `/home/ubuntu`.

```bash
sudo mkdir -p /var/www
sudo chown -R ubuntu:ubuntu /var/www
cd /var/www
git clone git@github.com:<your-org>/<your-repo>.git people
# or https URL with token
cd /var/www/people

# Switch to desired branch if needed:
git checkout <branch-name>
```

---

### Phase 6: Configure & Bootstrap Backend (`app/api`)

1. **Generate Security Secrets**:
   ```bash
   JWT_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
   MFA_KEY=$(python3 -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
   ERP_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(24))")
   ```

2. **Detect Public Domain**:
   ```bash
   PUBLIC_IP=$(curl -s https://checkip.amazonaws.com)
   DOMAIN=$(echo $PUBLIC_IP | tr '.' '-').sslip.io
   echo "Configuring domain: $DOMAIN"
   ```

3. **Create `app/api/.env`**:
   ```bash
   cd /var/www/people/app/api
   cat > .env <<EOF
   ENVIRONMENT=development
   EXPOSE_API_DOCS=true
   TIMEZONE=Asia/Kolkata

   DATABASE_URL=postgresql+psycopg://hrms-user:AdminPassword2026@127.0.0.1:5432/hrms-db
   POSTGRES_HOST=127.0.0.1
   POSTGRES_PORT=5432
   POSTGRES_USER=hrms-user
   POSTGRES_PASSWORD=AdminPassword2026
   POSTGRES_DB=hrms-db

   JWT_SECRET=${JWT_KEY}
   MFA_ENCRYPTION_KEY=${MFA_KEY}
   MFA_ENABLED=true
   MFA_REQUIRED_FOR_SUPER_ADMIN=false

   FRONTEND_URL=https://${DOMAIN}
   CORS_ORIGINS=https://${DOMAIN},http://localhost:3000

   AUTH_THROTTLE_BACKEND=memory
   SUPER_ADMIN_USERNAME=superadmin
   SUPER_ADMIN_PASSWORD=SuperAdmin@123
   SUPER_ADMIN_EMAIL=admin@hrms.com

   ERP_API_CLIENTS={"primary-erp": {"secret": "${ERP_SECRET}", "scopes": ["*"]}}
   ERP_API_KEY=dev-static-erp-key-12345
   EOF
   ```

4. **Sync Python Dependencies, Run Migrations & Seed Data**:
   ```bash
   # uv provisions standalone Python 3.14 automatically
   uv sync

   # Apply all Alembic migrations to create tables
   uv run alembic upgrade head

   # Seed pre-wired Indian organization personas and pending workflows
   uv run python db/seed_indian_data.py --clean
   ```

---

### Phase 7: Configure & Build Frontend (`app/web`)

1. **Create `app/web/.env`**:
   ```bash
   cd /var/www/people/app/web
   cat > .env <<EOF
   NUXT_HRMS_API_BASE=http://127.0.0.1:8000
   NUXT_HRMS_ALLOWED_ORIGINS=https://${DOMAIN},http://localhost:3000
   EOF
   ```

2. **Install Node Dependencies & Build Nuxt**:
   ```bash
   pnpm install

   # Memory-capped production compilation
   NODE_OPTIONS="--max-old-space-size=1536" pnpm build
   ```

---

### Phase 8: Configure Nginx & Let's Encrypt SSL

1. **Create Nginx Site Configuration**:
   ```bash
   sudo nano /etc/nginx/sites-available/hrms
   ```
   Paste the following (replace `<YOUR-DOMAIN>` with your `sslip.io` domain):
   ```nginx
   server {
       listen 80;
       server_name <YOUR-DOMAIN>;

       client_max_body_size 25M;

       # Proxy FastAPI OpenAPI interactive docs and schemas
       location ~ ^/(docs|redoc|openapi.json) {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }

       # Proxy all web application & BFF routes to Nuxt SSR
       location / {
           proxy_pass http://127.0.0.1:3000;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection 'upgrade';
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           proxy_cache_bypass $http_upgrade;
       }
   }
   ```

2. **Enable Site & Verify Configuration**:
   ```bash
   sudo ln -sf /etc/nginx/sites-available/hrms /etc/nginx/sites-enabled/
   sudo rm -f /etc/nginx/sites-enabled/default
   sudo nginx -t && sudo systemctl reload nginx
   ```

3. **Issue SSL Certificate via Certbot**:
   ```bash
   sudo certbot --nginx -d $DOMAIN
   ```
   Follow the prompts. Certbot updates Nginx automatically to redirect all HTTP traffic to HTTPS.

---

### Phase 9: Setup Background Services (`systemd`)

#### 1. Backend Service (`hrms-backend.service`)
```bash
sudo bash -c 'cat > /etc/systemd/system/hrms-backend.service <<EOF
[Unit]
Description=People HRMS FastAPI Backend
After=network.target postgresql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/var/www/people/app/api
ExecStart=/home/ubuntu/.local/bin/uv run uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5
EnvironmentFile=/var/www/people/app/api/.env

[Install]
WantedBy=multi-user.target
EOF'
```

#### 2. Frontend Service (`hrms-frontend.service`)
```bash
sudo bash -c 'cat > /etc/systemd/system/hrms-frontend.service <<EOF
[Unit]
Description=People HRMS Nuxt Web Frontend
After=network.target hrms-backend.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/var/www/people/app/web
ExecStart=/usr/bin/node /var/www/people/app/web/.output/server/index.mjs
Restart=always
RestartSec=5
Environment=PORT=3000
Environment=HOST=127.0.0.1
EnvironmentFile=/var/www/people/app/web/.env

[Install]
WantedBy=multi-user.target
EOF'
```

#### 3. Register and Start Daemons:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hrms-backend
sudo systemctl enable --now hrms-frontend
```

---

### Phase 10: Verification & Health Checks

Verify your deployment from the EC2 terminal:

```bash
# 1. Check local backend
curl -i http://127.0.0.1:8000/health
# Returns HTTP 200 OK {"status":"ok",...}

# 2. Check local frontend
curl -I http://127.0.0.1:3000
# Returns HTTP 302 Found (redirecting to /login)

# 3. Check public HTTPS
curl -I https://${DOMAIN}
# Returns HTTP 302 Found via Nginx with Secure __Host- cookies
```

---

## 4. Test Accounts & Pre-Wired Workflows

| Persona | Username | Password | Portal | Workflows Ready to Test |
| :--- | :--- | :--- | :--- | :--- |
| **Department Manager**<br>Vikram Malhotra | `vikram.malhotra` | `HrmsDev@2026!` | `/login` | Pending approvals for leave, attendance corrections, and overtime from team members. |
| **Senior Engineer**<br>Rahul Sharma | `rahul.sharma` | `HrmsDev@2026!` | `/login` | Employee self-service: View leave balance, punch in attendance, submit leave requests. |
| **HR Director**<br>Priya Nair | `priya.nair` | `HrmsDev@2026!` | `/login` | Organization-wide leave allocation, gazetted holiday schedules, shift management. |
| **Org Owner / CEO**<br>Rajesh Sharma | `rajesh.sharma` | `HrmsDev@2026!` | `/login` | Executive workforce dashboard, master attendance metrics, and company-wide trends. |
| **Super Admin** | `superadmin` | `SuperAdmin@123` | `/admin/login` | Break-glass admin portal, organization settings, and platform audit trails. |

---

## 5. Day-2 Operations Runbook

### Streaming Application Logs
```bash
# Real-time backend API logs
journalctl -u hrms-backend -f

# Real-time frontend SSR logs
journalctl -u hrms-frontend -f

# Nginx web server logs
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```

### Pulling Updates from Git
```bash
# 1. Stop daemons
sudo systemctl stop hrms-frontend hrms-backend

# 2. Update code
cd /var/www/people
git pull

# 3. Apply backend updates
cd /var/www/people/app/api
uv sync
uv run alembic upgrade head

# 4. Rebuild frontend with memory cap
cd /var/www/people/app/web
pnpm install
NODE_OPTIONS="--max-old-space-size=1536" pnpm build

# 5. Restart daemons
sudo systemctl start hrms-backend hrms-frontend
```

### Reset & Reseed Database
```bash
cd /var/www/people/app/api
uv run python db/seed_indian_data.py --clean
```

---

## 6. Troubleshooting FAQ

### 1. `FATAL: password authentication failed for user "hrms-user"`
- **Cause**: The PostgreSQL password does not match `DATABASE_URL` in `app/api/.env`, or the password contains special characters (`@`, `:`, `/`) breaking URL parsing.
- **Fix**: Reset the password to an alphanumeric string:
  ```bash
  sudo -u postgres psql -c "ALTER USER \"hrms-user\" WITH PASSWORD 'AdminPassword2026';"
  ```
  Update `DATABASE_URL` in `/var/www/people/app/api/.env` and re-test:
  ```bash
  PGPASSWORD='AdminPassword2026' psql -h 127.0.0.1 -U hrms-user -d hrms-db -c "SELECT 1;"
  ```

### 2. `Killed` or `Out of memory` during `pnpm build`
- **Cause**: The 2 GiB RAM on `t3.small` was exhausted by Vite/Tailwind.
- **Fix**: Verify swap is active with `free -h`. Always build with memory limits:
  ```bash
  NODE_OPTIONS="--max-old-space-size=1536" pnpm build
  ```

### 3. Login succeeds on server but browser immediately redirects back to `/login`
- **Cause**: Accessing the app over plain HTTP (`http://<IP>`). In production builds, Nuxt issues cookies with `__Host-` and `Secure; SameSite=Lax`. Browsers silently reject these cookies over unencrypted HTTP.
- **Fix**: Access the application through your encrypted HTTPS domain (`https://<DOMAIN>/login`) using the Let's Encrypt certificate configured in Phase 8.

### 4. `Unit hrms-backend.service not found`
- **Cause**: Systemd unit files have not been created in `/etc/systemd/system/`.
- **Fix**: Create the service files following Phase 9, run `sudo systemctl daemon-reload`, and then enable/start them.
