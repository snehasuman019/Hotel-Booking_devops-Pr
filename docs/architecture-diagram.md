# Architecture Diagrams

This document contains dedicated visual diagrams representing the Hotel Booking Platform's infrastructure, network security topology, database schema, and deployment workflows.

---

## 1. Cloud Infrastructure & Network Topology

```mermaid
graph TB
    subgraph Internet_Zone ["Public Internet"]
        Users["External Users & API Clients"]
        GHA["GitHub Actions Runner"]
    end

    subgraph AWS_VPC ["AWS Virtual Private Cloud (eu-north-1)"]
        subgraph Public_Subnet ["Public Subnet (Security Group: sg-hotel-booking)"]
            EIP["Elastic IP: 13.48.120.203"]
            
            subgraph EC2_VM ["EC2 Instance: i-03d455ea3e1887798 (t3.small)"]
                NGINX["Nginx Web Server\n• Port 80 (HTTP 301 Redirect)\n• Port 443 (TLS Termination)"]
                
                subgraph Docker_Network ["Docker Bridge Network (172.20.0.0/16)"]
                    API["FastAPI Container\n(hotel-booking-api:8000)\nNon-root appuser:10001"]
                    DB["PostgreSQL 16 Alpine\n(hotel-booking-db:5432)"]
                end
                
                Vol[("Docker Volume\npostgres_data")]
                SSMAgent["amazon-ssm-agent"]
                Cron["Cron Daemon\n(Daily S3 Backup)"]
            end
        end

        subgraph AWS_Managed ["AWS Managed Services"]
            S3[("Amazon S3 Bucket\nhotel-booking-backup-sneha\n(Versioning + SSE-S3)")]
            SSMService["AWS Systems Manager\n(Core & Run Command)"]
            IAM["AWS IAM / OIDC Provider\n(GitHubHotelBookingDeployRole)"]
        end
    end

    Users -->|HTTPS:443| EIP
    EIP --> NGINX
    NGINX -->|127.0.0.1:8000| API
    API -->|db:5432| DB
    DB --> Vol
    
    GHA -->|OIDC STS AssumeRole| IAM
    IAM --> SSMService
    SSMService -->|Outbound HTTPS:443| SSMAgent
    SSMAgent -.->|Dispatches scripts/deploy.sh| API

    Cron -->|aws s3 cp| S3
```

---

## 2. Database Entity-Relationship (ER) Diagram

```mermaid
erDiagram
    ROOMS ||--o{ RESERVATIONS : "has"
    ROOMS {
        int id PK "Serial auto-increment"
        string room_number UK "Unique, up to 10 chars"
        string room_type "Single, Double, Deluxe"
        numeric price_per_night "10 digits, 2 decimals"
        boolean is_active "Default true"
    }
    RESERVATIONS {
        int id PK "Serial auto-increment"
        string reference UK "Unique reference, e.g. HTL-XXXXXXXXXX"
        int room_id FK "References ROOMS(id)"
        string guest_name "Guest full name"
        date check_in "Booking start date"
        date check_out "Booking end date"
        string status "CONFIRMED, CANCELLED"
        timestamp created_at "Auto-set timestamp with timezone"
    }
```

---

## 3. Concurrency Protection & Row-Level Locking Sequence

```mermaid
sequenceDiagram
    autonumber
    actor GuestA as Guest A (Thread 1)
    actor GuestB as Guest B (Thread 2)
    participant API as FastAPI App (/reservations)
    participant DB as PostgreSQL Database

    Note over GuestA,GuestB: Simultaneous booking requests for Room 1 (Dec 01 - Dec 05)
    GuestA->>API: POST /reservations (Room 1, Dec 01-05)
    GuestB->>API: POST /reservations (Room 1, Dec 01-05)

    API->>DB: BEGIN TRANSACTION (Thread 1)
    API->>DB: SELECT * FROM rooms WHERE id = 1 FOR UPDATE (Thread 1)
    DB-->>API: Row Locked for Thread 1 ✅

    API->>DB: BEGIN TRANSACTION (Thread 2)
    API->>DB: SELECT * FROM rooms WHERE id = 1 FOR UPDATE (Thread 2)
    Note over DB: Thread 2 is BLOCKED waiting on Room 1 lock ⏳

    API->>DB: Check overlapping bookings (Thread 1)
    DB-->>API: None found
    API->>DB: INSERT reservation & COMMIT (Thread 1)
    DB-->>API: Commit complete. Row Lock Released! 🔓
    API-->>GuestA: HTTP 201 Created (Ref: HTL-A1B2C3D4E5)

    Note over DB: Lock acquired by Thread 2!
    DB-->>API: Row Returned to Thread 2
    API->>DB: Check overlapping bookings (Thread 2)
    DB-->>API: Found Reservation from Guest A! (Conflict)
    API->>DB: ROLLBACK (Thread 2)
    API-->>GuestB: HTTP 409 Conflict ("Room is already booked for these dates")
```
