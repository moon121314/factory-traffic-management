# Factory Traffic Management System

A production-oriented, event-driven backend API designed to manage and orchestrate traffic at a factory intersection. Built with Python, FastAPI, and PostgreSQL, this system prioritizes deterministic state management, strict concurrency control, and fail-safe crash recovery protocols.

## Technical Stack

*   **Backend:** Python 3, FastAPI, SQLAlchemy ORM
*   **Database:** PostgreSQL
*   **Testing:** Pytest
*   **Deployment:** Render (Frontend and API), Neon (Serverless PostgreSQL)

## Live Deployment

*   **Frontend Dashboard:** https://factory-traffic-management-dashboard.onrender.com
*   **Backend API (Swagger UI):** https://factory-traffic-management-leeq.onrender.com/docs
*   *Note: The backend is hosted on Render's free tier. Initial requests may take 30 to 60 seconds to wake the service from its idle state.*

---

## System Architecture and Engineering Decisions

Managing an intersection requires strict adherence to safety protocols and the absolute prevention of conflicting states. The system was designed around the following principles:

### 1. Concurrency and Race Condition Prevention
To prevent hazardous race conditions (e.g., conflicting green lights triggered by simultaneous sensor events), the system implements **PostgreSQL row-level locking (`SELECT ... FOR UPDATE`)**. 
*   Incoming sensor events are serialized at the database level.
*   The first event acquires the lock, calculates the state transition, commits the change, and releases the lock.
*   Subsequent events evaluate against the newly updated state. This guarantees ACID compliance and prevents conflicting states, even in multi-worker deployments.

### 2. Deterministic State Machine
Traffic flow is governed by a strict state machine. It enforces minimum green times, yellow-light transition phases, and safe default states.
*   **Emergency Preemption:** `EMERGENCY` events bypass the standard queue. The state machine instantly preempts the current cycle, forces conflicting lanes to `RED`, and grants priority to the emergency lane.

### 3. Crash Recovery Protocol
To prevent physical intersections from defaulting to an unsafe state after a server restart, the system executes a two-pass startup protocol:
1.  **Pass 1:** Marks all active intersection states as `UNKNOWN`.
2.  **Pass 2:** Safely reconciles database state with the physical controller, forcing an `ALL_RED` fail-safe state before resuming the standard scheduling loop.

---

## Local Development Setup

**1. Clone the repository:**
```bash
git clone https://github.com/moon121314/factory-traffic-management.git
cd factory-traffic-management
