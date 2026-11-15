# System & Cloud Architecture

## 1. High-Level System Architecture

The **Hotel Booking Platform** is engineered as a cloud-native, multi-container microservice deployed on an **AWS EC2 Ubuntu 24.04** host. It incorporates automated Continuous Integration and Continuous Deployment (CI/CD) with zero static credentials using **GitHub Actions OIDC** and **AWS Systems Manager (SSM)**.

```mermaid
flowchart TD
    Client(["Internet Clients / Mobile & Web Apps"]) -->|"HTTPS (Port 443)\nTLS 1.3 / Let's Encrypt"| NGINX["Nginx Reverse Proxy\n(Host: 13.48.120.203)"]
    
    subgraph EC2_Host ["AWS EC2 Host (Ubuntu 24.04 LTS - t3.small)"]
        NGINX -->|"HTTP Proxy Pass\n(127.0.0.1:8000)"| FastAPI["FastAPI API Service\n(Container: hotel-booking-api)\nUser: appuser (UID 10001)"]
        FastAPI -->|"SQLAlchemy 2.0 / psycopg3\n(Bridge: db:5432)"| Postgres["PostgreSQL 16 Engine\n(Container: hotel-booking-db)"]
        Postgres -->|"Data Mount"| DockerVol[("Docker Named Volume\npostgres_data")]
        
        CronBackup["Daily Cron Backup Job\n(/usr/local/bin/backup-db.sh)"] -->|"pg_dump"| Postgres
    end

    subgraph AWS_Cloud ["AWS Cloud Infrastructure (eu-north-1 Stockholm)"]
        CronBackup -->|"AWS CLI (EC2 IAM Role)\nAES-256 Encrypted"| S3Bucket[("Amazon S3 Bucket\nhotel-booking-backup-sneha\n(Versioning + 30d Lifecycle)")]
        SSM["AWS Systems Manager\n(SSM Run Command)"] -->|"ssm-agent IPC"| EC2_Host
    end

    subgraph CI_CD ["GitHub Actions Automation"]
        Dev["Developer Push / PR"] -->|"Triggers"| CI["CI Workflow (.github/workflows/ci.yml)\n• Pytest (PostgreSQL Service)\n• Docker Build & Tagging"]
        CI -->|"workflow_run: success"| CD["CD Workflow (.github/workflows/cd.yml)\n• AWS OIDC Authentication\n• SSM SendCommand Dispatch"]
        CD -->|"AssumeRole"| IAMRole["IAM Role: GitHubHotelBookingDeployRole"]
        IAMRole -->|"Authorize"| SSM
    end
```

---

## 2. Component Breakdown

### 2.1 Backend Application Layer (`api`)
* **Framework:** FastAPI (Python 3.13-slim) running via `uvicorn` ASGI server.
* **Security Context:** Hardened container running as unprivileged system user `appuser` (UID 10001).
* **Data Access:** SQLAlchemy 2.0 ORM with asynchronous-ready `psycopg` binary driver.
* **Concurrency Engine:** Implements row-level pessimistic locking (`SELECT ... FOR UPDATE`) on the `rooms` table to guarantee zero double-bookings under concurrent load.
* **Endpoints:**
  - `GET /` — Service status check.
  - `GET /health` — Application liveness probe.
  - `GET /ready` — Deep readiness probe validating database connectivity.
  - `GET /db-test` — Database connectivity and dialect test.
  - `GET /rooms` & `GET /rooms/{id}` — Room catalog.
  - `POST /reservations` — Atomic booking creation with overlap conflict detection.
  - `GET /availability` — Dynamic vacancy search excluding confirmed overlapping bookings.
  - `GET /docs` — OpenAPI / Swagger interactive documentation.

### 2.2 Database & Persistence Layer (`db`)
* **Database Engine:** PostgreSQL 16 Alpine.
* **Network Binding:** Strictly bound to `127.0.0.1:5432` on the EC2 host. Only reachable from the Docker bridge network by the `api` container.
* **Storage Engine:** Persistent Docker named volume `postgres_data` mapped to `/var/lib/postgresql/data`. Survives container lifecycles, upgrades, and rollbacks.
* **Healthcheck:** Monitored continuously using `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}`.

### 2.3 Edge Ingress & Networking (`nginx`)
* **Reverse Proxy:** Nginx 1.24 terminates TLS/SSL and proxies requests locally to `http://127.0.0.1:8000`.
* **TLS Security:** Let's Encrypt TLS certificate with automatic renewal via Certbot.
* **HTTP Redirection:** Port 80 unconditionally issues HTTP 301 Permanent Redirect to HTTPS on port 443.
* **Header Forwarding:** Propagates `Host`, `X-Real-IP`, `X-Forwarded-For`, and `X-Forwarded-Proto` for accurate client telemetry.

---

## 3. CI/CD Architecture & Zero-Secret Deployment

The deployment pipeline uses modern **OpenID Connect (OIDC)** authentication, eliminating the need to store long-lived AWS Access Keys or SSH private keys in GitHub repository secrets:

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Developer
    participant GH as GitHub Actions (CD Runner)
    participant OIDC as AWS IAM OIDC Provider
    participant IAM as Role: GitHubHotelBookingDeployRole
    participant SSM as AWS Systems Manager
    participant EC2 as EC2 Instance (i-03d455ea3e1887798)
    participant App as Docker Compose (hotel-booking-api)

    Dev->>GH: Push commit to main branch
    Note over GH: CI Pipeline succeeds (Pytest + Docker build)
    GH->>OIDC: Request short-lived OIDC JSON Web Token (JWT)
    OIDC->>IAM: Validate JWT claims (repo, branch, aud)
    IAM-->>GH: Issue temporary AWS STS credentials (1-hour validity)
    GH->>SSM: Send-Command (AWS-RunShellScript)
    SSM->>EC2: Deliver deploy command to amazon-ssm-agent
    Note over EC2: Execute scripts/deploy.sh as ubuntu user
    EC2->>EC2: git pull origin main
    EC2->>EC2: docker compose config -q
    EC2->>App: docker compose up -d --build --no-deps api
    Note over App: Start new container with updated image
    EC2->>App: Probe http://127.0.0.1:8000/health & /ready
    App-->>EC2: HTTP 200 OK
    EC2-->>SSM: Report Command Execution Success (Exit 0)
    SSM-->>GH: Status: Success
    GH-->>Dev: Pipeline Green ✅
```

---

## 4. Disaster Recovery & Backup Architecture

* **Automated Daily Dumps:** Linux `cron` triggers `/usr/local/bin/backup-db.sh` daily at 02:00 UTC.
* **Atomic Backup:** Executes `pg_dump` inside the `hotel-booking-db` container, compressing output to `.sql.gz`.
* **Encrypted Object Storage:** Streams compressed backups to private Amazon S3 bucket `hotel-booking-backup-sneha` in `eu-north-1`.
* **Retention Policy:** Versioning protects against accidental overwrites; S3 Lifecycle rules automatically transition older dumps and purge after 30 days.
