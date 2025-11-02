# High-Level Design (HLD) - Moolai Controller Service

## Document Information
- **Version**: 2.0
- **Last Updated**: October 27, 2025
- **Audience**: Technical Leads, System Architects, DevOps Engineers
- **Purpose**: Comprehensive architectural documentation for the Moolai Controller system

---

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [System Overview](#2-system-overview)
3. [Core Architecture](#3-core-architecture)
4. [Data Architecture](#4-data-architecture)
5. [Communication Protocols](#5-communication-protocols)
6. [Core Components & Responsibilities](#6-core-components--responsibilities)
7. [Independence Mode Feature](#7-independence-mode-feature)
8. [Data Flow Scenarios](#8-data-flow-scenarios)
9. [Deployment Architecture](#9-deployment-architecture)
10. [File Structure & Key Files](#10-file-structure--key-files)
11. [Operational Considerations](#11-operational-considerations)
12. [Future Enhancements](#12-future-enhancements)

---

## 1. Executive Summary

### 1.1 Purpose

The Moolai Controller is a centralized management and monitoring platform designed to oversee multiple Moolai orchestrator instances across organizations. It provides real-time status tracking, configuration management, and autonomous operation capabilities through a modern web-based interface.

### 1.2 Scope

**What the Controller Does**:
- Manages lifecycle and connectivity of multiple orchestrator instances
- Monitors orchestrator health via WebSocket heartbeats
- Provides independence mode for autonomous orchestrator operation
- Routes messages (recommendations, monitoring data) between orchestrators and administrators
- Delivers configuration updates to connected orchestrators
- Supports multi-tenant organization management
- Offers a React-based dashboard for visualization and control

**What the Controller Does NOT Do**:
- Does not run LLM inference or AI workloads (delegated to orchestrators)
- Does not store chat history or user conversations
- Does not directly interact with end users (only administrators)
- Does not provision cloud infrastructure (manual deployment)

### 1.3 Key Capabilities

| Capability | Description | Status |
|------------|-------------|--------|
| **Orchestrator Monitoring** | Real-time heartbeat tracking, connection status, health metrics | ✅ Active |
| **Independence Mode** | Allow orchestrators to operate autonomously without controller dependency | ✅ Active |
| **Message Routing** | Forward recommendations and monitoring data from orchestrators | ✅ Active |
| **Configuration Provisioning** | Push configuration updates to orchestrators on connect or on-demand | ✅ Active |
| **Multi-Organization Support** | Manage multiple tenants/organizations with isolated orchestrator groups | ✅ Active |
| **Authentication** | Superadmin bearer token-based authentication for API and UI access | ✅ Active |
| **Real-time Dashboard** | Live status updates, statistics, and operational visibility | ✅ Active |
| **Cost Analytics** | Track and forecast orchestrator operational costs | 🟡 Stubbed |
| **Auto-Provisioning** | Automatically spin up/down orchestrator containers | ❌ Future |

---

## 2. System Overview

### 2.1 What is the Moolai Controller?

The Moolai Controller acts as a **central hub** for managing distributed orchestrator instances. It tracks which orchestrators are online, pushes configuration changes in real-time, collects operational data, provides administrative visibility through a web UI, and enables orchestrators to operate independently when needed.

### 2.2 Role in the Moolai Ecosystem

```
┌─────────────────────────────────────────────────────────────────┐
│                      Moolai Ecosystem                           │
│                                                                 │
│  ┌──────────────┐                                              │
│  │   Admin UI   │ (Dashboard, monitoring, configuration)       │
│  └──────┬───────┘                                              │
│         │                                                       │
│         ▼                                                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              MOOLAI CONTROLLER (This System)             │  │
│  │                                                          │  │
│  │  - Orchestrator registration & heartbeat monitoring     │  │
│  │  - Configuration provisioning                           │  │
│  │  - Message routing                                      │  │
│  │  - Independence mode management                         │  │
│  └───────────────────┬──────────────────────────────────────┘  │
│                      │                                          │
│         ┌────────────┼────────────┬─────────────────┐          │
│         │            │            │                 │          │
│         ▼            ▼            ▼                 ▼          │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐   ┌───────────┐   │
│  │Orchestrator│ │Orchestrator│ │Orchestrator│...│Orchestrator│  │
│  │  (org-1)  │ │  (org-2)  │ │  (org-3)  │   │  (org-N)  │   │
│  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘   └─────┬─────┘   │
│        │             │             │               │          │
│        ▼             ▼             ▼               ▼          │
│  [End Users]   [End Users]   [End Users]     [End Users]     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Relationship to Orchestrators**:
- Each orchestrator is a standalone AI inference engine serving end users
- Orchestrators connect to the controller via WebSocket (persistent connection)
- Controller does NOT proxy user traffic (orchestrators handle users directly)
- Controller acts as a management plane, not a data plane

---

## 3. Core Architecture

### 3.1 Architectural Style

The Moolai Controller follows a **microservices-based containerized architecture** with:
- **Event-Driven Communication**: WebSocket-based real-time bidirectional messaging
- **RESTful API**: Standard HTTP/JSON API for management operations
- **Separation of Concerns**: Frontend (presentation), backend (business logic), database (persistence)
- **Stateful + Stateless Hybrid**: In-memory state for real-time operations, database for persistence

### 3.2 Design Decisions

#### Why FastAPI?
- Native async/await for high-concurrency WebSocket connections
- Built-in WebSocket support
- High performance (comparable to Node.js/Go)
- Type safety with Pydantic models
- Auto-generated OpenAPI/Swagger docs

#### Why PostgreSQL?
- ACID compliance for data consistency
- Relational data fits Organizations → Orchestrators model
- JSONB support for flexible schema
- Proven reliability with strong tooling
- Excellent async performance with asyncpg

#### Why Docker Compose?
- Single command deployment
- Environment consistency across dev/staging/production
- Automatic dependency management
- Network isolation and DNS resolution
- Persistent storage for database and configuration

#### Why WebSocket over HTTP Polling?
- Real-time bidirectional communication
- Single persistent connection (efficient)
- Sub-second message delivery
- Lower overhead than repeated HTTP requests
- Perfect for periodic heartbeat messages

### 3.3 System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                   Azure VM (B2 Instance)                        │
│                   4.155.149.35                                  │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │   Frontend   │    │  Controller  │    │  PostgreSQL  │     │
│  │   (Nginx)    │◄───┤   (FastAPI)  │◄───┤   Database   │     │
│  │              │    │              │    │              │     │
│  │  Port: 80    │    │  Port: 8765  │    │  Port: 5432  │     │
│  │              │    │              │    │              │     │
│  │  - React UI  │    │  - REST API  │    │  - orgs      │     │
│  │  - Dashboard │    │  - WebSocket │    │  - instances │     │
│  │  - Proxy API │    │  - Auth      │    │  - messages  │     │
│  │    calls     │    │  - State Mgmt│    │  - users     │     │
│  └──────────────┘    └───────┬──────┘    └──────────────┘     │
│                              │                                 │
│                              │ WebSocket (/ws)                 │
│                              │ Persistent Connection           │
│                              ▼                                 │
│                    ┌──────────────────┐                        │
│                    │  External Orch.  │                        │
│                    │  (ws_client)     │                        │
│                    └──────────────────┘                        │
│                                                                 │
│  Docker Network: moolai-network (bridge)                       │
│  All services communicate via container names (DNS)            │
└─────────────────────────────────────────────────────────────────┘

External Orchestrators (anywhere with internet):
  ws://4.155.149.35/ws
  
  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
  │ Orch-001     │    │ Orch-002     │    │ Orch-N       │
  │ (Local Mac)  │    │ (AWS)        │    │ (Edge Device)│
  └──────────────┘    └──────────────┘    └──────────────┘
```

### 3.4 Data Flow Overview

**Request Flow (UI → API)**:
```
User Browser → Nginx (Port 80) → Proxy to FastAPI (Port 8765) → Query PostgreSQL → Return JSON
```

**WebSocket Flow (Orchestrator ↔ Controller)**:
```
Orchestrator → ws://controller/ws → WebSocket Handler → 
  ├─> Update Database (if not independent)
  ├─> Update In-Memory State
  └─> Send Response (ack, config, etc.)
```

**Configuration Push Flow**:
```
Admin UI → PUT /api/v1/internal/... → Update DB → WebSocket Send → Orchestrator Receives
```

---

## 4. Data Architecture

### 4.1 Database Schema

The controller uses PostgreSQL with three primary tables:

#### 4.1.1 Organizations Table

**Purpose**: Store tenant/organization information for multi-tenant support

```sql
CREATE TABLE organizations (
    organization_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    is_active BOOLEAN DEFAULT true,
    is_independent BOOLEAN DEFAULT false,
    settings JSONB DEFAULT '{}',
    admin_email VARCHAR(255),
    support_email VARCHAR(255),
    website VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Key Columns**:
- `organization_id`: Unique business identifier (e.g., "org-001")
- `is_independent`: Organization-level independence flag (inherited by orchestrators)
- `settings`: Flexible JSONB for custom configuration

**Relationships**: One organization → Many orchestrator instances

#### 4.1.2 Orchestrator Instances Table

**Purpose**: Track all orchestrator instances and their operational state

```sql
CREATE TABLE orchestrator_instances (
    id SERIAL PRIMARY KEY,
    orchestrator_id VARCHAR(50) UNIQUE NOT NULL,
    organization_id VARCHAR(50) REFERENCES organizations(organization_id),
    name VARCHAR(255) NOT NULL,
    organization_name VARCHAR(255),
    status VARCHAR(20) DEFAULT 'inactive',
    health_status JSONB DEFAULT '{}',
    is_independent BOOLEAN DEFAULT false,
    last_seen TIMESTAMP,
    
    -- Configuration
    features JSONB DEFAULT '{}',
    session_config JSONB DEFAULT '{}',
    privacy_mode BOOLEAN DEFAULT false,
    
    -- Connection Information
    internal_url VARCHAR(255),
    database_url VARCHAR(255),
    redis_url VARCHAR(255),
    
    -- Container Information
    container_id VARCHAR(100),
    image_name VARCHAR(255),
    environment_variables JSONB DEFAULT '{}',
    
    -- Monitoring
    phoenix_endpoint VARCHAR(255),
    monitoring_enabled BOOLEAN DEFAULT false,
    
    -- Contact & Metadata
    admin_email VARCHAR(255),
    support_email VARCHAR(255),
    website VARCHAR(255),
    last_activity TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Key Columns**:
- `orchestrator_id`: Unique business identifier (e.g., "orch-001")
- `is_independent`: **Independence mode flag** - controls heartbeat processing
- `last_seen`: Timestamp of last received heartbeat (frozen when independent)
- `health_status`: JSONB storing health metrics
- `session_config`: JSONB for orchestrator-specific settings

**Relationships**: Many orchestrator instances → One organization

#### 4.1.3 Orchestrator Messages Table

**Purpose**: Queue and track messages sent to/from orchestrators

```sql
CREATE TABLE orchestrator_messages (
    id SERIAL PRIMARY KEY,
    orchestrator_id VARCHAR(50) NOT NULL,
    message_type VARCHAR(50) NOT NULL,
    message_content JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Use Cases**: Async message delivery queue, retry logic, audit trail

### 4.2 In-Memory Data Structures

The controller maintains in-memory state for real-time operations to avoid database overhead on every heartbeat.

#### Active Connections Map

```python
_ORCHESTRATORS: Dict[str, Dict[str, Any]] = {
    "orch-001": {
        "websocket": WebSocket,
        "last_seen": datetime,
        "connected_at": datetime,
        "metadata": {...}
    }
}
```

**Why In-Memory?**
- O(1) lookup without database query
- Instant access to connection state
- Reduces database load (heartbeats every 30s)
- Complementary to database (not a replacement)

**Tradeoff**: State is lost on controller restart (acceptable - orchestrators reconnect)

---

## 5. Communication Protocols

### 5.1 WebSocket Protocol

The controller uses WebSocket (RFC 6455) for persistent, bidirectional communication with orchestrators.

#### Connection Lifecycle

```
1. CONNECT
   Orchestrator → ws://4.155.149.35/ws
   WebSocket connection established

2. REGISTER
   Orchestrator → Controller
   {"type": "register", "orchestrator_id": "orch-001", ...}

3. HANDSHAKE ACK
   Controller → Orchestrator
   {"type": "handshake_ack", "success": true, ...}

4. PROVISIONING
   Controller → Orchestrator
   {"type": "provisioning", "config": {...}, ...}

5. HEARTBEAT LOOP (every 30 seconds)
   Orchestrator → Controller
   {"type": "i_am_alive", "orchestrator_id": "orch-001"}

6. DISCONNECT
   WebSocket close → Controller cleans up state
```

#### Supported Message Types

| Type | Direction | Purpose | Independence Mode Behavior |
|------|-----------|---------|---------------------------|
| `register` | Orch → Controller | Initial connection handshake | Processed normally |
| `i_am_alive` | Orch → Controller | Heartbeat keepalive | **Ignored if independent** |
| `handshake_ack` | Controller → Orch | Registration confirmation | Sent normally |
| `provisioning` | Controller → Orch | Configuration push | Sent normally |
| `recommendation` | Orch → Controller | ML model recommendations | Processed normally |
| `monitoring` | Orch → Controller | Performance metrics | Processed normally |
| `config_update` | Controller → Orch | Runtime config change | Sent normally |

#### Heartbeat Processing Logic

```
Receive {"type": "i_am_alive", "orchestrator_id": "X"}
  │
  ├─> Query Database: SELECT is_independent WHERE orchestrator_id = 'X'
  │
  ├─> IF is_independent = FALSE:
  │   ├─> Log: "Processing heartbeat from X"
  │   ├─> UPDATE last_seen = NOW()
  │   └─> Update in-memory state
  │
  └─> ELSE (is_independent = TRUE):
      ├─> Log: "Ignoring heartbeat from independent orchestrator X"
      └─> Skip all updates
```

### 5.2 REST API Protocol

#### Authentication
- Bearer token in `Authorization` header
- Validated against `DEV_BEARER_TOKEN` environment variable
- Returns `403 Forbidden` if invalid

#### Response Format

**Success**:
```json
{
  "success": true,
  "data": {...},
  "timestamp": "2025-10-27T10:30:00Z"
}
```

**Error**:
```json
{
  "success": false,
  "error": "Error type",
  "detail": "Detailed message"
}
```

#### Key API Endpoints

**Public Controller API** (`/api/v1/controller`):
- `GET /overview` - System statistics
- `GET /organizations` - List organizations (paginated)
- `GET /orchestrators` - List orchestrators (paginated)
- `GET /orchestrators/live` - Active connections (real-time)
- `GET /health` - Health check
- `GET /costs` - Cost analytics (stubbed)

**Internal Management API** (`/api/v1/internal`):
- `POST /auth/login` - Superadmin login
- `PUT /orchestrators/{id}/independence` - Toggle independence mode
- `POST /orchestrators/{id}/messages` - Send message to orchestrator
- `GET /messages` - Retrieve orchestrator messages
- `PUT /messages/{id}/status` - Update message status
- `GET /health` - Internal health + WebSocket status

---

## 6. Core Components & Responsibilities

### 6.1 Controller Backend (FastAPI Application)

**File**: `controller/app/main.py`

**Primary Responsibilities**:
- Initialize database connections on startup
- Register API routes and middleware
- Host WebSocket endpoint at `/ws`
- Configure CORS for frontend communication
- Coordinate between database, state management, and API layers

**Key Behaviors**:
- **On Startup**: Connect to PostgreSQL, load configuration, initialize state
- **On Shutdown**: Close connections, cleanup resources
- **Continuous**: Accept WebSocket connections, process heartbeats, handle API requests

### 6.2 WebSocket Communication Layer

**File**: `controller/app/main.py` (websocket_handler function)

**Primary Responsibilities**:
- Accept and maintain persistent WebSocket connections
- Process incoming messages (register, i_am_alive, recommendations, monitoring)
- Implement independence mode logic (query database, decide to process or ignore)
- Send outgoing messages (handshake_ack, provisioning, config_update)
- Update both in-memory state and database persistence

**Independence Mode Logic**:
```python
# Query database for is_independent flag
result = await db.execute("SELECT is_independent WHERE orchestrator_id = ?")
if result.is_independent:
    logger.info("Ignoring heartbeat from independent orchestrator")
    continue  # Skip processing
else:
    logger.info("Processing heartbeat")
    # Update last_seen, update state
```

### 6.3 Database Persistence Layer

**File**: `controller/app/db/database.py`

**Primary Responsibilities**:
- Manage PostgreSQL connection pool
- Provide async session management
- Build connection string from environment variables
- Handle connection failures and retries

**Configuration**:
- Uses SQLAlchemy async engine with asyncpg driver
- Connection pooling for performance
- Environment-based configuration

### 6.4 REST API Layer

#### Public Controller API
**File**: `controller/app/api/v1/controller.py`

**Purpose**: External-facing API for dashboard and monitoring

**Key Features**:
- System overview statistics
- Organization and orchestrator listing with pagination
- Live connection status from in-memory state
- Health checks for load balancers

#### Internal Management API
**File**: `controller/app/api/v1/internal.py`

**Purpose**: Administrative operations and orchestrator management

**Key Features**:
- Superadmin authentication (hardcoded for dev)
- Independence mode toggle (updates DB + config files)
- Message queue management
- Internal health check with WebSocket status

### 6.5 State Management

**File**: `controller/app/utils/controller_state.py`

**Primary Responsibilities**:
- Track active WebSocket connections in-memory
- Store orchestrator metadata (last_seen, connection time)
- Provide thread-safe access (RLock)
- Enable fast lookups without database queries

**Key Functions**:
- `mark_handshake()` - Register new connection
- `mark_keepalive()` - Update heartbeat timestamp
- `remove_orchestrator()` - Clean up on disconnect
- `list_orchestrators()` - Get all active connections

### 6.6 Configuration Management

**File**: `controller/app/controller_config.py`

**Primary Responsibilities**:
- Load and manage `controller_config.json`
- Provide thread-safe access to configuration
- Support runtime configuration updates
- Store organization and orchestrator metadata

**Configuration Structure**:
```json
{
  "organizations": {
    "org-001": {
      "name": "Default Orchestrator",
      "orchestrators": ["orch-001"],
      "is_independent": false
    }
  }
}
```

### 6.7 Additional Components

- **Activity Buffer** (`utils/buffer_manager.py`): In-memory logging for debugging
- **Message Routing** (`utils/dispatch.py`): Route messages between orchestrators and controller
- **Configuration Provisioning** (`utils/provisioning.py`): Push configuration updates to orchestrators
- **Frontend Dashboard** (`gui/frontend/`): React + Vite + TailwindCSS + Nginx

---

## 7. Independence Mode Feature

### 7.1 Purpose & Business Value

**What is Independence Mode?**

Independence Mode allows orchestrator instances to operate autonomously without requiring active management or monitoring from the controller. This decouples the orchestrator's operational status from the controller's availability.

**Key Concept**: When enabled:
- Orchestrator continues sending heartbeats (maintains WebSocket connection)
- Controller **receives** but **ignores** those heartbeats
- No database updates occur for that orchestrator
- Orchestrator operates as if the controller doesn't exist (from a monitoring perspective)

**Why Independence Mode?**

✅ **High Availability**: Production orchestrators continue functioning if controller goes offline
✅ **Reduced Dependency**: Critical orchestrators don't rely on controller health checks
✅ **Flexible Deployment**: Mix managed and autonomous orchestrators
✅ **Operational Freedom**: Deploy in isolated environments (air-gapped, edge)
✅ **Testing**: Local development without affecting production monitoring

**Use Cases**:
1. **Production Deployments**: Mission-critical orchestrators with 24/7 uptime requirements
2. **Edge Deployments**: Remote locations with intermittent connectivity
3. **Development**: Local orchestrators on developer machines
4. **Staged Rollouts**: Gradual transition from managed to autonomous
5. **Multi-Region**: Geographic distribution with regional autonomy

### 7.2 Architecture & Behavior

```
┌─────────────────────────────────────────────────────────────────────┐
│                    WebSocket Handler Decision Flow                  │
└─────────────────────────────────────────────────────────────────────┘

Receive Heartbeat: {"type": "i_am_alive", "orchestrator_id": "X"}
  │
  ▼
Query Database: SELECT is_independent FROM orchestrator_instances
  │
  ├─────────────┬─────────────┐
  │             │             │
  ▼             ▼             ▼
FALSE         TRUE          NULL
  │             │             │
  ▼             ▼             ▼
PROCESS       IGNORE      ERROR
  │             │
  ├─> Log: "Processing heartbeat"
  ├─> UPDATE last_seen = NOW()
  └─> Update in-memory state
                │
                ├─> Log: "Ignoring heartbeat"
                └─> Skip all updates

┌─────────────────────────────────────────────────────────────────────┐
│                         Database State                              │
└─────────────────────────────────────────────────────────────────────┘

orchestrator_instances:
┌────────────────┬─────────────┬──────────────────┐
│ orchestrator_id│is_independent│    last_seen     │
├────────────────┼─────────────┼──────────────────┤
│ orch-001       │   FALSE     │ 2025-10-27 10:30 │  ← Updates every 30s
│ orch-002       │   TRUE      │ 2025-10-27 09:00 │  ← Frozen (stale)
└────────────────┴─────────────┴──────────────────┘
```

### 7.3 Implementation Details

#### Database Schema

**orchestrator_instances.is_independent** (boolean, default: false)
- Per-orchestrator flag
- Directly controls heartbeat processing
- Queried on every `i_am_alive` message

**organizations.is_independent** (boolean, default: false)
- Organization-level flag
- Can be inherited by orchestrators (future enhancement)

#### State Transitions

```
┌──────────────┐                                    ┌──────────────┐
│   MANAGED    │  Toggle independence ON           │ INDEPENDENT  │
│    MODE      │ ─────────────────────────────────>│     MODE     │
│              │                                    │              │
│ Heartbeats   │                                    │ Heartbeats   │
│ processed    │                                    │ ignored      │
│ last_seen    │                                    │ last_seen    │
│ updated      │                                    │ frozen       │
│ Status:      │                                    │ Status:      │
│ "Active"     │  Toggle independence OFF          │ "Independent"│
│              │ <─────────────────────────────────│              │
└──────────────┘                                    └──────────────┘
```

#### Toggle Mechanism Flow

```
1. Admin Action (UI)
   └─> Click toggle switch in Organizations page

2. Frontend Request
   └─> PUT /api/v1/internal/orchestrators/{id}/independence
       Body: {"is_independent": true}

3. Controller Processing
   ├─> Update database: is_independent = true
   ├─> Write to /app/controller/app/.env
   ├─> Write to /app/controller/app/db/orchestrator_independence.json
   └─> Return success

4. Immediate Effect
   └─> Next heartbeat (within 30s) is ignored
```

#### Configuration Persistence

Independence settings persisted in **three locations**:

1. **PostgreSQL Database** (Primary source of truth)
   - Queried on every heartbeat
   - Real-time operational state

2. **Environment File** (`/app/controller/app/.env`)
   - Format: `ORCHESTRATOR_{ID}_INDEPENDENT=true`
   - Loaded on controller startup

3. **JSON Configuration** (`/app/controller/app/db/orchestrator_independence.json`)
   - Human-readable, version-controllable
   - Backup configuration store

**Why Three Locations?**
- Database: Real-time operational state
- .env: Environment-based configuration (Docker best practice)
- JSON: Portable, auditable configuration

### 7.4 Behavioral Differences

| Aspect | Managed Mode | Independence Mode |
|--------|--------------|-------------------|
| **Heartbeat Processing** | ✓ Processed | ✗ Ignored |
| **Database Updates** | ✓ last_seen updated | ✗ Frozen |
| **In-Memory State** | ✓ Updated | ✗ Not updated |
| **UI Status** | "Active" (green) | "Independent" (blue) |
| **Last Seen** | Current (e.g., "2s ago") | Frozen (e.g., "2h ago") |
| **WebSocket Connection** | ✓ Maintained | ✓ Maintained |
| **Configuration Push** | ✓ Works | ✓ Still works |
| **Message Routing** | ✓ Enabled | ✓ Still works |
| **Controller Dependency** | High | Low |

**Key Insight**: WebSocket connection remains open in both modes. Independence mode only affects heartbeat processing, not the connection itself.

### 7.5 User Experience & UI Behavior

**Dashboard View**:
```
┌────────────────────────────────────────────────────────────┐
│  Organizations                                             │
├────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐ │
│  │ Default Orchestrator (org-001)                       │ │
│  │ Orchestrator: orch-001                              │ │
│  │ Status: ● Active              Independence: [OFF]   │ │
│  │ Last Seen: 2 seconds ago                            │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ Production Orchestrator (org-002)                    │ │
│  │ Orchestrator: orch-002                              │ │
│  │ Status: ◆ Independent         Independence: [ON]    │ │
│  │ Last Seen: 2 hours ago (frozen)                     │ │
│  └──────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

**Visual Indicators**:
- **Active**: `●` Green badge - Heartbeats processed, last_seen current
- **Independent**: `◆` Blue badge - Autonomous mode, last_seen frozen
- **Inactive**: `○` Gray badge - No recent heartbeats
- **Error**: `✖` Red badge - Connection error

### 7.6 Logging & Observability

**Controller Logs (Normal Mode)**:
```
[2025-10-27 10:30:15] INFO: [C-OCS] Processing heartbeat from orchestrator orch-001
[2025-10-27 10:30:15] DEBUG: Updating last_seen for orch-001 in database
```

**Controller Logs (Independence Mode)**:
```
[2025-10-27 10:30:15] INFO: [C-OCS] Ignoring heartbeat from independent orchestrator orch-002
[2025-10-27 10:30:15] DEBUG: Skipping database update for independent orchestrator
```

**How to Monitor**:

1. **Check Controller Logs**:
   ```bash
   docker-compose logs controller -f | grep -E "Processing|Ignoring"
   ```

2. **Query Database**:
   ```sql
   SELECT orchestrator_id, is_independent, last_seen 
   FROM orchestrator_instances;
   ```

3. **Check UI**: Navigate to Organizations page, look for "Independent" badge

4. **Check Config Files**:
   ```bash
   docker exec moolai-controller cat /app/controller/app/.env | grep INDEPENDENT
   docker exec moolai-controller cat /app/controller/app/db/orchestrator_independence.json
   ```

### 7.7 Operational Scenarios

**Scenario 1: Controller Downtime**

```
Before:
  orch-001 (Managed): Relies on controller
  orch-002 (Independent): Autonomous

Controller Goes Offline:
  orch-001: May be impacted (depends on orchestrator resilience)
  orch-002: No impact (designed for this)

Recommendation: Enable independence for production orchestrators
```

**Scenario 2: Debugging Independent Orchestrator**

```
Problem: Independent orchestrator not responding

1. Temporarily disable independence (toggle OFF)
2. Wait for heartbeat processing to resume (< 30s)
3. Investigate orchestrator health using controller data
4. Fix issue
5. Re-enable independence (toggle ON)
```

### 7.8 Best Practices

**✓ DO Enable For**:
- Production orchestrators with high uptime requirements
- Remote/edge deployments with intermittent connectivity
- Mission-critical instances (healthcare, finance, emergency services)
- Proven stable orchestrators (running smoothly for 1+ week)

**✗ DON'T Enable For**:
- New orchestrators still being tested
- Development/staging environments where monitoring is valuable
- Orchestrators with known stability issues
- Instances requiring active health monitoring

**Configuration Recommendations**:
1. **Start Managed**: Deploy all new orchestrators in managed mode first
2. **Monitor First**: Observe behavior for at least 1 week
3. **Gradual Rollout**: Enable independence for one orchestrator at a time
4. **Document State**: Keep a record of which orchestrators are independent and why
5. **Regular Reviews**: Periodically review independence settings (quarterly)

**Monitoring Strategy for Independent Orchestrators**:
- Set up external health checks (not relying on controller)
- Use application-level monitoring (response time, error rate)
- Configure infrastructure monitoring (CPU, memory, disk)
- Set up log aggregation (ELK, Splunk)
- Create alerting rules (PagerDuty, OpsGenie)

### 7.9 Summary

Independence Mode is a powerful feature that:
- **Decouples** orchestrator operations from controller availability
- **Enables** high-availability production deployments
- **Simplifies** management of remote/edge orchestrators
- **Provides** flexibility in operational strategies

**Key Takeaway**: Independence mode gives you the best of both worlds - orchestrators can operate autonomously when needed, while still maintaining a connection to the controller for configuration and messaging.

---

## 8. Data Flow Scenarios

### 8.1 Orchestrator Registration Flow

```
1. Orchestrator starts ws_client
2. Connects to ws://controller:8765/ws
3. Sends: {"type": "register", "orchestrator_id": "orch-001", ...}
4. Controller queries/inserts database record
5. Controller updates in-memory state
6. Controller sends: {"type": "handshake_ack", "success": true}
7. Controller sends: {"type": "provisioning", "config": {...}}
8. Orchestrator receives config and applies it
9. Orchestrator starts heartbeat loop (every 30s)
```

### 8.2 Heartbeat Processing Flow (Normal Mode)

```
1. Orchestrator sends: {"type": "i_am_alive", "orchestrator_id": "orch-001"}
2. Controller queries: SELECT is_independent WHERE orchestrator_id = 'orch-001'
3. Result: is_independent = false
4. Controller logs: "Processing heartbeat from orchestrator orch-001"
5. Controller updates: UPDATE last_seen = NOW()
6. Controller updates in-memory state
```

### 8.3 Heartbeat Processing Flow (Independence Mode)

```
1. Orchestrator sends: {"type": "i_am_alive", "orchestrator_id": "orch-001"}
2. Controller queries: SELECT is_independent WHERE orchestrator_id = 'orch-001'
3. Result: is_independent = true
4. Controller logs: "Ignoring heartbeat from independent orchestrator orch-001"
5. Controller skips database update
6. Controller skips in-memory state update
7. Connection stays open (WebSocket maintained)
```

### 8.4 Independence Toggle Flow

```
1. Admin opens UI, navigates to Organizations page
2. Admin clicks toggle switch for orchestrator
3. Frontend sends: PUT /api/v1/internal/orchestrators/{id}/independence
   Body: {"is_independent": true}
4. Controller updates database
5. Controller writes to .env and JSON config files
6. Controller responds: {"success": true}
7. Frontend updates UI (toggle, status badge, toast notification)
8. Next heartbeat from orchestrator is ignored (immediate effect)
```

### 8.5 Dashboard Data Loading Flow

```
1. User opens dashboard in browser
2. React app loads, runs useEffect
3. Frontend makes parallel API calls:
   - GET /api/v1/controller/overview
   - GET /api/v1/controller/orchestrators
   - GET /api/v1/controller/organizations
   - GET /api/v1/controller/health
4. Nginx receives requests, proxies to controller
5. Controller queries PostgreSQL
6. Controller returns JSON responses
7. Frontend updates React state, renders UI
8. Frontend polls /orchestrators/live every 2s for real-time updates
```

---

## 9. Deployment Architecture

### 9.1 Docker Compose Services

**postgres**:
- Image: `postgres:15-alpine`
- Port: 5432
- Volumes: `postgres_data` for persistence
- Health check: `pg_isready`

**controller**:
- Build: `Dockerfile.controller`
- Port: 8765
- Depends on: postgres (waits for health check)
- Environment: Database credentials, controller settings
- Volumes: `controller_config.json` mounted

**frontend**:
- Build: `Dockerfile.frontend`
- Port: 80 (HTTP)
- Depends on: controller
- Nginx: Serves React build, proxies `/api/*` to controller

**Network**:
- All services on `moolai-network` bridge
- Internal DNS resolution (services reference by name)

### 9.2 Environment Configuration

**Controller Environment Variables**:
```
DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_USER=moolai
DATABASE_PASSWORD=moolai_password
DATABASE_NAME=moolai_controller
CONTROLLER_HOST=0.0.0.0
CONTROLLER_PORT=8765
DEV_BEARER_TOKEN=fake-dev-token
HEARTBEAT_TTL_SEC=120
HEARTBEAT_POKER_ENABLED=false  # Disabled
```

**Frontend Environment Variables**:
```
VITE_CONTROLLER_BASE_URL=""  # Empty for relative URLs
```

### 9.3 Deployment Flow

```
1. Build Images: docker-compose build
2. Start Services: docker-compose up -d
3. Database Init: Postgres creates schema on first run
4. Controller Startup: Initializes DB connection, starts WebSocket server
5. Frontend Startup: Nginx serves React app, proxies API calls
6. Health Checks: Services report healthy
7. Ready: System accepts orchestrator connections and UI traffic
```

### 9.4 Nginx Configuration

```nginx
server {
    listen 80;
    
    # Serve React build
    location / {
        root /usr/share/nginx/html;
        try_files $uri /index.html;
    }
    
    # Proxy API calls to controller
    location /api/ {
        proxy_pass http://controller:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
    }
    
    # Proxy WebSocket connections
    location /ws {
        proxy_pass http://controller:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## 10. File Structure & Key Files

```
controller/
├── app/
│   ├── main.py                          # FastAPI app, WebSocket handler
│   ├── settings.py                      # Environment variable loading
│   ├── controller_config.py             # JSON config management
│   │
│   ├── api/
│   │   └── v1/
│   │       ├── controller.py            # Public REST API
│   │       └── internal.py              # Internal management API
│   │
│   ├── db/
│   │   ├── database.py                  # PostgreSQL connection
│   │   └── controller_config.json       # Organization/orchestrator config
│   │
│   ├── models/
│   │   ├── organization.py              # Organization & OrchestratorInstance ORM
│   │   ├── orchestrator.py              # OrchestratorMessage ORM
│   │   └── user.py                      # User ORM (future)
│   │
│   ├── utils/
│   │   ├── controller_state.py          # In-memory connection state
│   │   ├── buffer_manager.py            # Activity logging
│   │   ├── dispatch.py                  # Message routing
│   │   └── provisioning.py              # Configuration push
│   │
│   └── gui/
│       └── frontend/                    # React + Vite frontend
│           ├── src/
│           │   ├── pages/dashboard/     # Dashboard, Organizations, Config
│           │   └── lib/api.ts           # Axios API client
│           └── dist/                    # Production build
│
├── docker-compose.yml                   # Multi-service orchestration
├── Dockerfile.controller                # Controller backend image
└── Dockerfile.frontend                  # Frontend + Nginx image
```

### Key Implementation Files

**Core Backend**:
- `controller/app/main.py` - FastAPI app and WebSocket handler
- `controller/app/api/v1/controller.py` - Public REST API
- `controller/app/api/v1/internal.py` - Internal management API
- `controller/app/db/database.py` - Database connection manager
- `controller/app/models/organization.py` - ORM models
- `controller/app/utils/controller_state.py` - In-memory state

**Frontend**:
- `controller/app/gui/frontend/src/pages/dashboard/dashboard.tsx`
- `controller/app/gui/frontend/src/pages/dashboard/organizations.tsx`
- `controller/app/gui/frontend/src/pages/dashboard/configuration.tsx`
- `controller/app/gui/frontend/src/lib/api.ts`

**Deployment**:
- `docker-compose.yml` - Service orchestration
- `Dockerfile.controller` - Backend image
- `Dockerfile.frontend` - Frontend + Nginx image

---

## 11. Operational Considerations

### 11.1 Monitoring & Observability

- Health check endpoints for service monitoring
- Activity buffer for debugging
- Database query logging (can be enabled)
- WebSocket connection tracking in-memory
- Controller logs: `docker-compose logs controller -f`

### 11.2 Scalability Considerations

- **Current**: In-memory state limits horizontal scaling (single instance)
- **Future**: Consider Redis for shared state in multi-instance deployment
- **WebSocket**: Stateful connections require sticky sessions for load balancing
- **Database**: Can handle multiple controller instances with shared state

### 11.3 Security

- Bearer token authentication for API access
- Environment variable-based secrets (not hardcoded)
- CORS configured for frontend domain
- Database credentials isolated in environment
- Internal API endpoints should be firewalled (not public)

### 11.4 Reliability

- Database health checks before startup
- Connection pooling for database resilience
- WebSocket reconnection logic in orchestrator client
- Independence mode for orchestrator autonomy
- Docker restart policies: `unless-stopped`

### 11.5 Backup & Recovery

**Database Backup**:
```bash
docker exec moolai-postgres pg_dump -U moolai moolai_controller > backup.sql
```

**Configuration Backup**:
```bash
docker cp moolai-controller:/app/controller/app/db/controller_config.json ./backup/
docker cp moolai-controller:/app/controller/app/.env ./backup/
```

**Restore**:
```bash
docker exec -i moolai-postgres psql -U moolai moolai_controller < backup.sql
```

---

## 12. Future Enhancements

**Potential improvements not yet implemented**:

1. **Redis for Shared State**: Enable multi-instance horizontal scaling
2. **Message Queue**: RabbitMQ/Kafka for async message delivery
3. **Metrics Export**: Prometheus integration for observability
4. **Distributed Tracing**: OpenTelemetry for request tracing
5. **RBAC**: Role-based access control with multiple admin levels
6. **Auto-Provisioning**: Docker API integration to spin up orchestrators
7. **Cost Tracking**: Integration with cloud provider APIs (AWS, Azure, GCP)
8. **Alert System**: Real-time alerts for orchestrator failures
9. **JWT Authentication**: Replace dev token with proper JWT
10. **Organization Inheritance**: Auto-apply independence to new orchestrators in org
11. **Backup Automation**: Scheduled database backups
12. **High Availability**: Multi-region controller deployment
13. **Audit Logging**: Complete audit trail of all admin actions
14. **GraphQL API**: Alternative to REST for complex queries
15. **WebSocket Compression**: Reduce bandwidth for heartbeats

---

## Conclusion

The Moolai Controller provides a centralized management platform for orchestrator instances with:
- **Real-time monitoring** via WebSocket heartbeats
- **Independence mode** for autonomous operation
- **Modern web interface** for visibility and control
- **Flexible deployment** with Docker Compose
- **Extensible architecture** for future enhancements

The architecture prioritizes simplicity, reliability, and ease of deployment while maintaining flexibility for production-scale operations.

---

**For questions or contributions, contact**: Technical Lead

**Last Updated**: October 27, 2025
