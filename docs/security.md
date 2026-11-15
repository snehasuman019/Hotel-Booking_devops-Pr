# Security Architecture & Best Practices

This document outlines the security controls, authentication mechanisms, network boundaries, and secret management policies applied to the **Hotel Booking Platform**.

---

## 1. Network Boundary & Defense-in-Depth

```mermaid
graph LR
    subgraph Public_Internet ["Public Zone"]
        WebTraffic["HTTPS Requests (443)"]
    end

    subgraph Host_DMZ ["Host Perimeter (EC2 OS)"]
        SG["AWS Security Group\n• Allow Ingress 80, 443\n• Block 5432, 8000, 22"]
        Nginx["Nginx Reverse Proxy\n(TLS 1.2 / TLS 1.3 Termination)"]
    end

    subgraph Internal_Private ["Internal Isolated Containers"]
        FastAPI["hotel-booking-api:8000\n(Bound to 127.0.0.1)"]
        Postgres["hotel-booking-db:5432\n(Bound to 127.0.0.1)"]
    end

    WebTraffic --> SG --> Nginx
    Nginx -->|Loopback Unix Socket / 127.0.0.1| FastAPI
    FastAPI -->|Docker Bridge Network (Internal DNS: db)| Postgres
```

### 1.1 Localhost Port Binding
* Neither PostgreSQL (5432) nor FastAPI (8000) are bound to `0.0.0.0` on the EC2 host.
* [`docker-compose.yml`](file:///e:/hotel-booking-devops/docker-compose.yml) explicitly binds ports to the host loopback interface (`127.0.0.1`):
  ```yaml
  ports:
    - "127.0.0.1:5432:5432"  # DB
    - "127.0.0.1:8000:8000"  # API
  ```
* This prevents any external IP from connecting directly to the database or application bypass of Nginx.

### 1.2 Ingress Firewalls (AWS Security Groups)
* Inbound Security Group rules permit only:
  - Port `80/tcp` (HTTP — redirects immediately to HTTPS).
  - Port `443/tcp` (HTTPS — TLS encrypted traffic).
* Port `22` (SSH) is closed to the public; operational access is handled securely via **AWS Systems Manager (SSM) Session Manager**, avoiding open management ports.

---

## 2. TLS / HTTPS Encryption

* **Certificate Authority:** Let's Encrypt automated certificate management.
* **Protocols Enforced:** Modern TLS 1.2 and TLS 1.3 ciphers.
* **HSTS / HTTP Strict Transport Security:** Enforces HTTPS on all subsequent browser requests.
* **Automated Renewal:** Certbot systemd timer tests and renews certificates automatically before expiry, executing a zero-downtime Nginx reload hook.

---

## 3. GitHub Actions OIDC Authentication (Zero Stored Keys)

Rather than storing long-lived `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in GitHub repository secrets, the deployment pipeline authenticates via **OpenID Connect (OIDC)**:

1. When the CD pipeline runs, GitHub issues a digitally signed OpenID Connect JSON Web Token (JWT).
2. The AWS STS service validates the token's audience (`sts.amazonaws.com`) and identity claims against the IAM Role Trust Policy:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": {
           "Federated": "arn:aws:iam::055280968541:oidc-provider/token.actions.githubusercontent.com"
         },
         "Action": "sts:AssumeRoleWithWebIdentity",
         "Condition": {
           "StringEquals": {
             "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
           },
           "StringLike": {
             "token.actions.githubusercontent.com:sub": "repo:snehasuman019/Hotel-Booking_devops-Pr:ref:refs/heads/main"
           }
         }
       }
     ]
   }
   ```
3. AWS STS returns temporary credentials valid for **1 hour**.
4. Once the deployment step concludes, the credentials expire automatically.

---

## 4. Container Hardening & Non-Root Execution

* **Unprivileged User:** [`Dockerfile`](file:///e:/hotel-booking-devops/Dockerfile) defines a dedicated unprivileged user `appuser` (UID 10001) and group `appgroup` (GID 10001):
  ```dockerfile
  RUN groupadd -g 10001 appgroup && \
      useradd -u 10001 -g appgroup -s /bin/bash -m appuser
  USER appuser
  ```
* **Read-Only / Principle of Least Privilege:** The application runs without root privileges, restricting potential exploit impact inside the container.

---

## 5. Secrets Management & Privacy Compliance

* **Git Secret Exclusion:** `.env` is listed in [`.gitignore`](file:///e:/hotel-booking-devops/.gitignore). Sensitive credentials (database passwords, tokens) are never committed to version control.
* **PII Sanitization in Application Logs:**
  - FastAPI application logs record operational events (e.g. `Reservation confirmed: Ref=HTL-XXXXXXXXXX, Room=1, Dates=[2026-12-01 -> 2026-12-05]`).
  - Personal identifiable information (`guest_name`, contact information) is strictly excluded from console logs to prevent PII leakage in centralized log streams.
