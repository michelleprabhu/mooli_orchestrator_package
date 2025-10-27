# High-Level Design (HLD) - Moolai Controller Service

## 📋 Table of Contents
1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Core Components](#core-components)
4. [Database Schema](#database-schema)
5. [API Endpoints](#api-endpoints)
6. [WebSocket Protocol](#websocket-protocol)
7. [Independence Mode](#independence-mode)
8. [File Structure & Responsibilities](#file-structure--responsibilities)
9. [Data Flow](#data-flow)
10. [Deployment](#deployment)

---

## Overview

The **Moolai Controller Service** is a central management platform for orchestrating and monitoring multiple Moolai orchestrator instances. It provides real-time status tracking, independence mode management, message routing, and administrative capabilities through a unified web interface.

### Key Capabilities
- **Orchestrator Monitoring**: Real-time heartbeat tracking via WebSocket
- **Independence Mode**: Allow orchestrators to operate autonomously
- **Message Routing**: Forward recommendations and monitoring messages
- **Multi-tenant Support**: Manage multiple organizations and orchestrator instances
- **Authentication**: Superadmin login for secure access
- **Real-time Dashboard**: Live status updates and analytics

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Azure VM (B2 Instance)                    │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │   Frontend      │  │   Controller   │  │  PostgreSQL  │ │
│  │   (Nginx)       │  │   (FastAPI)    │  │  Database    │ │
│  │                 │  │                 │  │              │ │
│  │  Port 80        │  │  Port 8765     │  │  Port 5432   │ │
│  │  - React/Vite   │  │  - REST API    │  │  - All Tables│ │
│  │  - UI Components│  │  - WebSocket   │  │  - Persistence│
│  │  - Reverse Proxy│  │  - Business    │  │              │ │
│  │                 │  │    Logic      │  │              │ │
│  └────────┬────────┘  └────────┬───────┘  └──────┬───────┘ │
│           │                   │                   │         │
│           └───────────────────┴───────────────────┘         │
│                   moolai-network (Docker)                 │
│                                                           │
└───────────────────────────────┬───────────────────────────┘
                                │
                                │ WebSocket (ws://4.155.149.35/ws)
                                │
                     ┌──────────▼───────────┐
                     │  Orchestrator Client │
                     │   (Local Machine)    │
                     │   - Sends heartbeats │
                     │   - Receives config  │
                     │   - Orch-001        │
                     └──────────────────────┘
```

---

## Core Components

### 1. **FastAPI Application** (`main.py`)
The central FastAPI application that orchestrates all services.

**Responsibilities:**
- Initialize database connection
- Register API routes (`/api/v1/controller`, `/api/v1/internal`)
- WebSocket endpoint (`/ws`) for orchestrator connections
- CORS configuration
- Startup/shutdown lifecycle management
- Health check endpoint

**Key Functions:**
```python
@app.on_event("startup")
async def startup() -> None:
    # Initialize database
    await init_db()
    # Start heartbeat poker (if enabled)
    # Initialize WebSocket handler
    
@app.websocket("/ws")
async def websocket_handler(websocket: WebSocket):
    # Handle orchestrator connections
    # Process heartbeats and messages
    # Check independence status
    # Update database and state
```

---

### 2. **WebSocket Handler** (`main.py` - `websocket_handler()`)
Manages real-time bi-directional communication with orchestrators.

**Responsibilities:**
- Accept WebSocket connections from orchestrators
- Process incoming messages:
  - `i_am_alive` (heartbeats)
  - `register` (initial handshake)
  - `request_status` (status queries)
- **Independence Check**: Query database for `is_independent` flag
- Update orchestrator state in memory and database
- Send acknowledgments and configuration updates
- Handle reconnection scenarios

**Message Flow:**
```
Orchestrator → Controller
  {"type": "register", "orchestrator_id": "orch-001", ...}
  
Controller → Orchestrator
  {"type": "handshake_ack", "success": true, ...}
  {"type": "provisioning", "config": {...}, ...}

Orchestrator → Controller (every 30s)
  {"type": "i_am_alive", "orchestrator_id": "orch-001"}

Controller → Database
  UPDATE orchestrator_instances 
  SET last_seen = NOW(), status = 'active'
  WHERE orchestrator_id = 'orch-001'
  
  UNLESS is_independent = TRUE → Ignore heartbeat
```

---

### 3. **Database Layer** (`db/database.py`)
Manages PostgreSQL database connections and operations.

**Responsibilities:**
- Create async database engine (SQLAlchemy)
- Build database URL from environment variables
- Session management for async operations
- Connection pooling
- Database initialization and schema creation

**Configuration:**
- **Host**: `DATABASE_HOST` (default: `postgres`)
- **Port**: `DATABASE_PORT` (default: `5432`)
- **User**: `DATABASE_USER` (default: `moolai`)
- **Database**: `DATABASE_NAME` (default: `moolai_controller`)

**Key Classes:**
- `DatabaseManager`: Singleton for managing database connections
- `AsyncSession`: Async database sessions
- `Base`: SQLAlchemy declarative base for ORM models

---

### 4. **API Routes**

#### **Controller API** (`api/v1/controller.py`)
External-facing REST API for dashboard and frontend.

**Endpoints:**
- `GET /api/v1/controller/overview` - System overview statistics
- `GET /api/v1/controller/organizations` - List organizations
- `GET /api/v1/controller/orchestrators` - List orchestrators
- `GET /api/v1/controller/health` - Health check
- `GET /api/v1/controller/costs` - Cost analytics

**Authentication:** Bearer token (`DEV_BEARER_TOKEN`)

#### **Internal API** (`api/v1/internal.py`)
Internal API for orchestrator management and configuration.

**Endpoints:**
- `POST /api/v1/internal/auth/login` - Superadmin login
- `PUT /api/v1/internal/orchestrators/{id}/independence` - Toggle independence
- `POST /api/v1/internal/orchestrators/{id}/messages` - Send messages
- `GET /api/v1/internal/messages` - Get orchestrator messages
- `PUT /api/v1/internal/messages/{id}/status` - Update message status

---

### 5. **State Management** (`utils/controller_state.py`)
In-memory orchestrator state tracking.

**Responsibilities:**
- Track active WebSocket connections
- Store last seen timestamps
- Store metadata per orchestrator
- Thread-safe operations (using RLock)

**Functions:**
- `mark_handshake(orch_id, ws, metadata)` - Record connection
- `mark_keepalive(orch_id, metadata)` - Update heartbeat
- `remove_orchestrator(orch_id)` - Clean up on disconnect
- `list_orchestrators(public=True)` - Get active orchestrators

**Storage:**
```python
_connected = {
    "orch-001": {
        "ws": <WebSocket>,
        "last_seen": "2025-10-05T20:00:00Z",
        "metadata": {...}
    },
    ...
}
```

---

### 6. **Frontend** (`gui/frontend/`)
React-based dashboard UI with real-time updates.

**Components:**
- `App.tsx` - Main routing component
- `pages/dashboard/dashboard.tsx` - Overview dashboard
- `pages/dashboard/organizations-detail.tsx` - Independence toggle UI
- `pages/auth/login.tsx` - Superadmin login
- `components/dashboard/sidebar.tsx` - Navigation

**Features:**
- Real-time orchestrator status display
- Independence mode toggle
- Message display with accept/dismiss
- Configurable polling intervals

---

## Database Schema

### **organizations**
Stores organization-level information.

```sql
CREATE TABLE organizations (
    organization_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    location VARCHAR(255),
    metadata JSONB DEFAULT '{}',
    features JSONB DEFAULT '{}',
    last_seen TIMESTAMP,
    status VARCHAR(50) DEFAULT 'inactive',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    settings JSONB DEFAULT '{}',
    is_independent BOOLEAN DEFAULT FALSE  -- Key field for independence mode
);
```

### **orchestrator_instances**
Stores individual orchestrator configuration and status.

```sql
CREATE TABLE orchestrator_instances (
    orchestrator_id VARCHAR(255) PRIMARY KEY,
    organization_id VARCHAR(255),
    organization_name VARCHAR(255),
    name VARCHAR(255),
    location VARCHAR(255),
    status VARCHAR(50) DEFAULT 'inactive',
    last_seen TIMESTAMP,
    health_status VARCHAR(50) DEFAULT 'healthy',
    is_independent BOOLEAN DEFAULT FALSE,  -- Key field for independence mode
    metadata JSONB DEFAULT '{}',
    features JSONB DEFAULT '{}',
    session_config JSONB DEFAULT '{}',
    privacy_mode BOOLEAN DEFAULT FALSE,
    monitoring_enabled BOOLEAN DEFAULT TRUE,
    internal_url VARCHAR(500),
    database_url VARCHAR(500),
    redis_url VARCHAR(500),
    container_id VARCHAR(255),
    image_name VARCHAR(255),
    environment_variables JSONB DEFAULT '{}',
    phoenix_endpoint VARCHAR(500),
    admin_email VARCHAR(255),
    support_email VARCHAR(255),
    website VARCHAR(255),
    last_activity TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### **orchestrator_messages**
Stores recommendation and monitoring messages.

```sql
CREATE TABLE orchestrator_messages (
    id VARCHAR(255) PRIMARY KEY,
    orchestrator_id VARCHAR(255) NOT NULL,
    message_type VARCHAR(50) NOT NULL,  -- 'recommendation' or 'monitoring'
    content TEXT NOT NULL,
    message_metadata JSONB DEFAULT '{}',
    status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'accepted', 'dismissed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### **orchestrator_connections**
Tracks WebSocket connection state (legacy).

```sql
CREATE TABLE orchestrator_connections (
    connection_id VARCHAR(255) PRIMARY KEY,
    orchestrator_id VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,
    last_seen TIMESTAMP,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## API Endpoints

### **Controller API** (`/api/v1/controller`)

#### `GET /api/v1/controller/overview`
Returns system-wide statistics.

**Response:**
```json
{
  "success": true,
  "data": {
    "total_organizations": 2,
    "active_orchestrators": 1,
    "total_users": 0
  }
}
```

#### `GET /api/v1/controller/organizations`
List all organizations with pagination.

**Query Parameters:**
- `page_size` (default: 10)
- `page` (default: 1)

**Response:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "organization_id": "org-001",
        "name": "Default Orchestrator",
        "status": "active",
        "is_independent": false
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 10
  }
}
```

#### `GET /api/v1/controller/orchestrators`
List all orchestrators.

**Response:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "orchestrator_id": "orch-001",
        "name": "Default Orchestrator",
        "status": "active",  // Overridden to "independent" if is_independent=true
        "last_seen": "2025-10-05T20:00:00Z",
        "is_independent": false
      }
    ]
  }
}
```

#### `GET /api/v1/controller/health`
Health check endpoint.

**Response:**
```json
{
  "status": "up",
  "database": "up",
  "timestamp": "2025-10-05T20:00:00Z"
}
```

---

### **Internal API** (`/api/v1/internal`)

#### `POST /api/v1/internal/auth/login`
Superadmin login endpoint.

**Request Body:**
```json
{
  "username": "michelleprabhu",
  "password": "password123"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Login successful",
  "user": {
    "username": "michelleprabhu",
    "role": "superadmin",
    "token": "dummy-session-token-michelleprabhu"
  }
}
```

#### `PUT /api/v1/internal/orchestrators/{orchestrator_id}/independence`
Toggle independence mode for an orchestrator.

**Request Body:**
```json
{
  "is_independent": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "Independence mode updated",
  "orchestrator_id": "orch-001",
  "is_independent": true
}
```

#### `POST /api/v1/internal/orchestrators/{orchestrator_id}/messages`
Send a message to an orchestrator.

**Request Body:**
```json
{
  "message_type": "recommendation",
  "content": "We recommend enabling cache to improve performance"
}
```

**Response:**
```json
{
  "success": true,
  "message_id": "msg-123",
  "orchestrator_id": "orch-001"
}
```

#### `GET /api/v1/internal/messages`
Get all orchestrator messages.

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "msg-123",
      "orchestrator_id": "orch-001",
      "message_type": "recommendation",
      "content": "...",
      "status": "pending",
      "created_at": "2025-10-05T20:00:00Z"
    }
  ]
}
```

---

## WebSocket Protocol

### **Connection Flow**
```
1. Orchestrator → Controller
   ws://4.155.149.35/ws

2. Controller → Orchestrator
   {"type": "handshake_ack", "success": true}

3. Orchestrator → Controller (register)
   {
     "type": "register",
     "orchestrator_id": "orch-001",
     "metadata": {...}
   }

4. Controller → Orchestrator (provisioning)
   {
     "type": "provisioning",
     "config": {...}
   }

5. Orchestrator → Controller (heartbeat every 30s)
   {"type": "i_am_alive", "orchestrator_id": "orch-001"}

6. Controller → Database
   UPDATE orchestrator_instances 
   SET last_seen = NOW()
   WHERE orchestrator_id = 'orch-001'
   AND is_independent = FALSE
```

### **Message Types**

**From Orchestrator:**
- `register` - Initial handshake with metadata
- `i_am_alive` - Heartbeat signal
- `request_status` - Query current status
- `update_metadata` - Update orchestrator metadata

**From Controller:**
- `handshake_ack` - Accept connection
- `provisioning` - Initial configuration
- `config_update` - Configuration changes
- `stop_monitoring` - Request to stop heartbeats (for independence)

---

## Independence Mode

### **Concept**
Independence Mode allows an orchestrator to operate autonomously without controller supervision. When enabled:
- Controller **ignores** incoming heartbeats
- No active status updates to the database
- Messages are hidden in the UI
- Orchestrator operates independently (still sends heartbeats, controller doesn't process them)

### **How It Works**

#### **1. Toggle Independence ON**
```
User → UI → PUT /api/v1/internal/orchestrators/orch-001/independence
          → { "is_independent": true }

Backend:
  UPDATE orchestrator_instances 
  SET is_independent = TRUE 
  WHERE orchestrator_id = 'orch-001'

WebSocket Handler (on next heartbeat):
  SELECT is_independent FROM orchestrator_instances WHERE orchestrator_id = 'orch-001'
  
  if is_independent == TRUE:
    logger.info("[C-OCS] Ignoring heartbeat from independent orchestrator orch-001")
    continue  # Skip all processing
  
  # If FALSE, proceed normally:
  logger.info("[C-OCS] Processing heartbeat from orchestrator orch-001")
  UPDATE orchestrator_instances SET last_seen = NOW(), status = 'active'
```

#### **2. Toggle Independence OFF**
```
User → UI → PUT /api/v1/internal/orchestrators/orch-001/independence
          → { "is_independent": false }

Backend:
  UPDATE orchestrator_instances 
  SET is_independent = FALSE 
  WHERE orchestrator_id = 'orch-001'

WebSocket Handler (on next heartbeat):
  Independence check returns FALSE
  → Process heartbeat normally
  → Update database with last_seen
  → Status changes to "active"
```

### **Database Query**
The independence check happens **every heartbeat** (every 30 seconds):

```python
# In websocket_handler() in main.py
if mtype == "i_am_alive":
    # Check independence status from database
    async with db_manager.get_session() as db:
        independence_query = text("""
            SELECT is_independent FROM orchestrator_instances 
            WHERE orchestrator_id = :orch_id
        """)
        result = await db.execute(independence_query, {"orch_id": orch_id})
        row = result.fetchone()
        
        if row and row[0]:  # is_independent = True
            logger.info("[C-OCS] Ignoring heartbeat from independent orchestrator %s", orch_id)
            continue  # Skip heartbeat processing
```

### **Frontend Display**
The frontend reflects independence status:

```typescript
// Dashboard
if (o.is_independent) {
  <Badge variant="destructive">independent</Badge>
} else if (o.status === "active") {
  <Badge variant="default">active (heartbeat)</Badge>
} else {
  <Badge variant="secondary">inactive</Badge>
}

// Organization Details
if (isIndependent) {
  // Show "This orchestrator operates independently"
  // Hide recommendation/monitoring messages
} else {
  // Show messages with Accept/Dismiss buttons
}
```

---

## File Structure & Responsibilities

### **Backend Files**

#### **`main.py`**
- **Purpose**: FastAPI application entry point
- **Responsibilities**: 
  - App initialization
  - WebSocket handler
  - Independence check logic
  - Health check endpoint
  - Startup/shutdown lifecycle
- **Key Functions**: `websocket_handler()`, `startup()`, `shutdown()`

#### **`db/database.py`**
- **Purpose**: Database connection management
- **Responsibilities**:
  - Async engine creation
  - Session factory
  - Database URL construction from env vars
  - Table initialization
- **Key Class**: `DatabaseManager`

#### **`controller_config.py`**
- **Purpose**: File-based configuration storage
- **Responsibilities**:
  - Read/write controller_config.json
  - Thread-safe operations
  - Orchestrator registration
- **Key Class**: `_ControllerConfig`

#### **`api/v1/controller.py`**
- **Purpose**: External-facing REST API
- **Endpoints**: `/api/v1/controller/*`
- **Responsibilities**:
  - Public API routes
  - Authentication (Bearer token)
  - Status override for independent orchestrators
- **Key Functions**: `_dev_auth()`, status override logic

#### **`api/v1/internal.py`**
- **Purpose**: Internal API for orchestrator management
- **Endpoints**: `/api/v1/internal/*`
- **Responsibilities**:
  - Login endpoint
  - Independence toggle
  - Message management
  - Health check
- **Key Functions**: `toggle_independence()`, `create_message()`

#### **`utils/controller_state.py`**
- **Purpose**: In-memory orchestrator state
- **Responsibilities**:
  - Track active connections
  - Store last seen timestamps
  - Thread-safe state management
- **Key Functions**: `mark_handshake()`, `mark_keepalive()`, `list_orchestrators()`

#### **`models/organization.py`**
- **Purpose**: SQLAlchemy ORM models
- **Key Classes**: `Organization`, `OrchestratorInstance`

#### **`models/orchestrator_message.py`**
- **Purpose**: Message model
- **Key Class**: `OrchestratorMessage`

---

### **Frontend Files**

#### **`gui/frontend/src/App.tsx`**
- **Purpose**: Main routing component
- **Responsibilities**: Route definitions, authentication guard

#### **`gui/frontend/src/pages/dashboard/dashboard.tsx`**
- **Purpose**: Overview dashboard
- **Responsibilities**: Display orchestrator status, error handling

#### **`gui/frontend/src/pages/dashboard/organizations-detail.tsx`**
- **Purpose**: Independence toggle UI
- **Responsibilities**: Toggle independence, display messages, handle recommendations

#### **`gui/frontend/src/pages/auth/login.tsx`**
- **Purpose**: Superadmin login page
- **Responsibilities**: Authentication UI, redirect after login

#### **`gui/frontend/src/lib/api.ts`**
- **Purpose**: Axios API client configuration
- **Responsibilities**: Base URL, bearer token injection

---

## Data Flow

### **1. Orchestrator Connection**
```
Orchestrator Client
  ↓
WebSocket Connection (ws://4.155.149.35/ws)
  ↓
main.py websocket_handler()
  ↓
register_orchestrator()
  ↓
Database INSERT into orchestrator_instances
  ↓
State Update via controller_state.py
  ↓
Send handshake_ack → Orchestrator
```

### **2. Heartbeat Processing**
```
Orchestrator sends i_am_alive (every 30s)
  ↓
WebSocket receives message
  ↓
Check independence status (query database)
  ↓
IF independent:
  → Log "[C-OCS] Ignoring heartbeat"
  → Skip processing
IF NOT independent:
  → Log "[C-OCS] Processing heartbeat"
  → Update database (last_seen, status)
  → Update in-memory state
```

### **3. Independence Toggle**
```
User clicks toggle in UI
  ↓
PUT /api/v1/internal/orchestrators/{id}/independence
  ↓
Update database (is_independent = true/false)
  ↓
Write to .env files (for persistence)
  ↓
Return success
  ↓
Frontend updates UI (status badge, messages visibility)
  ↓
Next heartbeat triggers independence check
  ↓
Controller processes or ignores accordingly
```

### **4. Message Flow**
```
POST /api/v1/internal/orchestrators/{id}/messages
  ↓
Insert into orchestrator_messages table
  ↓
Status = 'pending'
  ↓
UI fetches messages via GET /api/v1/internal/messages
  ↓
Display in Organization Details page
  ↓
User clicks Accept/Dismiss
  ↓
PUT /api/v1/internal/messages/{id}/status
  ↓
Update message status to 'accepted' or 'dismissed'
```

---

## Deployment

### **Environment Variables**

**Controller (`docker-compose.yml`):**
```yaml
- DATABASE_HOST=postgres
- DATABASE_PORT=5432
- DATABASE_USER=moolai
- DATABASE_PASSWORD=moolai_password
- DATABASE_NAME=moolai_controller
- CONTROLLER_HOST=0.0.0.0
- CONTROLLER_PORT=8765
- DEV_BEARER_TOKEN=fake-dev-token
- HEARTBEAT_TTL_SEC=120
- HEARTBEAT_POKER_ENABLED=false
```

**Orchestrator Client:**
```bash
export ORCHESTRATOR_ID=orch-001
export CONTROLLER_WS_URL=ws://4.155.149.35/ws
export HEARTBEAT_INTERVAL_SEC=30
export ORCHESTRATOR_HTTP_ENABLED=false
```

### **Docker Compose Services**
- **postgres**: PostgreSQL database
- **controller**: FastAPI backend
- **frontend**: Nginx with React build

### **Access Points**
- Frontend: `http://4.155.149.35`
- Controller API: `http://4.155.149.35:8765`
- WebSocket: `ws://4.155.149.35/ws`
- PostgreSQL: `4.155.149.35:5432`

---

## Conclusion

The Moolai Controller Service provides a robust, scalable platform for managing multiple orchestrator instances with:
- Real-time status tracking via WebSocket
- Independence mode for autonomous operation
- Message routing and management
- Multi-tenant support
- Secure authentication
- Comprehensive monitoring and analytics

All components are containerized and deployed on Azure VM for high availability and easy scaling.

