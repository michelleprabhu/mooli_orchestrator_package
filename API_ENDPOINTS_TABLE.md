# Moolai Controller - API Endpoints Quick Reference Table

## Complete Backend Endpoints with Database Interactions

| Endpoint | Method | Called By | Purpose | Database Tables Updated | Database Operation | Logs Generated |
|----------|--------|-----------|---------|------------------------|-------------------|----------------|
| **WebSocket Endpoints** |
| `/ws` (handshake) | WS | Orchestrator Client | Establish connection, register orchestrator | `organizations`, `orchestrator_instances` | INSERT/UPDATE both tables with orchestrator metadata | `[C-OCS] WebSocket connection accepted`<br>`[C-OCS] DB: Registered {id} in both tables`<br>`[C-OCS] Orchestrator {id} connected` |
| `/ws` (i_am_alive) | WS | Orchestrator Client | Send heartbeat to prove liveness | `orchestrator_instances` | UPDATE `last_seen`, `status='active'`, `health_status='healthy'` (only if NOT independent) | `[C-OCS] Processing heartbeat from orchestrator {id}` (normal)<br>`[C-OCS] Ignoring heartbeat from independent orchestrator {id}` (independent) |
| **Controller API (Public - /api/v1/controller)** |
| `/api/v1/controller/organizations` | GET | Frontend Dashboard | List all organizations with pagination | None | SELECT from `organizations` | None (read-only) |
| `/api/v1/controller/organizations/{id}` | GET | Frontend | Get specific organization details | None | SELECT from `organizations` WHERE `organization_id = {id}` | None (read-only) |
| `/api/v1/controller/organizations` | POST | Frontend | Create new organization | `organizations` | INSERT organization record | `INFO: Organization {id} created successfully` |
| `/api/v1/controller/orchestrators` | GET | Frontend Dashboard | List all orchestrator instances | None | SELECT from `orchestrator_instances` | None (read-only) |
| `/api/v1/controller/orchestrators/live` | GET | Frontend (every 10s) | Get currently connected orchestrators | None (in-memory only) | No database query (uses WebSocket connection state) | None (frequent polling) |
| `/api/v1/controller/orchestrator-instances` | POST | Frontend | Create orchestrator instance placeholder | `orchestrator_instances` | INSERT with `status='inactive'` | `INFO: Orchestrator instance {id} created successfully` |
| `/api/v1/controller/orchestrator-instances/{id}` | DELETE | Frontend | Delete orchestrator instance | `orchestrator_instances`, `organizations` (conditional) | DELETE instance, DELETE org if no other instances exist | `INFO: Orchestrator instance {id} deleted` |
| **Internal API (Administrative - /api/v1/internal)** |
| `/api/v1/internal/orchestrators/register` | POST | Frontend, External Systems | Register new orchestrator (creates both org and instance) | `organizations`, `orchestrator_instances` | INSERT/UPDATE both tables | `INFO: DB registration successful for {id}` |
| `/api/v1/internal/orchestrators/{id}/independence` | PUT | Frontend (Toggle Switch) | Enable/disable independence mode | `orchestrator_instances`, `organizations` | UPDATE `is_independent` flag in both tables | `INFO: Independence mode enabled for {id}`<br>`INFO: Independence setting written to environment files` |
| `/api/v1/internal/orchestrators/{id}/independence` | GET | Frontend | Check independence status | None | SELECT `is_independent` from `orchestrator_instances` | None (read-only) |
| `/api/v1/internal/orchestrators/{id}/messages` | POST | External Systems, Monitoring | Create recommendation or monitoring message | `orchestrator_messages` | INSERT message with `status='pending'` | `INFO: Message {msg_id} created for {id} (type: {type})` |
| `/api/v1/internal/orchestrators/{id}/messages` | GET | Frontend, Orchestrator | Retrieve messages for orchestrator | None | SELECT from `orchestrator_messages` WHERE `orchestrator_id={id}` | None (read-only) |
| `/api/v1/internal/messages/{msg_id}/status` | PUT | Frontend, Orchestrator | Accept or dismiss a message | `orchestrator_messages` | UPDATE `status` to 'accepted' or 'dismissed' | `INFO: Message {msg_id} status updated to '{status}'` |
| `/api/v1/internal/messages` | GET | Frontend (Admin) | Get all messages across all orchestrators | None | SELECT from `orchestrator_messages` with filters | None (read-only) |
| `/api/v1/internal/orchestrators/{id}/deregister` | DELETE | Frontend | Deregister and delete orchestrator completely | `orchestrator_messages`, `orchestrator_instances`, `organizations` | DELETE from all 3 tables (cascading) | `INFO: Orchestrator {id} disconnected`<br>`INFO: Cleaned up connection for {id}`<br>`INFO: Orchestrator {id} deregistered from database` |
| `/api/v1/internal/orchestrators/{id}/send` | POST | Internal Logic, Admin | Send message to orchestrator via WebSocket | None | No database (ephemeral WebSocket message) | `INFO: Sent message to orchestrator {id} (type: {type})` |
| `/api/v1/internal/logs` | GET | Frontend (Logs Page) | Retrieve controller application logs | None (in-memory buffer) | No database (reads from in-memory log buffer) | None (self-referential) |

