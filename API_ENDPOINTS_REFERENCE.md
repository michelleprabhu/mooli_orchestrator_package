# Moolai Controller - API Endpoints Reference
**Complete Backend Endpoints with Database Interactions**

---

## 📍 Table of Contents
1. [WebSocket Endpoints](#websocket-endpoints)
2. [Controller API Endpoints (Public)](#controller-api-endpoints-public)
3. [Internal API Endpoints (Administrative)](#internal-api-endpoints-administrative)
4. [Database Tables Overview](#database-tables-overview)
5. [Data Flow Diagrams](#data-flow-diagrams)

---

## 🔌 WebSocket Endpoints

### **WS /ws**
**Purpose:** Real-time bidirectional communication between controller and orchestrators

**Protocol:** WebSocket (HTTP Upgrade)

**Message Types:**

#### 1. Handshake (Orchestrator → Controller)
```json
{
  "type": "handshake",
  "service": "orchestrator",
  "data": {
    "orchestrator_id": "org-002",
    "metadata": {
      "version": "1.0.0",
      "hostname": "MacBookPro.lan",
      "ip": "192.168.1.99",
      "ssl_enabled": false,
      "name": "Michelle Organisation",
      "location": "localhost",
      "features": {}
    }
  },
  "timestamp": "2025-10-28T18:56:34.050Z"
}
```

**Controller Actions:**
- Validates handshake
- Registers orchestrator in memory (`controller_state.py`)
- Updates database (both tables)
- Sends `handshake_ack` response
- Sends initial `provision_config`

**Database Updates:**
```sql
-- Insert/Update in organizations table
INSERT INTO organizations (organization_id, name, location, settings, is_active, created_at, updated_at)
VALUES ($orchestrator_id, $name, $location, $settings, false, NOW(), NOW())
ON CONFLICT (organization_id) DO UPDATE SET 
  name = EXCLUDED.name,
  location = EXCLUDED.location,
  settings = EXCLUDED.settings,
  updated_at = NOW();

-- Insert/Update in orchestrator_instances table
INSERT INTO orchestrator_instances (
  orchestrator_id, organization_id, organization_name, location,
  status, health_status, metadata, features, is_independent,
  privacy_mode, monitoring_enabled, created_at, updated_at
)
VALUES (
  $orchestrator_id, $orchestrator_id, $name, $location,
  'active', 'healthy', $metadata, $features, false,
  false, true, NOW(), NOW()
)
ON CONFLICT (orchestrator_id) DO UPDATE SET
  organization_name = EXCLUDED.organization_name,
  location = EXCLUDED.location,
  status = 'active',
  health_status = 'healthy',
  metadata = EXCLUDED.metadata,
  features = EXCLUDED.features,
  updated_at = NOW();
```

**Logs:**
```
[C-OCS] WebSocket connection accepted
[C-OCS] DB: Registered org-002 in both tables
[C-OCS] Orchestrator org-002 connected
[C-OCS] handshake_ack sent to org-002
[C-OCS] Initial provisioning sent to org-002
```

---

#### 2. Heartbeat / Keepalive (Orchestrator → Controller)
```json
{
  "type": "i_am_alive",
  "timestamp": "2025-10-28T19:00:24.185Z"
}
```

**Controller Actions:**
- Checks `is_independent` flag in database
- **If NOT independent:**
  - Updates `last_seen` timestamp
  - Sets `status = 'active'`
  - Updates `health_status = 'healthy'`
  - Adds activity to buffer
- **If independent:**
  - Logs "Ignoring heartbeat"
  - No database update

**Database Updates (if NOT independent):**
```sql
UPDATE orchestrator_instances 
SET 
  last_seen = NOW(),
  status = 'active',
  health_status = 'healthy',
  updated_at = NOW()
WHERE orchestrator_id = $orchestrator_id;
```

**Logs:**
```
-- Normal mode:
[C-OCS] Processing heartbeat from orchestrator org-002

-- Independent mode:
[C-OCS] Ignoring heartbeat from independent orchestrator org-002
```

---

#### 3. Configuration Provisioning (Controller → Orchestrator)
```json
{
  "type": "provision_config",
  "data": {
    "features": {
      "cache": {"enabled": true},
      "firewall": {"enabled": false}
    },
    "settings": {},
    "policies": {}
  },
  "timestamp": "2025-10-28T18:56:34.266Z"
}
```

**Triggered By:**
- Initial connection (after handshake)
- Manual push via `/api/v1/internal/orchestrators/{id}/send` endpoint
- Feature toggle changes

**Database Reads:**
```sql
SELECT features, settings FROM organizations WHERE organization_id = $orchestrator_id;
```

**No Database Writes** (configuration stored in memory and sent to orchestrator)

**Logs:**
```
[C-OCS] Initial provisioning sent to org-002
```

---

## 🌐 Controller API Endpoints (Public)

**Base URL:** `/api/v1/controller`

**Authentication:** Optional (dev mode with `DEV_BEARER_TOKEN`)

---

### **GET /api/v1/controller/organizations**
**Purpose:** List all organizations with pagination

**Called By:** Frontend Dashboard (Organizations page)

**Request:**
```bash
GET /api/v1/controller/organizations?page=1&page_size=100
```

**Database Query:**
```sql
SELECT 
  organization_id, name, location, status, is_active, 
  is_independent, features, metadata, settings,
  last_seen, created_at, updated_at
FROM organizations
ORDER BY created_at DESC
LIMIT $page_size OFFSET ($page - 1) * $page_size;

-- Also counts total
SELECT COUNT(*) FROM organizations;
```

**Response:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "organization_id": "org-002",
        "name": "Michelle Organisation",
        "status": "inactive",
        "is_independent": false,
        "location": "localhost",
        "features": {},
        "last_seen": null,
        "created_at": "2025-10-28T18:47:04.033042"
      }
    ],
    "page": 1,
    "page_size": 100,
    "total_items": 3,
    "total_pages": 1
  },
  "message": "Organizations retrieved successfully"
}
```

**Logs:** None (read-only)

---

### **GET /api/v1/controller/organizations/{org_id}**
**Purpose:** Get details of a specific organization

**Called By:** Frontend (Organization details view)

**Database Query:**
```sql
SELECT * FROM organizations WHERE organization_id = $org_id;
```

**Response:**
```json
{
  "success": true,
  "data": {
    "organization_id": "org-002",
    "name": "Michelle Organisation",
    "location": "localhost",
    "status": "active",
    "is_independent": false,
    "features": {},
    "settings": {},
    "last_seen": "2025-10-28T19:00:24.185924",
    "created_at": "2025-10-28T18:47:04.033042"
  },
  "message": "Organization retrieved successfully"
}
```

---

### **POST /api/v1/controller/organizations**
**Purpose:** Create a new organization

**Called By:** Frontend (Add New Organization dialog)

**Request Body:**
```json
{
  "org_id": "org-005",
  "name": "New Organization",
  "location": "us-west-2",
  "features": {},
  "metadata": {}
}
```

**Database Insert:**
```sql
INSERT INTO organizations (
  organization_id, name, location, is_active, settings, created_at, updated_at
)
VALUES (
  $org_id, $name, $location, true, $settings, NOW(), NOW()
);
```

**Response:**
```json
{
  "success": true,
  "data": {
    "organization_id": "org-005",
    "name": "New Organization",
    "location": "us-west-2",
    "is_active": true
  },
  "message": "Organization org-005 created successfully"
}
```

**Logs:**
```
INFO: Organization org-005 created successfully
```

---

### **GET /api/v1/controller/orchestrators**
**Purpose:** List all orchestrator instances with pagination

**Called By:** Frontend Dashboard (Organizations page, Dashboard page)

**Request:**
```bash
GET /api/v1/controller/orchestrators?page=1&page_size=100
```

**Database Query:**
```sql
SELECT 
  orchestrator_id, organization_id, organization_name, name,
  status, health_status, is_independent, privacy_mode,
  location, features, metadata, last_seen, created_at, updated_at
FROM orchestrator_instances
ORDER BY created_at DESC
LIMIT $page_size OFFSET ($page - 1) * $page_size;

-- Also counts total
SELECT COUNT(*) FROM orchestrator_instances;
```

**Response:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "orchestrator_id": "org-002",
        "organization_id": "org-002",
        "name": "",
        "organization_name": "Default Orchestrator",
        "status": "active",
        "health_status": "healthy",
        "is_independent": false,
        "last_seen": "2025-10-28T19:00:24.185924",
        "location": "localhost",
        "features": {},
        "metadata": {}
      }
    ],
    "page": 1,
    "page_size": 100,
    "total_items": 3,
    "total_pages": 1
  },
  "message": "Orchestrators retrieved successfully"
}
```

**Logs:** None (read-only)

---

### **POST /api/v1/controller/orchestrator-instances**
**Purpose:** Create a new orchestrator instance (placeholder)

**Called By:** Frontend or external systems

**Request Body:**
```json
{
  "org_id": "org-005",
  "name": "New Orchestrator",
  "location": "us-west-2",
  "features": {},
  "metadata": {}
}
```

**Database Insert:**
```sql
INSERT INTO orchestrator_instances (
  orchestrator_id, organization_name, location, status, health_status,
  features, session_config, is_independent, privacy_mode,
  monitoring_enabled, created_at, updated_at
) VALUES (
  $org_id, $name, $location, 'inactive', 'unknown',
  $features, '{}', false, false, true, NOW(), NOW()
);
```

**Response:**
```json
{
  "success": true,
  "data": {
    "orchestrator_id": "org-005",
    "organization_name": "New Orchestrator",
    "location": "us-west-2",
    "status": "inactive",
    "is_independent": false,
    "privacy_mode": false
  },
  "message": "Orchestrator instance org-005 created successfully"
}
```

**Logs:**
```
INFO: Orchestrator instance org-005 created successfully
```

---

### **GET /api/v1/controller/orchestrators/live**
**Purpose:** Get currently connected orchestrators (WebSocket active)

**Called By:** Frontend Dashboard (every 10 seconds)

**Data Source:** In-memory state (`controller_state.py` - not database)

**Response:**
```json
{
  "success": true,
  "data": {
    "orchestrators": {
      "org-002": {
        "organization_id": "org-002",
        "name": "Default Orchestrator",
        "status": "connected",
        "last_seen": "2025-10-28T19:00:24.185Z",
        "metadata": {
          "version": "1.0.0",
          "hostname": "MacBookPro.lan",
          "features": {}
        }
      }
    },
    "total_count": 1
  },
  "message": "Live orchestrators retrieved successfully"
}
```

**Database:** Not queried (uses in-memory WebSocket connection state)

**Logs:** None (frequent polling)

---

### **DELETE /api/v1/controller/orchestrator-instances/{orchestrator_id}**
**Purpose:** Delete an orchestrator instance

**Called By:** Frontend (Delete button in Organizations page)

**Database Delete:**
```sql
-- Delete orchestrator instance
DELETE FROM orchestrator_instances WHERE orchestrator_id = $orchestrator_id;

-- Optionally delete organization if no other instances
DELETE FROM organizations 
WHERE organization_id = $orchestrator_id 
  AND NOT EXISTS (
    SELECT 1 FROM orchestrator_instances WHERE organization_id = $orchestrator_id
  );
```

**Response:**
```json
{
  "success": true,
  "message": "Orchestrator instance org-002 deleted successfully"
}
```

**Logs:**
```
INFO: Orchestrator instance org-002 deleted
```

---

## 🔐 Internal API Endpoints (Administrative)

**Base URL:** `/api/v1/internal`

**Authentication:** Required (`Authorization: Bearer fake-dev-token`)

---

### **POST /api/v1/internal/orchestrators/register**
**Purpose:** Register a new orchestrator (creates entries in both tables)

**Called By:** 
- Frontend (Add New Organization dialog)
- External orchestrator registration scripts
- Manual API calls

**Request Body:**
```json
{
  "orchestrator_id": "org-005",
  "organization_id": "org-005",
  "name": "New Organization",
  "location": "us-west-2",
  "internal_url": "http://org-005:8000",
  "database_url": "postgresql://...",
  "redis_url": "redis://...",
  "container_id": "abc123",
  "image_name": "moolai/orchestrator:latest",
  "environment_variables": {}
}
```

**Database Inserts:**
```sql
-- 1. Create orchestrator instance
INSERT INTO orchestrator_instances (
  orchestrator_id, organization_id, organization_name, location,
  internal_url, database_url, redis_url, container_id, image_name,
  environment_variables, status, health_status, is_independent,
  privacy_mode, monitoring_enabled, features, session_config,
  created_at, updated_at
)
VALUES (
  $orchestrator_id, $organization_id, $name, $location,
  $internal_url, $database_url, $redis_url, $container_id, $image_name,
  $environment_variables, 'inactive', 'unknown', false,
  false, true, $features, '{}', NOW(), NOW()
)
ON CONFLICT (orchestrator_id) DO UPDATE SET
  organization_name = EXCLUDED.organization_name,
  location = EXCLUDED.location,
  internal_url = EXCLUDED.internal_url,
  updated_at = NOW();

-- 2. Create/Update organization
INSERT INTO organizations (
  organization_id, name, location, is_active, settings, created_at, updated_at
)
VALUES (
  $org_id, $name, $location, false, $settings, NOW(), NOW()
)
ON CONFLICT (organization_id) DO UPDATE SET
  name = EXCLUDED.name,
  location = EXCLUDED.location,
  settings = EXCLUDED.settings,
  updated_at = NOW();
```

**Response:**
```json
{
  "success": true,
  "message": "Orchestrator instance registered (inactive until connection)",
  "orchestrator_id": "org-005",
  "organization_id": "org-005"
}
```

**Logs:**
```
INFO: DB registration successful for org-005
```

---

### **PUT /api/v1/internal/orchestrators/{orchestrator_id}/independence**
**Purpose:** Toggle independence mode for an orchestrator

**Called By:** Frontend (Independence Mode toggle switch)

**Request Body:**
```json
{
  "is_independent": true,
  "privacy_mode": false
}
```

**Database Update:**
```sql
UPDATE orchestrator_instances
SET 
  is_independent = $is_independent,
  privacy_mode = $privacy_mode,
  updated_at = NOW()
WHERE orchestrator_id = $orchestrator_id;

-- Also update organizations table
UPDATE organizations
SET 
  is_independent = $is_independent,
  updated_at = NOW()
WHERE organization_id = $orchestrator_id;
```

**Response:**
```json
{
  "success": true,
  "message": "Independence mode updated successfully",
  "orchestrator_id": "org-002",
  "is_independent": true,
  "privacy_mode": false
}
```

**Side Effects:**
- Attempts to write to `.env` file (non-critical if fails)
- Attempts to write to `orchestrator_independence.json` (non-critical if fails)
- Future heartbeats will be ignored if `is_independent = true`

**Logs:**
```
INFO: Independence mode enabled for org-002
INFO: Independence setting written to environment files for org-002: True
```

---

### **GET /api/v1/internal/orchestrators/{orchestrator_id}/independence**
**Purpose:** Get current independence status of an orchestrator

**Called By:** Frontend (to display toggle state)

**Database Query:**
```sql
SELECT is_independent, privacy_mode, updated_at
FROM orchestrator_instances
WHERE orchestrator_id = $orchestrator_id;
```

**Response:**
```json
{
  "success": true,
  "is_independent": true,
  "privacy_mode": false,
  "orchestrator_id": "org-002"
}
```

**Logs:** None (read-only)

---

### **POST /api/v1/internal/orchestrators/{orchestrator_id}/messages**
**Purpose:** Create a new message (recommendation or monitoring alert)

**Called By:** 
- External monitoring systems
- Manual API calls (curl)
- Orchestrator internal logic

**Request Body:**
```json
{
  "message_type": "recommendation",
  "content": "Consider enabling caching to improve performance by 40%",
  "metadata": {
    "severity": "medium",
    "category": "performance",
    "estimated_impact": "40% faster response time"
  }
}
```

**Database Insert:**
```sql
INSERT INTO orchestrator_messages (
  id, orchestrator_id, message_type, content, message_metadata,
  status, created_at, updated_at
)
VALUES (
  $message_id, $orchestrator_id, $message_type, $content, $metadata,
  'pending', NOW(), NOW()
);
```

**Response:**
```json
{
  "success": true,
  "message": "Message created successfully",
  "message_id": "msg_org-002_1730140824",
  "orchestrator_id": "org-002",
  "message_type": "recommendation",
  "status": "pending"
}
```

**Logs:**
```
INFO: Message msg_org-002_1730140824 created for org-002 (type: recommendation)
```

---

### **GET /api/v1/internal/orchestrators/{orchestrator_id}/messages**
**Purpose:** Retrieve messages for a specific orchestrator

**Called By:** 
- Frontend (Messages view)
- Orchestrator polling for new messages

**Query Parameters:**
- `message_type` (optional): `recommendation` or `monitoring`
- `status` (optional): `pending`, `accepted`, `dismissed`

**Request:**
```bash
GET /api/v1/internal/orchestrators/org-002/messages?message_type=recommendation&status=pending
```

**Database Query:**
```sql
SELECT 
  id, orchestrator_id, message_type, content, message_metadata,
  status, created_at, updated_at
FROM orchestrator_messages
WHERE orchestrator_id = $orchestrator_id
  AND ($message_type IS NULL OR message_type = $message_type)
  AND ($status IS NULL OR status = $status)
ORDER BY created_at DESC;
```

**Response:**
```json
{
  "success": true,
  "message": "Messages retrieved successfully",
  "orchestrator_id": "org-002",
  "messages": [
    {
      "id": "msg_org-002_1730140824",
      "orchestrator_id": "org-002",
      "message_type": "recommendation",
      "content": "Consider enabling caching to improve performance by 40%",
      "metadata": {
        "severity": "medium",
        "category": "performance"
      },
      "status": "pending",
      "created_at": "2025-10-28T19:20:24.000Z",
      "updated_at": "2025-10-28T19:20:24.000Z"
    }
  ],
  "total_count": 1
}
```

**Logs:** None (read-only)

---

### **PUT /api/v1/internal/messages/{message_id}/status**
**Purpose:** Update message status (accept or dismiss)

**Called By:** 
- Frontend (Accept/Dismiss buttons)
- Orchestrator after processing message

**Request Body:**
```json
{
  "status": "accepted"
}
```

**Database Update:**
```sql
UPDATE orchestrator_messages
SET 
  status = $status,
  updated_at = NOW()
WHERE id = $message_id;
```

**Response:**
```json
{
  "success": true,
  "message": "Message accepted successfully",
  "message_id": "msg_org-002_1730140824",
  "status": "accepted",
  "orchestrator_id": "org-002"
}
```

**Logs:**
```
INFO: Message msg_org-002_1730140824 status updated to 'accepted'
```

---

### **GET /api/v1/internal/messages**
**Purpose:** Get all messages across all orchestrators

**Called By:** Frontend (Admin dashboard, Messages view)

**Query Parameters:**
- `message_type` (optional): `recommendation` or `monitoring`
- `status` (optional): `pending`, `accepted`, `dismissed`
- `limit` (default: 100): Maximum number of messages

**Database Query:**
```sql
SELECT 
  id, orchestrator_id, message_type, content, message_metadata,
  status, created_at, updated_at
FROM orchestrator_messages
WHERE ($message_type IS NULL OR message_type = $message_type)
  AND ($status IS NULL OR status = $status)
ORDER BY created_at DESC
LIMIT $limit;
```

**Response:**
```json
{
  "success": true,
  "message": "All messages retrieved successfully",
  "messages": [
    {
      "id": "msg_org-002_1730140824",
      "orchestrator_id": "org-002",
      "message_type": "recommendation",
      "content": "Consider enabling caching",
      "status": "pending",
      "created_at": "2025-10-28T19:20:24.000Z"
    },
    {
      "id": "msg_org-003_1730140900",
      "orchestrator_id": "org-003",
      "message_type": "monitoring",
      "content": "High memory usage detected",
      "status": "pending",
      "created_at": "2025-10-28T19:21:40.000Z"
    }
  ],
  "total_count": 2
}
```

**Logs:** None (read-only)

---

### **DELETE /api/v1/internal/orchestrators/{orchestrator_id}/deregister**
**Purpose:** Deregister and delete an orchestrator

**Called By:** Frontend (Delete organization)

**Database Deletes:**
```sql
-- Delete messages first (foreign key constraint)
DELETE FROM orchestrator_messages WHERE orchestrator_id = $orchestrator_id;

-- Delete orchestrator instance
DELETE FROM orchestrator_instances WHERE orchestrator_id = $orchestrator_id;

-- Delete organization if no other instances
DELETE FROM organizations 
WHERE organization_id = $orchestrator_id
  AND NOT EXISTS (
    SELECT 1 FROM orchestrator_instances WHERE organization_id = $orchestrator_id
  );
```

**In-Memory Cleanup:**
- Closes WebSocket connection if active
- Removes from `controller_state` tracking
- Clears activity buffers

**Response:**
```json
{
  "success": true,
  "message": "Orchestrator org-002 deregistered successfully"
}
```

**Logs:**
```
INFO: Orchestrator org-002 disconnected
INFO: Cleaned up connection for org-002
INFO: Orchestrator org-002 deregistered from database
```

---

### **POST /api/v1/internal/orchestrators/{orchestrator_id}/send**
**Purpose:** Send a message to orchestrator via WebSocket

**Called By:** 
- Internal provisioning logic
- Manual admin commands

**Request Body:**
```json
{
  "type": "provision_config",
  "data": {
    "features": {
      "cache": {"enabled": true}
    }
  }
}
```

**Actions:**
- Looks up active WebSocket connection in memory
- Sends message directly through WebSocket
- No database interaction (ephemeral message)

**Response:**
```json
{
  "success": true,
  "message": "Message sent to org-002 successfully"
}
```

**Logs:**
```
INFO: Sent message to orchestrator org-002 (type: provision_config)
```

---

### **GET /api/v1/internal/logs**
**Purpose:** Retrieve controller application logs

**Called By:** Frontend (Logs page)

**Query Parameters:**
- `q` (optional): Search substring
- `level` (optional): `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- `limit` (default: 200): Maximum log entries

**Data Source:** In-memory log buffer (not database)

**Response:**
```json
{
  "success": true,
  "logs": [
    {
      "timestamp": "2025-10-28T19:20:24.000Z",
      "level": "INFO",
      "message": "[C-OCS] Processing heartbeat from orchestrator org-002"
    },
    {
      "timestamp": "2025-10-28T19:20:54.000Z",
      "level": "INFO",
      "message": "[C-OCS] Processing heartbeat from orchestrator org-002"
    }
  ],
  "total_count": 2
}
```

**Database:** Not used (logs from in-memory buffer)

**Logs:** None (self-referential)

---

## 💾 Database Tables Overview

### **Table: organizations**
**Purpose:** Store organization/tenant metadata

**Columns:**
- `organization_id` (PK): Unique identifier
- `name`: Human-readable name
- `location`: Geographic location or deployment zone
- `metadata`: JSON blob for custom fields
- `features`: JSON blob for enabled features
- `last_seen`: Last activity timestamp (updated by heartbeats)
- `status`: `active` | `inactive`
- `created_at`: Creation timestamp
- `updated_at`: Last modification timestamp
- `is_active`: Boolean flag
- `settings`: JSON blob for configuration
- `is_independent`: Boolean flag for independence mode

**Updated By:**
- WebSocket handshake: Creates/updates record
- Heartbeat messages: Updates `last_seen` (if NOT independent)
- POST `/api/v1/controller/organizations`: Creates record
- PUT `/api/v1/internal/orchestrators/{id}/independence`: Updates `is_independent`

---

### **Table: orchestrator_instances**
**Purpose:** Store individual orchestrator instance data

**Columns:**
- `orchestrator_id` (PK): Unique identifier
- `organization_id` (FK): Links to organizations table
- `name`: Instance-specific name
- `organization_name`: Cached organization name
- `status`: `active` | `inactive`
- `health_status`: `healthy` | `degraded` | `unhealthy` | `unknown`
- `is_independent`: Boolean flag for independence mode
- `last_seen`: Last heartbeat timestamp
- `metadata`: JSON blob with runtime metadata
- `features`: JSON blob for enabled features
- `session_config`: JSON blob for session settings
- `privacy_mode`: Boolean flag
- `monitoring_enabled`: Boolean flag
- `location`: Geographic location
- `internal_url`: Internal service URL
- `database_url`: PostgreSQL connection string
- `redis_url`: Redis connection string
- `container_id`: Docker container ID
- `image_name`: Docker image name
- `environment_variables`: JSON blob of env vars
- `phoenix_endpoint`: Monitoring endpoint URL
- `admin_email`: Contact email
- `support_email`: Support email
- `website`: Organization website
- `last_activity`: Last non-heartbeat activity timestamp
- `created_at`: Creation timestamp
- `updated_at`: Last modification timestamp

**Updated By:**
- WebSocket handshake: Creates/updates record, sets `status = 'active'`
- Heartbeat messages: Updates `last_seen`, `status`, `health_status` (if NOT independent)
- POST `/api/v1/internal/orchestrators/register`: Creates record
- PUT `/api/v1/internal/orchestrators/{id}/independence`: Updates `is_independent`
- WebSocket disconnect: Sets `status = 'inactive'`

---

### **Table: orchestrator_messages**
**Purpose:** Store messages between controller and orchestrators

**Columns:**
- `id` (PK): Unique message identifier (format: `msg_{orchestrator_id}_{timestamp}`)
- `orchestrator_id` (FK): Target orchestrator
- `message_type`: `recommendation` | `monitoring`
- `content`: Message text
- `message_metadata`: JSON blob with additional data
- `status`: `pending` | `accepted` | `dismissed`
- `created_at`: Creation timestamp
- `updated_at`: Last modification timestamp

**Updated By:**
- POST `/api/v1/internal/orchestrators/{id}/messages`: Creates record
- PUT `/api/v1/internal/messages/{id}/status`: Updates `status`
- DELETE `/api/v1/internal/orchestrators/{id}/deregister`: Deletes all messages for orchestrator

---

## 📊 Data Flow Diagrams

### Flow 1: Orchestrator Startup & Connection
```
┌─────────────┐                    ┌──────────────┐                    ┌──────────────┐
│ Orchestrator│                    │  Controller  │                    │  PostgreSQL  │
│   Client    │                    │   (FastAPI)  │                    │   Database   │
└──────┬──────┘                    └──────┬───────┘                    └──────┬───────┘
       │                                  │                                   │
       │ 1. WebSocket Connect (HTTP)      │                                   │
       │─────────────────────────────────>│                                   │
       │                                  │                                   │
       │ 2. Send Handshake                │                                   │
       │ {type: "handshake", data: {...}} │                                   │
       │─────────────────────────────────>│                                   │
       │                                  │                                   │
       │                                  │ 3. Validate Handshake             │
       │                                  │                                   │
       │                                  │ 4. Register in Memory             │
       │                                  │ (controller_state.py)             │
       │                                  │                                   │
       │                                  │ 5. INSERT/UPDATE organizations    │
       │                                  │──────────────────────────────────>│
       │                                  │                                   │
       │                                  │ 6. INSERT/UPDATE orchestrator_instances
       │                                  │──────────────────────────────────>│
       │                                  │                                   │
       │ 7. Send handshake_ack            │                                   │
       │<─────────────────────────────────│                                   │
       │                                  │                                   │
       │ 8. Send provision_config         │                                   │
       │<─────────────────────────────────│                                   │
       │                                  │                                   │
       │ 9. Start Heartbeat Loop          │                                   │
       │ (every 30 seconds)               │                                   │
       │                                  │                                   │
```

---

### Flow 2: Heartbeat Processing (Normal Mode)
```
┌─────────────┐                    ┌──────────────┐                    ┌──────────────┐
│ Orchestrator│                    │  Controller  │                    │  PostgreSQL  │
└──────┬──────┘                    └──────┬───────┘                    └──────┬───────┘
       │                                  │                                   │
       │ 1. Send i_am_alive               │                                   │
       │ {type: "i_am_alive", ...}        │                                   │
       │─────────────────────────────────>│                                   │
       │                                  │                                   │
       │                                  │ 2. Check is_independent flag      │
       │                                  │──────────────────────────────────>│
       │                                  │<──────────────────────────────────│
       │                                  │ (is_independent = false)          │
       │                                  │                                   │
       │                                  │ 3. Log: "Processing heartbeat"    │
       │                                  │                                   │
       │                                  │ 4. Update in-memory state         │
       │                                  │ (mark_keepalive)                  │
       │                                  │                                   │
       │                                  │ 5. UPDATE orchestrator_instances  │
       │                                  │    SET last_seen = NOW(),         │
       │                                  │        status = 'active',         │
       │                                  │        health_status = 'healthy'  │
       │                                  │──────────────────────────────────>│
       │                                  │                                   │
       │                                  │ 6. Add to activity buffer         │
       │                                  │ (buffer_manager.py)               │
       │                                  │                                   │
```

---

### Flow 3: Heartbeat Processing (Independence Mode)
```
┌─────────────┐                    ┌──────────────┐                    ┌──────────────┐
│ Orchestrator│                    │  Controller  │                    │  PostgreSQL  │
└──────┬──────┘                    └──────┬───────┘                    └──────┬───────┘
       │                                  │                                   │
       │ 1. Send i_am_alive               │                                   │
       │ {type: "i_am_alive", ...}        │                                   │
       │─────────────────────────────────>│                                   │
       │                                  │                                   │
       │                                  │ 2. Check is_independent flag      │
       │                                  │──────────────────────────────────>│
       │                                  │<──────────────────────────────────│
       │                                  │ (is_independent = true)           │
       │                                  │                                   │
       │                                  │ 3. Log: "Ignoring heartbeat from  │
       │                                  │         independent orchestrator" │
       │                                  │                                   │
       │                                  │ 4. NO DATABASE UPDATE             │
       │                                  │                                   │
       │                                  │ 5. Continue listening             │
       │                                  │                                   │
```

---

### Flow 4: Toggle Independence Mode
```
┌──────────┐           ┌──────────────┐           ┌──────────────┐           ┌──────────────┐
│ Frontend │           │  Controller  │           │  PostgreSQL  │           │ Orchestrator │
└────┬─────┘           └──────┬───────┘           └──────┬───────┘           └──────┬───────┘
     │                        │                          │                          │
     │ 1. User clicks toggle  │                          │                          │
     │ (Independence ON)      │                          │                          │
     │                        │                          │                          │
     │ 2. PUT /api/v1/internal/orchestrators/org-002/independence               │
     │ {is_independent: true} │                          │                          │
     │───────────────────────>│                          │                          │
     │                        │                          │                          │
     │                        │ 3. UPDATE orchestrator_instances                    │
     │                        │    SET is_independent = true                        │
     │                        │─────────────────────────>│                          │
     │                        │                          │                          │
     │                        │ 4. UPDATE organizations  │                          │
     │                        │    SET is_independent = true                        │
     │                        │─────────────────────────>│                          │
     │                        │                          │                          │
     │                        │ 5. Try write to .env     │                          │
     │                        │ (non-critical if fails)  │                          │
     │                        │                          │                          │
     │ 6. Response: success   │                          │                          │
     │<───────────────────────│                          │                          │
     │                        │                          │                          │
     │ 7. UI updates badge    │                          │                          │
     │ (green → red)          │                          │                          │
     │                        │                          │                          │
     │                        │ 8. Next heartbeat arrives│                          │
     │                        │<─────────────────────────────────────────────────────│
     │                        │                          │                          │
     │                        │ 9. Check is_independent  │                          │
     │                        │─────────────────────────>│                          │
     │                        │<─────────────────────────│                          │
     │                        │ (is_independent = true)  │                          │
     │                        │                          │                          │
     │                        │ 10. Log: "Ignoring heartbeat"                       │
     │                        │                          │                          │
     │                        │ 11. NO DB UPDATE         │                          │
     │                        │                          │                          │
```

---

### Flow 5: Send & Retrieve Messages
```
┌─────────────┐           ┌──────────────┐           ┌──────────────┐           ┌──────────────┐
│   External  │           │  Controller  │           │  PostgreSQL  │           │   Frontend   │
│   System    │           │   (FastAPI)  │           │   Database   │           │   Dashboard  │
└──────┬──────┘           └──────┬───────┘           └──────┬───────┘           └──────┬───────┘
       │                         │                          │                          │
       │ 1. POST /api/v1/internal/orchestrators/org-002/messages               │
       │ {message_type: "recommendation", content: "..."}                        │
       │────────────────────────>│                          │                          │
       │                         │                          │                          │
       │                         │ 2. Generate message_id   │                          │
       │                         │ (msg_org-002_timestamp)  │                          │
       │                         │                          │                          │
       │                         │ 3. INSERT orchestrator_messages                     │
       │                         │─────────────────────────>│                          │
       │                         │                          │                          │
       │ 4. Response: success    │                          │                          │
       │<────────────────────────│                          │                          │
       │                         │                          │                          │
       │                         │                          │ 5. Frontend polls for messages
       │                         │                          │<─────────────────────────│
       │                         │                          │                          │
       │                         │ 6. SELECT * FROM orchestrator_messages              │
       │                         │    WHERE orchestrator_id = 'org-002'                │
       │                         │<─────────────────────────│                          │
       │                         │─────────────────────────>│                          │
       │                         │                          │                          │
       │                         │ 7. Return messages       │                          │
       │                         │─────────────────────────────────────────────────────>│
       │                         │                          │                          │
       │                         │                          │ 8. User clicks "Accept"  │
       │                         │                          │<─────────────────────────│
       │                         │                          │                          │
       │                         │ 9. PUT /api/v1/internal/messages/{id}/status        │
       │                         │    {status: "accepted"}  │                          │
       │                         │<─────────────────────────────────────────────────────│
       │                         │                          │                          │
       │                         │ 10. UPDATE orchestrator_messages                    │
       │                         │     SET status = 'accepted'                         │
       │                         │─────────────────────────>│                          │
       │                         │                          │                          │
       │                         │ 11. Response: success    │                          │
       │                         │─────────────────────────────────────────────────────>│
       │                         │                          │                          │
```

---

## 🗂️ In-Memory State Management

### **Module: controller_state.py**
**Purpose:** Track active WebSocket connections and orchestrator state

**Functions:**

#### `mark_handshake(orchestrator_id, websocket, metadata)`
- Stores WebSocket connection object
- Records handshake timestamp
- Stores orchestrator metadata
- Called by: WebSocket `/ws` handler during handshake

#### `mark_keepalive(orchestrator_id)`
- Updates last keepalive timestamp
- Called by: WebSocket `/ws` handler on `i_am_alive` message (if NOT independent)

#### `remove_orchestrator(orchestrator_id)`
- Removes WebSocket connection
- Clears handshake/keepalive timestamps
- Called by: WebSocket `/ws` handler on disconnect

#### `list_orchestrators(public=True)`
- Returns dictionary of active orchestrators
- If `public=True`: Returns sanitized data for API
- If `public=False`: Returns full internal state
- Called by: GET `/api/v1/controller/orchestrators/live`

**Data Structure:**
```python
{
  "org-002": {
    "websocket": <WebSocket object>,
    "handshake_time": "2025-10-28T18:56:34.050Z",
    "last_keepalive": "2025-10-28T19:00:24.185Z",
    "metadata": {
      "version": "1.0.0",
      "hostname": "MacBookPro.lan",
      "features": {}
    }
  }
}
```

---

### **Module: buffer_manager.py**
**Purpose:** Maintain activity logs for debugging and monitoring

**Class: ControllerBufferManager**

**Methods:**

#### `add_activity(activity_type, data)`
- Logs controller events
- Stores timestamp, type, and data
- Activity types:
  - `"handshake"`: Orchestrator connected
  - `"keepalive"`: Heartbeat received
  - `"disconnect"`: Orchestrator disconnected
  - `"provision"`: Configuration sent
  - `"message_sent"`: Message dispatched

**Data Structure:**
```python
[
  {
    "timestamp": "2025-10-28T18:56:34.050Z",
    "type": "handshake",
    "data": {"orchestrator_id": "org-002"}
  },
  {
    "timestamp": "2025-10-28T19:00:24.185Z",
    "type": "keepalive",
    "data": {"orchestrator_id": "org-002"}
  }
]
```

**Buffer Size:** 1000 entries (circular buffer, oldest entries dropped)

**Called By:**
- WebSocket handler (handshake, keepalive, disconnect)
- Configuration provisioning logic
- Message dispatch functions

---

## 🔍 Summary: What Logs Where

### **WebSocket Connection Logs:**
```
[C-OCS] WebSocket connection accepted
[C-OCS] DB: Registered {orchestrator_id} in both tables
[C-OCS] Orchestrator {orchestrator_id} connected
[C-OCS] handshake_ack sent to {orchestrator_id}
[C-OCS] Initial provisioning sent to {orchestrator_id}
```

**Database:** 
- `organizations` (INSERT/UPDATE)
- `orchestrator_instances` (INSERT/UPDATE)

**In-Memory:**
- `controller_state`: Add WebSocket connection
- `buffer_manager`: Log handshake activity

---

### **Heartbeat Logs (Normal Mode):**
```
[C-OCS] Processing heartbeat from orchestrator {orchestrator_id}
```

**Database:**
- `orchestrator_instances`: UPDATE `last_seen`, `status`, `health_status`

**In-Memory:**
- `controller_state`: Update `last_keepalive`
- `buffer_manager`: Log keepalive activity

---

### **Heartbeat Logs (Independence Mode):**
```
[C-OCS] Ignoring heartbeat from independent orchestrator {orchestrator_id}
```

**Database:** None (no updates)

**In-Memory:** None (intentionally ignored)

---

### **Independence Toggle Logs:**
```
INFO: Independence mode enabled for {orchestrator_id}
INFO: Independence setting written to environment files for {orchestrator_id}: {value}
```

**Database:**
- `orchestrator_instances`: UPDATE `is_independent`
- `organizations`: UPDATE `is_independent`

**Files (non-critical):**
- `/app/controller/app/.env`
- `/app/controller/app/db/orchestrator_independence.json`

---

### **Message Creation Logs:**
```
INFO: Message {message_id} created for {orchestrator_id} (type: {message_type})
```

**Database:**
- `orchestrator_messages`: INSERT new message

---

### **Message Status Update Logs:**
```
INFO: Message {message_id} status updated to '{status}'
```

**Database:**
- `orchestrator_messages`: UPDATE `status`

---

### **Organization/Orchestrator Creation Logs:**
```
INFO: Organization {org_id} created successfully
INFO: Orchestrator instance {orchestrator_id} created successfully
INFO: DB registration successful for {orchestrator_id}
```

**Database:**
- `organizations`: INSERT
- `orchestrator_instances`: INSERT

---

### **Deregistration Logs:**
```
INFO: Orchestrator {orchestrator_id} disconnected
INFO: Cleaned up connection for {orchestrator_id}
INFO: Orchestrator {orchestrator_id} deregistered from database
```

**Database:**
- `orchestrator_messages`: DELETE all for orchestrator
- `orchestrator_instances`: DELETE
- `organizations`: DELETE (if no other instances)

**In-Memory:**
- `controller_state`: Remove WebSocket connection
- `buffer_manager`: Log disconnect activity

---

## 🎯 Quick Reference: Endpoint → Database Mapping

| Endpoint | Database Tables | Operation |
|----------|----------------|-----------|
| **WebSocket /ws (handshake)** | `organizations`, `orchestrator_instances` | INSERT/UPDATE both |
| **WebSocket /ws (i_am_alive)** | `orchestrator_instances` | UPDATE (if NOT independent) |
| **GET /organizations** | `organizations` | SELECT |
| **POST /organizations** | `organizations` | INSERT |
| **GET /orchestrators** | `orchestrator_instances` | SELECT |
| **POST /orchestrator-instances** | `orchestrator_instances` | INSERT |
| **GET /orchestrators/live** | In-memory only | No DB query |
| **DELETE /orchestrator-instances/{id}** | `orchestrator_instances`, `organizations` | DELETE |
| **POST /internal/orchestrators/register** | `organizations`, `orchestrator_instances` | INSERT both |
| **PUT /internal/orchestrators/{id}/independence** | `orchestrator_instances`, `organizations` | UPDATE both |
| **GET /internal/orchestrators/{id}/independence** | `orchestrator_instances` | SELECT |
| **POST /internal/orchestrators/{id}/messages** | `orchestrator_messages` | INSERT |
| **GET /internal/orchestrators/{id}/messages** | `orchestrator_messages` | SELECT |
| **PUT /internal/messages/{id}/status** | `orchestrator_messages` | UPDATE |
| **GET /internal/messages** | `orchestrator_messages` | SELECT |
| **DELETE /internal/orchestrators/{id}/deregister** | All 3 tables | DELETE |
| **GET /internal/logs** | In-memory buffer only | No DB query |

---

**End of API Endpoints Reference** 📚





