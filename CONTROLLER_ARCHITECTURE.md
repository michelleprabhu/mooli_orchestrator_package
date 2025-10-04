# Controller Architecture - Implementation Guide

## Current Status ✅

### What's Working Now:
1. **Database**: PostgreSQL running with all tables created
2. **Backend API**: Running on `http://localhost:8765`
   - REST API endpoints for organizations, orchestrators
   - Authentication with bearer token
3. **WebSocket Server**: Integrated into backend on `ws://localhost:8765/ws`
   - Accepts orchestrator connections
   - Handles handshake and heartbeats
4. **Frontend**: React app ready to run on `http://localhost:8080`

---

## Your Requirements (What Needs to Be Built)

### 1. **Frontend CRUD for Orchestrators**

**What you want:**
- From the Controller Frontend, create/delete orchestrator instances
- Each action should be logged in the database
- UI shows which orchestrators are active/connected

**Status:** ✅ **PARTIALLY WORKING**
- Frontend has the UI (`organizations.tsx`)
- API endpoints exist:
  - `POST /api/v1/controller/orchestrator-instances` - Create
  - `DELETE /api/v1/controller/orchestrator-instances/{id}` - Delete
  - `GET /api/v1/controller/orchestrators/live` - Show active ones

**What's Missing:**
- The frontend needs to be started (run `npm run dev` in `controller/app/gui/frontend/`)
- Database permissions need to be fixed (see error in logs about "permission denied for table organizations")

---

### 2. **Heartbeat Monitoring**

**What you want:**
- Ongoing heartbeat between WebSocket server (controller) and WebSocket client (orchestrator)
- Heartbeat logged to show orchestrator is active
- Cron job monitors heartbeats

**Status:** ✅ **WORKING**
- WebSocket connection established on `ws://localhost:8765/ws`
- Heartbeat poker cron runs every 30s (configured in `.env`)
- Orchestrator sends `i_am_alive` messages every 10s
- Controller sends `controller_heartbeat` back every 20s
- Heartbeats update `orchestrator_instances.last_seen` in database

**Files Involved:**
- `controller/app/main.py` - WebSocket endpoint at `/ws`
- `controller/app/cron/heartbeat_poker.py` - Monitors heartbeats
- `orchestrator/app/ws_client.py` - Sends heartbeats

---

### 3. **Independence Mode**

**What you want:**
- From controller FE, mark orchestrator as "independent"
- When independent, heartbeat stops
- Reflected in:
  - UI
  - Orchestrator's `.env` file
  - FE shows orchestrator is independent

**Status:** ⚠️ **PARTIALLY IMPLEMENTED**

**What Exists:**
- Database columns: `orchestrator_instances.is_independent` and `orchestrator_instances.privacy_mode`
- API endpoints:
  - `PUT /api/v1/internal/orchestrators/{id}/independence` - Set independence
  - `GET /api/v1/internal/orchestrators/{id}/independence` - Get status

**What's Missing:**
1. **Frontend UI** to toggle independence mode
2. **Logic to stop heartbeat** when independence is enabled
3. **Write to orchestrator's .env file** (this is complex - see below)

**Challenge with .env writing:**
- The orchestrator runs in a separate process/container
- Controller cannot directly modify orchestrator's `.env` file
- **Solution**: Orchestrator should poll for its independence status and update its own config

---

### 4. **Monitoring/Recommendation Messages**

**What you want:**
- Orchestrator sends monitoring/recommendation messages to controller
- Controller can see and accept these messages

**Status:** ❌ **NOT IMPLEMENTED**

**What Needs to Be Done:**
1. Add message type `monitoring_report` or `recommendation` to orchestrator
2. Orchestrator sends these messages via WebSocket
3. Controller receives and stores in database (new table?)
4. Frontend displays these messages

---