---

## Database Tables Summary

| Table Name | Purpose | Key Columns | Updated By Endpoints |
|------------|---------|-------------|---------------------|
| **organizations** | Store organization/tenant metadata | `organization_id` (PK)<br>`name`<br>`location`<br>`status`<br>`is_independent`<br>`last_seen`<br>`features`<br>`settings` | WebSocket handshake<br>WebSocket heartbeat (if NOT independent)<br>POST `/organizations`<br>POST `/orchestrators/register`<br>PUT `/orchestrators/{id}/independence` |
| **orchestrator_instances** | Store individual orchestrator instance data | `orchestrator_id` (PK)<br>`organization_id` (FK)<br>`status`<br>`health_status`<br>`is_independent`<br>`last_seen`<br>`location`<br>`metadata`<br>`features` | WebSocket handshake<br>WebSocket heartbeat (if NOT independent)<br>POST `/orchestrator-instances`<br>POST `/orchestrators/register`<br>PUT `/orchestrators/{id}/independence` |
| **orchestrator_messages** | Store messages between controller and orchestrators | `id` (PK)<br>`orchestrator_id` (FK)<br>`message_type`<br>`content`<br>`status`<br>`message_metadata`<br>`created_at` | POST `/orchestrators/{id}/messages`<br>PUT `/messages/{msg_id}/status` |

---

## In-Memory State (No Database)

| Component | Purpose | Updated By |
|-----------|---------|------------|
| **controller_state.py** | Tracks active WebSocket connections, handshake/keepalive timestamps | WebSocket handshake, WebSocket heartbeat, WebSocket disconnect |
| **buffer_manager.py** | Maintains activity logs (handshake, keepalive, disconnect events) | All WebSocket events, Configuration provisioning, Message dispatch |

---

## Heartbeat Behavior by Independence Mode

| Independence Mode | Heartbeat Received | Database Updated? | Log Message |
|-------------------|-------------------|-------------------|-------------|
| **Normal (is_independent = false)** | Every 30 seconds | ✅ YES<br>Updates `last_seen`, `status='active'`, `health_status='healthy'` | `[C-OCS] Processing heartbeat from orchestrator {id}` |
| **Independent (is_independent = true)** | Every 30 seconds (still sent) | ❌ NO<br>Heartbeat ignored, no DB update | `[C-OCS] Ignoring heartbeat from independent orchestrator {id}` |

---

## Quick Reference: Which Endpoint Updates Which Table?

| Database Table | INSERT | UPDATE | DELETE |
|----------------|--------|--------|--------|
| **organizations** | • WebSocket handshake<br>• POST `/organizations`<br>• POST `/orchestrators/register` | • WebSocket handshake<br>• WebSocket heartbeat (if NOT independent)<br>• PUT `/orchestrators/{id}/independence` | • DELETE `/orchestrator-instances/{id}` (conditional)<br>• DELETE `/orchestrators/{id}/deregister` |
| **orchestrator_instances** | • WebSocket handshake<br>• POST `/orchestrator-instances`<br>• POST `/orchestrators/register` | • WebSocket handshake<br>• WebSocket heartbeat (if NOT independent)<br>• PUT `/orchestrators/{id}/independence` | • DELETE `/orchestrator-instances/{id}`<br>• DELETE `/orchestrators/{id}/deregister` |
| **orchestrator_messages** | • POST `/orchestrators/{id}/messages` | • PUT `/messages/{msg_id}/status` | • DELETE `/orchestrators/{id}/deregister` (all messages for orchestrator) |

---

## Data Flow Summary

### 1. Orchestrator Connects
```
Orchestrator → WebSocket /ws (handshake) 
  → INSERT/UPDATE organizations + orchestrator_instances 
  → Status becomes 'active'
```

### 2. Heartbeat (Normal Mode)
```
Orchestrator → WebSocket /ws (i_am_alive) 
  → Check is_independent flag 
  → UPDATE orchestrator_instances (last_seen, status, health_status)
```

### 3. Heartbeat (Independence Mode)
```
Orchestrator → WebSocket /ws (i_am_alive) 
  → Check is_independent flag 
  → Ignore heartbeat, NO database update
```

### 4. Toggle Independence
```
Frontend → PUT /orchestrators/{id}/independence 
  → UPDATE orchestrator_instances.is_independent 
  → UPDATE organizations.is_independent
```

### 5. Send Message
```
External System → POST /orchestrators/{id}/messages 
  → INSERT orchestrator_messages 
  → Status = 'pending'
```

### 6. Accept/Dismiss Message
```
Frontend/Orchestrator → PUT /messages/{msg_id}/status 
  → UPDATE orchestrator_messages.status 
  → Status = 'accepted' or 'dismissed'
```

---

**End of Quick Reference Table** 📊





