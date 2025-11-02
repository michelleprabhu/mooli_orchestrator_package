<!-- ed683c3b-2d6d-4361-ad5a-f8214548d803 421cddfb-949d-43c8-a6fc-adfc36cb73c6 -->
# Moolai Controller - High-Level Design Document

## Document Structure

### 1. Executive Summary

- **Purpose**: Brief overview of what the Controller does and why it exists
- **Scope**: Boundaries of the system (what it manages, what it doesn't)
- **Key Stakeholders**: Technical leads, architects, DevOps
- **Document Audience**: Technical decision-makers who need to understand system design

### 2. System Overview

- **What is the Moolai Controller?**
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Central management hub for multiple orchestrator instances
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Real-time monitoring and configuration platform
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Multi-tenant organization management

- **Role in Ecosystem**
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Relationship to orchestrator instances
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Position in overall Moolai architecture
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Integration points with external systems

- **High-Level Capabilities**
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Orchestrator lifecycle management
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Real-time heartbeat monitoring
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Independence mode (autonomous operation)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Message routing (recommendations, monitoring)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Configuration provisioning
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Multi-organization support

### 3. Architecture & Design Principles

#### 3.1 Architectural Style

- Microservices-based containerized deployment
- Event-driven communication via WebSocket
- RESTful API for management operations
- Separation of concerns (frontend, backend, database)

#### 3.2 Design Decisions

- **Why FastAPI**: Async support, WebSocket integration, performance
- **Why PostgreSQL**: ACID compliance, relational data, proven reliability
- **Why Docker Compose**: Simplified deployment, environment consistency
- **Why WebSocket**: Real-time bidirectional communication for heartbeats

#### 3.3 System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                   Azure VM (B2 Instance)                    │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │   Frontend   │◄───┤  Controller  │◄───┤  PostgreSQL  │ │
│  │   (Nginx)    │    │   (FastAPI)  │    │   Database   │ │
│  │              │    │              │    │              │ │
│  │  - React UI  │    │  - REST API  │    │  - orgs      │ │
│  │  - Dashboard │    │  - WebSocket │    │  - instances │ │
│  │  - Proxy     │    │  - Auth      │    │  - messages  │ │
│  └──────────────┘    └───────┬──────┘    └──────────────┘ │
│                              │                             │
│                              │ WebSocket (/ws)             │
│                              ▼                             │
│                    ┌──────────────────┐                    │
│                    │  Orchestrator    │                    │
│                    │  Instances       │                    │
│                    │  (ws_client)     │                    │
│                    └──────────────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

### 4. Core Components & Responsibilities

#### 4.1 Controller Backend (FastAPI Application)

**File**: `controller/app/main.py`

**Primary Responsibilities**:

- Initialize and manage application lifecycle
- Host REST API endpoints for management operations
- Provide WebSocket endpoint for orchestrator connections
- Coordinate between database, state management, and API layers
- Handle CORS for frontend communication
- Manage authentication and authorization

**Key Behaviors**:

- On startup: Initialize database connection, load configuration
- On shutdown: Close database connections, cleanup resources
- Continuous: Accept WebSocket connections, process heartbeats

#### 4.2 WebSocket Communication Layer

**File**: `controller/app/main.py` (websocket_handler function)

**Primary Responsibilities**:

- Accept and maintain persistent connections from orchestrators
- Process incoming messages (register, i_am_alive, status requests)
- Send outgoing messages (handshake_ack, provisioning, config updates)
- Implement independence mode logic (ignore heartbeats when enabled)
- Update both in-memory state and database persistence

**Message Types Handled**:

1. **register**: Initial connection handshake from orchestrator
2. **i_am_alive**: Periodic heartbeat (every 30s by default)
3. **recommendation**: ML model recommendations from orchestrator
4. **monitoring**: Performance metrics and logs
5. **config_update**: Configuration change requests

**Independence Mode Behavior**:

- When `is_independent = true` for an orchestrator:
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Controller logs heartbeat receipt but does NOT process it
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Database `last_seen` is NOT updated
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Orchestrator appears as "independent" status in UI
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Allows orchestrator to operate without controller dependency

#### 4.3 Database Persistence Layer

**File**: `controller/app/db/database.py`

**Primary Responsibilities**:

- Manage PostgreSQL connection pool
- Provide async session management for database operations
- Handle connection lifecycle (create, reuse, close)
- Build connection strings from environment variables

**Configuration**:

- Uses SQLAlchemy async engine with asyncpg driver
- Connection pooling for performance
- Environment-based configuration (host, port, credentials)

#### 4.4 REST API Layer

##### Public Controller API

**File**: `controller/app/api/v1/controller.py`

**Purpose**: External-facing API for dashboard and monitoring

**Key Endpoints**:

- `GET /api/v1/controller/overview`: System statistics (total orgs, active orchestrators)
- `GET /api/v1/controller/organizations`: List all organizations with pagination
- `GET /api/v1/controller/orchestrators`: List all orchestrator instances
- `GET /api/v1/controller/orchestrators/live`: Real-time active connections
- `GET /api/v1/controller/health`: System health check
- `GET /api/v1/controller/costs`: Cost analytics (stubbed)

**Authentication**: Bearer token via `Authorization` header

##### Internal Management API

**File**: `controller/app/api/v1/internal.py`

**Purpose**: Administrative operations and orchestrator management

**Key Endpoints**:

- `POST /api/v1/internal/auth/login`: Superadmin authentication
- `PUT /api/v1/internal/orchestrators/{id}/independence`: Toggle independence mode
- `POST /api/v1/internal/orchestrators/{id}/messages`: Send messages to orchestrator
- `GET /api/v1/internal/messages`: Retrieve orchestrator messages
- `PUT /api/v1/internal/messages/{id}/status`: Update message status
- `GET /api/v1/internal/health`: Internal health check with WebSocket status

**Special Behavior**:

- Independence toggle updates database AND writes to config files
- Health endpoint checks active WebSocket connections

#### 4.5 State Management

**File**: `controller/app/utils/controller_state.py`

**Primary Responsibilities**:

- Track active WebSocket connections in-memory
- Store orchestrator metadata (last_seen, status)
- Provide thread-safe access to connection state
- Enable fast lookups without database queries

**Key Functions**:

- `mark_handshake()`: Register new connection
- `mark_keepalive()`: Update heartbeat timestamp
- `remove_orchestrator()`: Clean up on disconnect
- `list_orchestrators()`: Get all active connections

**Why In-Memory State?**

- Fast access for real-time operations
- Reduces database load for frequent heartbeats
- Complements database persistence (not replaces)

#### 4.6 Configuration Management

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

#### 4.7 Activity Buffer

**File**: `controller/app/utils/buffer_manager.py`

**Primary Responsibilities**:

- Log controller operations in-memory
- Provide debugging and audit trail
- Buffer messages for batch processing
- Enable real-time activity monitoring

**Use Cases**:

- Debugging connection issues
- Tracking message flow
- Performance monitoring
- Audit logging

#### 4.8 Message Routing & Dispatch

**File**: `controller/app/utils/dispatch.py`

**Primary Responsibilities**:

- Route messages between orchestrators and controller
- Handle message type-specific logic
- Forward recommendations and monitoring data
- Manage message queuing and delivery

**Message Flow**:

1. Orchestrator sends message via WebSocket
2. Dispatch layer identifies message type
3. Routes to appropriate handler
4. Stores in database if needed
5. Sends acknowledgment back to orchestrator

#### 4.9 Configuration Provisioning

**File**: `controller/app/utils/provisioning.py`

**Primary Responsibilities**:

- Push configuration updates to orchestrators
- Handle orchestrator-specific settings
- Manage configuration versioning
- Validate configuration before sending

**Provisioning Triggers**:

- New orchestrator registration
- Configuration change via API
- Independence mode toggle
- Manual push from admin

#### 4.10 Frontend Dashboard

**Directory**: `controller/app/gui/frontend/`

**Technology Stack**:

- React 18 with TypeScript
- Vite for build tooling
- TailwindCSS for styling
- Nginx for serving and reverse proxy

**Key Pages**:

- **Dashboard**: Overview statistics, live orchestrators, cost charts
- **Organizations**: List and manage organizations
- **Configuration**: System health, WebSocket status, settings
- **Login**: Superadmin authentication

**Frontend Architecture**:

- Nginx serves static React build
- Nginx proxies API calls to controller backend
- Uses relative URLs for API calls (no CORS issues)
- Real-time updates via polling (every 2s for live data)

### 5. Data Architecture

#### 5.1 Database Schema

##### Organizations Table

**Purpose**: Store organization/tenant information

**Key Columns**:

- `organization_id` (PK): Unique identifier
- `name`: Organization display name
- `status`: active/inactive
- `is_active`: Boolean flag
- `is_independent`: Independence mode flag
- `settings`: JSONB for flexible configuration
- `created_at`, `updated_at`: Timestamps

**Relationships**:

- One organization → Many orchestrator instances

##### Orchestrator Instances Table

**Purpose**: Track all orchestrator instances

**Key Columns**:

- `id` (PK): Auto-increment ID
- `orchestrator_id` (Unique): Business identifier (e.g., "orch-001")
- `organization_id` (FK): Parent organization (nullable)
- `name`: Display name
- `status`: active/inactive/error
- `is_independent`: Independence mode flag
- `last_seen`: Last heartbeat timestamp
- `health_status`: JSON health metrics
- `features`: JSON feature flags
- `session_config`: JSON session configuration
- `internal_url`, `database_url`, `redis_url`: Connection strings
- `container_id`, `image_name`: Docker metadata
- `environment_variables`: JSON env vars
- `phoenix_endpoint`, `monitoring_enabled`: Observability settings
- `admin_email`, `support_email`, `website`: Contact info

**Relationships**:

- Many orchestrator instances → One organization

##### Orchestrator Messages Table

**Purpose**: Store messages sent to/from orchestrators

**Key Columns**:

- `id` (PK): Auto-increment ID
- `orchestrator_id`: Target orchestrator
- `message_type`: recommendation/monitoring/config/alert
- `message_content`: JSONB message payload
- `status`: pending/sent/delivered/failed
- `created_at`, `updated_at`: Timestamps

**Use Cases**:

- Message queue for async delivery
- Audit trail of communications
- Retry logic for failed messages

#### 5.2 In-Memory Data Structures

**Active Connections Map**:

```python
{
  "orch-001": {
    "websocket": WebSocket,
    "last_seen": datetime,
    "metadata": {...}
  }
}
```

**Activity Buffer**:

```python
[
  {"timestamp": "...", "event": "heartbeat", "orch_id": "orch-001"},
  {"timestamp": "...", "event": "register", "orch_id": "orch-002"}
]
```

### 6. Communication Protocols

#### 6.1 WebSocket Protocol

**Connection Lifecycle**:

1. **Connect**: Orchestrator initiates WebSocket connection to `ws://<controller>/ws`
2. **Register**: Orchestrator sends `{"type": "register", "orchestrator_id": "orch-001", ...}`
3. **Handshake**: Controller responds with `{"type": "handshake_ack", "success": true}`
4. **Provisioning**: Controller sends configuration via `{"type": "provisioning", "config": {...}}`
5. **Heartbeat Loop**: Orchestrator sends `{"type": "i_am_alive"}` every 30s
6. **Disconnect**: Connection closes, controller cleans up state

**Message Format**:

All messages are JSON with required `type` field:

```json
{
  "type": "message_type",
  "orchestrator_id": "orch-001",
  "timestamp": "2025-10-05T20:00:00Z",
  "payload": {...}
}
```

**Heartbeat Processing Logic**:

```
1. Receive i_am_alive message
2. Query database: SELECT is_independent FROM orchestrator_instances WHERE orchestrator_id = ?
3. IF is_independent = true:
     - Log: "Ignoring heartbeat from independent orchestrator"
     - Skip database update
     - Continue listening
   ELSE:
     - Log: "Processing heartbeat from orchestrator"
     - Update last_seen in database
     - Update in-memory state
     - Send acknowledgment (optional)
```

#### 6.2 REST API Protocol

**Authentication**:

- Bearer token in `Authorization` header
- Token validated against `DEV_BEARER_TOKEN` environment variable
- 403 Forbidden if invalid or missing

**Response Format**:

All API responses follow consistent structure:

```json
{
  "success": true,
  "data": {...},
  "message": "Optional message",
  "timestamp": "2025-10-05T20:00:00Z"
}
```

**Error Handling**:

```json
{
  "success": false,
  "error": "Error description",
  "detail": "Detailed error message"
}
```

**Pagination**:

List endpoints support pagination:

- Query params: `page` (default: 1), `page_size` (default: 10)
- Response includes: `items`, `total`, `page`, `page_size`

### 7. Independence Mode Feature

#### 7.1 Purpose & Business Value

**What is Independence Mode?**

Independence Mode is a feature that allows orchestrator instances to operate autonomously without requiring active management or monitoring from the controller. This decouples the orchestrator's operational status from the controller's availability.

**Why Independence Mode?**

- **High Availability**: Production orchestrators can continue functioning even if the controller goes offline
- **Reduced Dependency**: Critical orchestrators don't rely on controller health checks
- **Flexible Deployment**: Allows mixing managed and autonomous orchestrators in the same infrastructure
- **Operational Freedom**: Enables orchestrators to be deployed in isolated environments while maintaining registration
- **Testing & Development**: Useful for testing orchestrators without controller interference

**Use Cases**:

1. **Production Deployments**: Mission-critical orchestrators that must remain operational 24/7
2. **Edge Deployments**: Orchestrators in remote locations with intermittent controller connectivity
3. **Development Environments**: Local orchestrators that don't need active monitoring
4. **Staged Rollouts**: Gradually transition orchestrators from managed to autonomous state

#### 7.2 Architecture & Behavior

**System Architecture with Independence Mode**:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Controller System                           │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    WebSocket Handler                         │  │
│  │                                                              │  │
│  │  ┌────────────────────────────────────────────────────┐     │  │
│  │  │  Receive Heartbeat: {"type": "i_am_alive", ...}   │     │  │
│  │  └────────────────┬───────────────────────────────────┘     │  │
│  │                   │                                          │  │
│  │                   ▼                                          │  │
│  │  ┌────────────────────────────────────────────────────┐     │  │
│  │  │  Query Database:                                   │     │  │
│  │  │  SELECT is_independent                             │     │  │
│  │  │  FROM orchestrator_instances                       │     │  │
│  │  │  WHERE orchestrator_id = ?                         │     │  │
│  │  └────────────────┬───────────────────────────────────┘     │  │
│  │                   │                                          │  │
│  │         ┌─────────┴─────────┐                               │  │
│  │         │                   │                               │  │
│  │         ▼                   ▼                               │  │
│  │  ┌─────────────┐     ┌─────────────┐                       │  │
│  │  │is_independent│     │is_independent│                      │  │
│  │  │   = FALSE    │     │   = TRUE     │                      │  │
│  │  └──────┬───────┘     └──────┬───────┘                      │  │
│  │         │                    │                               │  │
│  │         ▼                    ▼                               │  │
│  │  ┌─────────────┐     ┌──────────────┐                       │  │
│  │  │  PROCESS    │     │   IGNORE     │                       │  │
│  │  │  HEARTBEAT  │     │  HEARTBEAT   │                       │  │
│  │  └──────┬───────┘     └──────┬───────┘                      │  │
│  │         │                    │                               │  │
│  │         ▼                    ▼                               │  │
│  │  ┌─────────────┐     ┌──────────────┐                       │  │
│  │  │ Update DB:  │     │ Log only:    │                       │  │
│  │  │ last_seen   │     │ "Ignoring    │                       │  │
│  │  │ = NOW()     │     │ heartbeat"   │                       │  │
│  │  │             │     │              │                       │  │
│  │  │ Update      │     │ No DB update │                       │  │
│  │  │ in-memory   │     │ No state     │                       │  │
│  │  │ state       │     │ update       │                       │  │
│  │  └─────────────┘     └──────────────┘                       │  │
│  │                                                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Database Layer                            │  │
│  │                                                              │  │
│  │  orchestrator_instances:                                     │  │
│  │  ┌────────────────┬─────────────┬──────────────────┐        │  │
│  │  │ orchestrator_id│is_independent│    last_seen     │        │  │
│  │  ├────────────────┼─────────────┼──────────────────┤        │  │
│  │  │ orch-001       │   FALSE     │ 2025-10-27 10:30 │ ◄──┐   │  │
│  │  │ orch-002       │   TRUE      │ 2025-10-27 09:00 │    │   │  │
│  │  │                │             │ (stale)          │    │   │  │
│  │  └────────────────┴─────────────┴──────────────────┘    │   │  │
│  │                                                          │   │  │
│  │  Note: orch-002's last_seen is stale because           │   │  │
│  │        independence mode is enabled                     │   │  │
│  └──────────────────────────────────────────────────────────│───┘  │
│                                                             │      │
└─────────────────────────────────────────────────────────────┼──────┘
                                                              │
                                                              │
                    ┌─────────────────────────────────────────┘
                    │ Only orch-001 updates
                    │ (is_independent = FALSE)
                    │
          ┌─────────▼──────────┐         ┌──────────────────┐
          │  Orchestrator-001  │         │ Orchestrator-002 │
          │   (Managed Mode)   │         │ (Independent)    │
          │                    │         │                  │
          │  Heartbeat → ✓     │         │ Heartbeat → ✗    │
          │  Monitored         │         │ Autonomous       │
          │  last_seen updates │         │ last_seen frozen │
          └────────────────────┘         └──────────────────┘
```

#### 7.3 Implementation Details

**Database Schema**:

Two tables store the independence flag:

1. **orchestrator_instances.is_independent** (boolean, default: false)

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Per-orchestrator flag
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Takes precedence over organization-level setting
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Directly controls heartbeat processing

2. **organizations.is_independent** (boolean, default: false)

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Organization-level flag
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Can be inherited by all orchestrators in the organization
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Useful for bulk independence management

**State Transitions**:

```
┌──────────────┐                                    ┌──────────────┐
│              │  Admin toggles independence ON     │              │
│   MANAGED    │ ──────────────────────────────────>│ INDEPENDENT  │
│    MODE      │                                    │     MODE     │
│              │                                    │              │
│ • Heartbeats │                                    │ • Heartbeats │
│   processed  │                                    │   ignored    │
│ • last_seen  │                                    │ • last_seen  │
│   updated    │                                    │   frozen     │
│ • Status:    │                                    │ • Status:    │
│   "Active"   │                                    │   "Independent"│
│              │  Admin toggles independence OFF    │              │
│              │ <──────────────────────────────────│              │
└──────────────┘                                    └──────────────┘
```

**Toggle Mechanism Flow**:

```
1. Admin Action (UI)
   └─> Click toggle switch in Organizations page

2. Frontend Request
   └─> PUT /api/v1/internal/orchestrators/{id}/independence
       Body: {"is_independent": true}

3. Controller Processing
   ├─> Validate request
   ├─> Update database:
   │   UPDATE orchestrator_instances 
   │   SET is_independent = true 
   │   WHERE orchestrator_id = ?
   │
   ├─> Persist to configuration files:
   │   ├─> /app/controller/app/.env
   │   │   ORCHESTRATOR_ORCH_001_INDEPENDENT=true
   │   │
   │   └─> /app/controller/app/db/orchestrator_independence.json
   │       {"orch-001": {"is_independent": true}}
   │
   └─> Return success response

4. Immediate Effect
   └─> Next heartbeat from orchestrator is ignored
```

**Configuration Persistence**:

Independence settings are persisted in three locations to ensure durability:

1. **PostgreSQL Database** (primary source of truth)

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - `orchestrator_instances.is_independent` column
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Queried on every heartbeat

2. **Environment File** (`/app/controller/app/.env`)

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Format: `ORCHESTRATOR_{ID}_INDEPENDENT=true`
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Loaded on controller startup
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Used to restore state after container restart

3. **JSON Configuration** (`/app/controller/app/db/orchestrator_independence.json`)

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Format: `{"orch-001": {"is_independent": true}}`
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Backup configuration store
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Human-readable for manual inspection

**Why Three Locations?**

- Database: Real-time operational state
- .env: Environment-based configuration (Docker best practice)
- JSON: Portable, version-controllable configuration

#### 7.4 Behavioral Differences

**Normal (Managed) Mode vs Independence Mode**:

| Aspect | Managed Mode | Independence Mode |

|--------|--------------|-------------------|

| **Heartbeat Processing** | ✓ Processed | ✗ Ignored |

| **Database Updates** | ✓ last_seen updated | ✗ No updates |

| **In-Memory State** | ✓ Updated | ✗ Not updated |

| **UI Status Display** | "Active" / "Inactive" | "Independent" |

| **Last Seen Timestamp** | Current (updates every 30s) | Frozen (last value before independence) |

| **WebSocket Connection** | ✓ Maintained | ✓ Maintained (but ignored) |

| **Configuration Push** | ✓ Receives updates | ✓ Receives updates (still works) |

| **Message Routing** | ✓ Enabled | ✓ Enabled (still works) |

| **Controller Dependency** | High (requires active controller) | Low (operates autonomously) |

**Key Insight**: The WebSocket connection remains open in both modes. Independence mode only affects heartbeat processing, not the connection itself. This means:

- Configuration updates can still be pushed to independent orchestrators
- Messages can still be routed
- The orchestrator can voluntarily send data to the controller
- Only the controller's monitoring/tracking is disabled

#### 7.5 User Experience & UI Behavior

**Dashboard View**:

```
┌────────────────────────────────────────────────────────────┐
│  Organizations                                             │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ Default Orchestrator (org-001)                       │ │
│  │                                                      │ │
│  │ Orchestrator: orch-001                              │ │
│  │ Status: Active                    [Toggle: OFF]     │ │
│  │ Last Seen: 2 seconds ago                            │ │
│  │ Independence: Disabled                              │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ Production Orchestrator (org-002)                    │ │
│  │                                                      │ │
│  │ Orchestrator: orch-002                              │ │
│  │ Status: Independent               [Toggle: ON]      │ │
│  │ Last Seen: 2 hours ago (frozen)                     │ │
│  │ Independence: Enabled                               │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**Toggle Interaction Flow**:

```
User Action                Controller Response              UI Update
─────────────────────────────────────────────────────────────────────

1. Click Toggle ON
   │
   ├──> PUT /independence      ──> Update DB
   │    {is_independent: true}     is_independent = true
   │                                │
   │                                ├──> Write to .env
   │                                │
   │                                └──> Write to JSON
   │
   └──> Response: Success      ──> Toggle switches to ON
                                   Status changes to "Independent"
                                   Last Seen stops updating

2. Wait 30 seconds...
   │
   ├──> Heartbeat arrives      ──> Controller logs:
   │                                "Ignoring heartbeat from 
   │                                 independent orchestrator"
   │
   └──> No DB update           ──> Last Seen remains frozen
                                   UI shows stale timestamp

3. Click Toggle OFF
   │
   ├──> PUT /independence      ──> Update DB
   │    {is_independent: false}    is_independent = false
   │                                │
   │                                ├──> Update .env
   │                                │
   │                                └──> Update JSON
   │
   └──> Response: Success      ──> Toggle switches to OFF
                                   Status changes to "Active"

4. Wait 30 seconds...
   │
   ├──> Heartbeat arrives      ──> Controller logs:
   │                                "Processing heartbeat from 
   │                                 orchestrator orch-001"
   │                                │
   │                                └──> UPDATE last_seen = NOW()
   │
   └──> DB updated             ──> Last Seen updates to current time
                                   UI shows "2 seconds ago"
```

#### 7.6 Logging & Observability

**Controller Logs (Normal Mode)**:

```
[2025-10-27 10:30:15] INFO: [C-OCS] Processing heartbeat from orchestrator orch-001
[2025-10-27 10:30:15] DEBUG: Updating last_seen for orch-001 in database
[2025-10-27 10:30:15] DEBUG: Updating in-memory state for orch-001
```

**Controller Logs (Independence Mode)**:

```
[2025-10-27 10:30:15] INFO: [C-OCS] Ignoring heartbeat from independent orchestrator orch-002
[2025-10-27 10:30:15] DEBUG: Skipping database update for independent orchestrator
```

**How to Monitor Independence Mode**:

1. **Check Controller Logs**:
   ```bash
   docker-compose logs controller -f | grep -E "Processing|Ignoring"
   ```

2. **Query Database**:
   ```sql
   SELECT orchestrator_id, is_independent, last_seen 
   FROM orchestrator_instances;
   ```

3. **Check UI Dashboard**:

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Navigate to Organizations page
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Look for "Independent" status badge
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                - Check toggle switch position

4. **Check Configuration Files**:
   ```bash
   # Check .env file
   cat /app/controller/app/.env | grep INDEPENDENT
   
   # Check JSON config
   cat /app/controller/app/db/orchestrator_independence.json
   ```


#### 7.7 Operational Scenarios

**Scenario 1: Controller Downtime**

```
Before Controller Goes Down:
- orch-001: Managed mode (is_independent = false)
- orch-002: Independent mode (is_independent = true)

Controller Goes Offline:
- orch-001: Loses heartbeat acknowledgment, may show errors
- orch-002: Continues operating normally (already autonomous)

Impact:
- orch-001: Operational impact (depends on orchestrator's resilience)
- orch-002: No impact (designed for this scenario)

Recommendation: Enable independence mode for production orchestrators
```

**Scenario 2: Gradual Migration to Independence**

```
Step 1: Deploy orchestrator in managed mode
        └─> Monitor stability, verify functionality

Step 2: Test independence mode in staging
        └─> Toggle ON, verify orchestrator continues working

Step 3: Enable independence in production
        └─> Toggle ON, monitor for 24-48 hours

Step 4: Confirm autonomous operation
        └─> Orchestrator operates without controller dependency
```

**Scenario 3: Debugging Independent Orchestrator**

```
Problem: Independent orchestrator not responding

Step 1: Temporarily disable independence
        └─> Toggle OFF in UI

Step 2: Wait for heartbeat processing to resume
        └─> Check logs for "Processing heartbeat"

Step 3: Verify last_seen updates
        └─> Check database or UI for current timestamp

Step 4: Investigate orchestrator health
        └─> Use controller's monitoring data

Step 5: Re-enable independence when resolved
        └─> Toggle ON in UI
```

#### 7.8 Best Practices

**When to Enable Independence Mode**:

✓ **DO Enable For**:

- Production orchestrators with high uptime requirements
- Orchestrators in remote/edge locations
- Mission-critical instances that cannot tolerate controller downtime
- Orchestrators that have proven stability over time

✗ **DON'T Enable For**:

- New orchestrators still being tested
- Development/staging environments where monitoring is valuable
- Orchestrators with known stability issues
- Instances requiring active health monitoring

**Configuration Recommendations**:

1. **Start Managed**: Deploy all new orchestrators in managed mode first
2. **Monitor First**: Observe orchestrator behavior for at least 1 week
3. **Gradual Rollout**: Enable independence for one orchestrator at a time
4. **Document State**: Keep a record of which orchestrators are independent and why
5. **Regular Reviews**: Periodically review independence settings (quarterly)

**Monitoring Strategy**:

- Set up alerts for independent orchestrators using external monitoring
- Don't rely solely on controller for independent orchestrator health
- Use application-level health checks (not just heartbeats)
- Consider implementing orchestrator-to-monitoring-system direct reporting

### 8. Deployment Architecture

#### 8.1 Docker Compose Services

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
- Volumes: `controller_config.json` for configuration persistence

**frontend**:

- Build: `Dockerfile.frontend`
- Port: 80 (HTTP)
- Depends on: controller
- Nginx configuration: Serve React build, proxy `/api/*` to controller

**Network**:

- All services on `moolai-network` bridge network
- Internal DNS resolution (services can reference each other by name)

#### 8.2 Environment Configuration

**Controller Environment Variables**:

- `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_NAME`
- `CONTROLLER_HOST`, `CONTROLLER_PORT`
- `DEV_BEARER_TOKEN`: Authentication token
- `HEARTBEAT_TTL_SEC`: How long before orchestrator considered inactive
- `HEARTBEAT_POKER_ENABLED`: Disabled (set to `false`)

**Frontend Environment Variables**:

- `VITE_CONTROLLER_BASE_URL`: Empty string (uses relative URLs)

#### 8.3 Deployment Flow

1. **Build Images**: `docker-compose build`
2. **Start Services**: `docker-compose up -d`
3. **Database Init**: Postgres creates schema on first run
4. **Controller Startup**: Initializes database connection, starts WebSocket server
5. **Frontend Startup**: Nginx serves React app, proxies API calls
6. **Health Checks**: Services report healthy status
7. **Ready**: System accepts orchestrator connections and UI traffic

### 9. Data Flow Scenarios

#### 9.1 Orchestrator Registration Flow

```
1. Orchestrator starts ws_client
2. ws_client connects to ws://controller:8765/ws
3. ws_client sends: {"type": "register", "orchestrator_id": "orch-001", ...}
4. Controller receives message
5. Controller queries database for existing record
6. Controller updates/inserts orchestrator_instances record
7. Controller updates in-memory state
8. Controller sends: {"type": "handshake_ack", "success": true}
9. Controller sends: {"type": "provisioning", "config": {...}}
10. Orchestrator receives config and applies it
11. Orchestrator starts heartbeat loop
```

#### 9.2 Heartbeat Processing Flow (Normal Mode)

```
1. Orchestrator sends: {"type": "i_am_alive", "orchestrator_id": "orch-001"}
2. Controller receives message
3. Controller queries: SELECT is_independent FROM orchestrator_instances WHERE orchestrator_id = 'orch-001'
4. Result: is_independent = false
5. Controller logs: "Processing heartbeat from orchestrator orch-001"
6. Controller updates: UPDATE orchestrator_instances SET last_seen = NOW() WHERE orchestrator_id = 'orch-001'
7. Controller updates in-memory state: mark_keepalive("orch-001")
8. Controller continues listening
```

#### 9.3 Heartbeat Processing Flow (Independence Mode)

```
1. Orchestrator sends: {"type": "i_am_alive", "orchestrator_id": "orch-001"}
2. Controller receives message
3. Controller queries: SELECT is_independent FROM orchestrator_instances WHERE orchestrator_id = 'orch-001'
4. Result: is_independent = true
5. Controller logs: "Ignoring heartbeat from independent orchestrator orch-001"
6. Controller skips database update
7. Controller skips in-memory state update
8. Controller continues listening (connection stays open)
```

#### 9.4 Independence Toggle Flow

```
1. Admin opens UI, navigates to Organizations page
2. Admin clicks toggle switch for "orch-001"
3. Frontend sends: PUT /api/v1/internal/orchestrators/orch-001/independence {"is_independent": true}
4. Controller receives request
5. Controller updates database: UPDATE orchestrator_instances SET is_independent = true WHERE orchestrator_id = 'orch-001'
6. Controller writes to /app/controller/app/.env: ORCHESTRATOR_ORCH_001_INDEPENDENT=true
7. Controller writes to /app/controller/app/db/orchestrator_independence.json
8. Controller responds: {"success": true, "message": "Independence mode updated"}
9. Frontend updates UI to show "Independent" status
10. Next heartbeat from orch-001 is ignored
```

#### 9.5 Dashboard Data Loading Flow

```
1. User opens dashboard in browser
2. React app loads, runs useEffect hook
3. Frontend makes parallel API calls:
   - GET /api/v1/controller/overview
   - GET /api/v1/controller/costs
   - GET /api/v1/controller/orchestrators?page_size=100
   - GET /api/v1/controller/organizations?page_size=5
   - GET /api/v1/controller/health
4. Nginx receives requests, proxies to controller backend
5. Controller queries database for each endpoint
6. Controller returns JSON responses
7. Frontend receives data, updates React state
8. UI renders with live data
9. Frontend polls /api/v1/controller/orchestrators/live every 2s for real-time updates
```

### 10. File Structure & Key Files

```
controller/
├── app/
│   ├── main.py                          # FastAPI app, WebSocket handler, startup/shutdown
│   ├── settings.py                      # Environment variable loading
│   ├── controller_config.py             # JSON config file management
│   │
│   ├── api/
│   │   └── v1/
│   │       ├── controller.py            # Public REST API endpoints
│   │       └── internal.py              # Internal management API
│   │
│   ├── db/
│   │   ├── database.py                  # PostgreSQL connection management
│   │   └── controller_config.json       # Organization/orchestrator configuration
│   │
│   ├── models/
│   │   ├── organization.py              # Organization & OrchestratorInstance ORM models
│   │   ├── orchestrator.py              # OrchestratorMessage ORM model
│   │   └── user.py                      # User ORM model (future use)
│   │
│   ├── utils/
│   │   ├── controller_state.py          # In-memory connection state management
│   │   ├── buffer_manager.py            # Activity logging buffer
│   │   ├── dispatch.py                  # Message routing logic
│   │   └── provisioning.py              # Configuration push to orchestrators
│   │
│   └── gui/
│       └── frontend/                    # React + Vite frontend
│           ├── src/
│           │   ├── pages/
│           │   │   ├── dashboard/       # Dashboard page
│           │   │   ├── organizations/   # Organizations management
│           │   │   └── configuration/   # System configuration
│           │   └── lib/
│           │       └── api.ts           # Axios API client
│           └── dist/                    # Production build (served by Nginx)
│
├── docker-compose.yml                   # Multi-service orchestration
├── Dockerfile.controller                # Controller backend image
└── Dockerfile.frontend                  # Frontend + Nginx image
```

### 11. Legacy Components (Not in Use)

**Note**: The following files exist in the codebase but are NOT actively used in the current deployment:

- `controller/app/ws_server.py`: Legacy standalone WebSocket server (replaced by integrated handler in main.py)
- `controller/app/api/routes_orgs.py`: Old organization routes (replaced by v1/controller.py)
- `controller/app/api/routes_users.py`: Old user routes (not currently used)
- `controller/app/api/routes_analytics.py`: Old analytics routes (not currently used)

These files are kept for reference but should not be documented as active components.

### 12. Operational Considerations

#### 12.1 Monitoring & Observability

- Health check endpoints for service monitoring
- Activity buffer for debugging
- Database query logging (can be enabled)
- WebSocket connection tracking

#### 12.2 Scalability Considerations

- In-memory state limits horizontal scaling (single instance)
- Database can handle multiple controller instances with shared state
- WebSocket connections are stateful (sticky sessions needed for load balancing)
- Consider Redis for shared state in multi-instance deployment

#### 12.3 Security

- Bearer token authentication for API access
- Environment variable-based secrets (not hardcoded)
- CORS configured for frontend domain
- Database credentials isolated in environment
- No public exposure of internal API endpoints (should be firewalled)

#### 12.4 Reliability

- Database health checks before startup
- Connection pooling for database resilience
- WebSocket reconnection logic in orchestrator client
- Independence mode for orchestrator autonomy
- Docker restart policies (unless-stopped)

### 13. Future Enhancements

**Potential improvements not yet implemented**:

- Redis for shared state (multi-instance support)
- Message queue (RabbitMQ/Kafka) for async message delivery
- Metrics export (Prometheus)
- Distributed tracing (OpenTelemetry)
- Role-based access control (RBAC)
- Orchestrator auto-provisioning (Docker API integration)
- Cost tracking integration (cloud provider APIs)
- Alert system for orchestrator failures

---

## Implementation Files Reference

### Core Backend Files

- `controller/app/main.py` - FastAPI application and WebSocket handler
- `controller/app/api/v1/controller.py` - Public REST API
- `controller/app/api/v1/internal.py` - Internal management API
- `controller/app/db/database.py` - Database connection manager
- `controller/app/models/organization.py` - ORM models for organizations and orchestrators
- `controller/app/utils/controller_state.py` - In-memory state management
- `controller/app/controller_config.py` - Configuration file management

### Frontend Files

- `controller/app/gui/frontend/src/pages/dashboard/dashboard.tsx` - Dashboard page
- `controller/app/gui/frontend/src/pages/dashboard/organizations.tsx` - Organizations page
- `controller/app/gui/frontend/src/pages/dashboard/configuration.tsx` - Configuration page
- `controller/app/gui/frontend/src/lib/api.ts` - API client

### Deployment Files

- `docker-compose.yml` - Service orchestration
- `Dockerfile.controller` - Controller backend image
- `Dockerfile.frontend` - Frontend + Nginx image

---

## Conclusion

The Moolai Controller provides a centralized management platform for orchestrator instances with real-time monitoring, independence mode for autonomous operation, and a modern web interface. The architecture prioritizes simplicity, reliability, and ease of deployment while maintaining flexibility for future enhancements.

### To-dos

- [ ] Review HLD document structure with technical lead
- [ ] Replace existing HLD.md with new comprehensive document
- [ ] Enhance with additional architecture diagrams if needed
- [ ] Prepare demo walkthrough based on HLD sections