## Architecture Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    CONTROLLER (Port 8765)                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐          ┌──────────────┐               │
│  │   Frontend   │          │  Backend API │               │
│  │  (React/     │─HTTP────▶│  (FastAPI)   │               │
│  │   Vite)      │          │              │               │
│  │  Port 8080   │◀─────────│  Port 8765   │               │
│  └──────────────┘          └──────┬───────┘               │
│                                   │                         │
│                                   │                         │
│                            ┌──────▼───────┐                │
│                            │  WebSocket   │                │
│                            │   Endpoint   │                │
│                            │   /ws        │                │
│                            └──────┬───────┘                │
│                                   │                         │
│                            ┌──────▼───────┐                │
│                            │  PostgreSQL  │                │
│                            │   Database   │                │
│                            └──────────────┘                │
└─────────────────────────────────────────────────────────────┘
                                   │
                                   │ WebSocket
                                   │ (ws://localhost:8765/ws)
                                   │
┌──────────────────────────────────▼──────────────────────────┐
│                    ORCHESTRATOR                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐          ┌──────────────┐               │
│  │  WS Client   │          │   Backend    │               │
│  │  (ws_client  │──────────│   (FastAPI)  │               │
│  │   .py)       │          │              │               │
│  └──────────────┘          └──────────────┘               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### Key Tables:

1. **`organizations`** - Organization master data
   - `organization_id` (PK)
   - `name`, `location`, `is_active`
   - `settings` (JSON) - includes features

2. **`orchestrator_instances`** - Orchestrator instances (one per organization)
   - `orchestrator_id` (PK) - matches organization_id
   - `organization_name`, `location`
   - `status` (active/inactive)
   - `last_seen` - Last heartbeat timestamp
   - `is_independent`, `privacy_mode`
   - `features` (JSON)

3. **`orchestrators`** - Legacy table for backward compatibility
   - `orchestrator_id` (PK)
   - `organization_id`
   - `last_heartbeat`

4. **`activity_logs`** - Audit trail
   - All CRUD operations logged here

---

## How to Test the Complete Flow

### Step 1: Start Controller

```bash
cd /Users/michelleprabhu/Desktop/mooli_orchestrator_package
python -m controller.app.main
```

This starts:
- REST API on port 8765
- WebSocket server on ws://localhost:8765/ws
- Heartbeat poker cron

### Step 2: Start Frontend

```bash
cd controller/app/gui/frontend
npm install  # if not already done
npm run dev
```

Frontend will start on http://localhost:8080

### Step 3: Start Orchestrator (WebSocket Client)

The orchestrator needs to be configured to connect to:
```
CONTROLLER_WS_URL=ws://localhost:8765/ws
```

OR update the orchestrator's .env to add:
```
CONTROLLER_HOST=localhost
CONTROLLER_PORT=8765
CONTROLLER_WS_PATH=/ws
```

Then run:
```bash
cd orchestrator
python -m app.ws_client
```

### Step 4: Verify Connection

1. Check controller logs for: `[C-OCS] Orchestrator xxx connected`
2. Check orchestrator logs for: `[O-CCS] handshake_ack received`
3. Watch for ongoing heartbeat messages

### Step 5: Test from Frontend

1. Go to http://localhost:8080
2. Navigate to Organizations page
3. Create a new organization
4. Watch it appear in the list
5. Once orchestrator connects, it should show as "active"

---

## What Still Needs to Be Done

### Priority 1: Database Permissions
```sql
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO moolai;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO moolai;
```

### Priority 2: Frontend Independence Toggle
Add UI in `organizations.tsx` to:
- Show independence status
- Toggle independence mode
- Call `PUT /api/v1/internal/orchestrators/{id}/independence`

### Priority 3: Stop Heartbeat on Independence
When `is_independent=true`:
- Controller should not expect heartbeats
- Orchestrator should disconnect gracefully
- Status should show "independent" not "inactive"

### Priority 4: Monitoring Messages
1. Define message schema
2. Add handler in controller WebSocket endpoint
3. Store in database
4. Display in frontend

---

## Environment Configuration

### Controller `.env` (controller/app/.env):
```env
# Database
DATABASE_URL=postgresql+asyncpg://moolai:moolai@127.0.0.1:5432/moolai_controller

# Ports
PORT=8765
CONTROLLER_OCS_HTTP_PORT=8010

# Heartbeat
HEARTBEAT_POKE_INTERVAL_SEC=30
HEARTBEAT_TTL_SEC=600

# CORS
ALLOWED_ORIGINS=http://localhost:8080

# Auth (dev)
DEV_BEARER_TOKEN=fake-dev-token
```

### Orchestrator `.env`:
```env
# Controller connection
CONTROLLER_HOST=localhost
CONTROLLER_PORT=8765
CONTROLLER_WS_PATH=/ws

# Or use full URL:
CONTROLLER_WS_URL=ws://localhost:8765/ws

# Keepalive
WEBSOCKET_KEEPALIVE_INTERVAL=10

# Identity
ORCHESTRATOR_ID=orch-001
```

---

## Common Issues & Solutions

### 1. "Address already in use" on port 8765
```bash
pkill -9 -f "python.*controller.app.main"
```

### 2. "Permission denied for table organizations"
```sql
psql -U postgres
GRANT ALL ON ALL TABLES IN SCHEMA public TO moolai;
```

### 3. WebSocket connection fails
- Ensure controller is running on port 8765
- Check WebSocket endpoint is `/ws`
- Verify orchestrator is using correct URL

### 4. Heartbeat not showing in frontend
- Check `orchestrator_instances.last_seen` is updating
- Verify heartbeat poker is running (check logs)
- Ensure orchestrator is sending `i_am_alive` messages

---

## Next Steps

1. ✅ Fix database permissions
2. ✅ Start the frontend
3. ✅ Configure orchestrator to connect to `/ws`
4. ✅ Test full flow: create → connect → heartbeat → delete
5. ⚠️ Implement independence mode UI
6. ⚠️ Implement monitoring/recommendation messages


