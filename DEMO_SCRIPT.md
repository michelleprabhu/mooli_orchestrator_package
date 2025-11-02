# Moolai Controller - Demo Script
**Complete Walkthrough with Talking Points**

---

## 🎯 Introduction (30 seconds)

**"Hello everyone! Today I'll be demonstrating the Moolai Controller - a centralized management platform for orchestrator instances. The controller provides real-time monitoring, configuration management, and enables organizations to run orchestrators either in supervised mode or independently. Let me walk you through the key features."**

---

## 📋 Part 1: System Architecture Overview (1 minute)

**"The Moolai Controller is built on a modern tech stack:"**

- **Backend:** FastAPI with Python, providing both REST APIs and WebSocket support
- **Frontend:** React dashboard with real-time updates
- **Database:** PostgreSQL for persistent storage of organizations and orchestrator metadata
- **Communication:** WebSocket protocol for real-time bidirectional communication between controller and orchestrators
- **Deployment:** Fully containerized with Docker Compose

**"The system has three main components:"**
1. **Controller Service** - The central hub running on Azure VM
2. **Orchestrator Clients** - Individual instances that connect to the controller
3. **PostgreSQL Database** - Stores all organizational data, orchestrator metadata, and messages

---

## 🔌 Part 2: WebSocket Connection & Heartbeat Mechanism (2 minutes)

**"Let's start by understanding how orchestrators connect to the controller. I'll start an orchestrator client for organization org-002."**

### Step 1: Start Orchestrator Client

```bash
# First, clean any cached config
rm -f /Users/michelleprabhu/Desktop/mooli_orchestrator_package/orchestrator/app/db/orchestrator_config.json

# Start the orchestrator client
cd /Users/michelleprabhu/Desktop/mooli_orchestrator_package && \
export ORCHESTRATOR_ID=org-002 && \
export CONTROLLER_WS_URL=ws://4.155.149.35/ws && \
export HEARTBEAT_INTERVAL_SEC=30 && \
export ORCHESTRATOR_HTTP_ENABLED=false && \
python -m orchestrator.app.ws_client &
```

**"Notice the output - let me explain what just happened:"**

1. **`[O-CCS] booting ws_client…`** - The orchestrator client is initializing
2. **`[O-CCS] WS URL => ws://4.155.149.35/ws`** - Connecting to the controller's WebSocket endpoint
3. **`[O-CCS] ORCHESTRATOR_ID => org-002`** - This client represents organization org-002
4. **`[O-CCS] Connecting to ws://4.155.149.35/ws (attempt 1)`** - Establishing WebSocket connection
5. **`[O-CCS] handshake_ack received`** - Controller acknowledged the connection
6. **`[O-CCS] i_am_alive sent #1`** - First heartbeat sent

**"The orchestrator sends a heartbeat every 30 seconds to let the controller know it's still alive and operational."**

---

### Step 2: Watch Controller Logs

```bash
ssh -i ~/Desktop/Controller_key.pem azureuser@4.155.149.35 "cd ~/moolai/mooli_orchestrator_package && sudo docker-compose logs controller -f --tail=30 | grep -E 'org-002|connected|Processing heartbeat'"
```

**"In the controller logs, you'll see:"**

- **`[C-OCS] WebSocket connection accepted`** - Controller accepts the incoming connection
- **`[C-OCS] DB: Registered org-002 in both tables`** - Orchestrator is registered in both `organizations` and `orchestrator_instances` tables
- **`[C-OCS] Orchestrator org-002 connected`** - Handshake complete
- **`[C-OCS] handshake_ack sent to org-002`** - Acknowledgment sent back
- **`[C-OCS] Processing heartbeat from orchestrator org-002`** - Heartbeats are being processed every 30 seconds

**"Each heartbeat updates the `last_seen` timestamp in the database, so we always know the last time an orchestrator checked in."**

---

## 💾 Part 3: Database State (2 minutes)

**"Let's look at what's stored in the database. We have two main tables: `organizations` and `orchestrator_instances`."**

### Check Organizations Table

```bash
ssh -i ~/Desktop/Controller_key.pem azureuser@4.155.149.35 "cd ~/moolai/mooli_orchestrator_package && sudo docker exec moolai-postgres psql -U moolai -d moolai_controller -c 'SELECT organization_id, name, status, is_independent, last_seen FROM organizations ORDER BY created_at DESC;'"
```

**"The organizations table shows:"**
- **`organization_id`** - Unique identifier (e.g., org-002)
- **`name`** - Human-readable name (e.g., "Michelle Organisation")
- **`status`** - Current status (active/inactive)
- **`is_independent`** - Whether this organization is running in independence mode
- **`last_seen`** - Last activity timestamp

### Check Orchestrator Instances Table

```bash
ssh -i ~/Desktop/Controller_key.pem azureuser@4.155.149.35 "cd ~/moolai/mooli_orchestrator_package && sudo docker exec moolai-postgres psql -U moolai -d moolai_controller -c 'SELECT orchestrator_id, organization_id, status, health_status, is_independent, last_seen FROM orchestrator_instances ORDER BY last_seen DESC NULLS LAST;'"
```

**"The orchestrator_instances table tracks:"**
- **`orchestrator_id`** - Links to the organization
- **`status`** - active (connected and sending heartbeats) or inactive (not connected)
- **`health_status`** - healthy, degraded, or unhealthy based on metrics
- **`is_independent`** - Independence mode flag
- **`last_seen`** - Updated with every heartbeat (every 30 seconds)

**"Notice how org-002 shows as 'active' with a recent `last_seen` timestamp - this proves the heartbeat mechanism is working."**

---

## 🖥️ Part 4: Frontend Dashboard (2 minutes)

**"Now let's look at the web dashboard. Open your browser and go to http://4.155.149.35/organizations"**

### Organizations Page

**"On this page, you can see:"**

1. **Organization Cards** - Each organization is displayed with:
   - Organization ID and name
   - Status badge (active = green, inactive = gray, independent = red)
   - Number of registered orchestrators
   - Live status indicator

2. **Expand Details** - Click the chevron to see:
   - Registered orchestrator instances
   - Current features (cache, firewall status)
   - Health metrics
   - Independence mode toggle switch

3. **Add New Organization** - Click the "Add New Organization" button to create a new org through the UI

**"The dashboard auto-refreshes every 10 seconds, so status changes appear in near real-time."**

---

## 🎛️ Part 5: Independence Mode Feature (3 minutes)

**"One of our key features is Independence Mode. This allows orchestrators to operate autonomously without controller supervision."**

### What is Independence Mode?

**"When an orchestrator is set to independent:"**
- ✅ It continues to send heartbeats to the controller
- ✅ The controller receives and acknowledges them
- ❌ **BUT** the controller does NOT process or store them
- ✅ The orchestrator operates completely autonomously
- ✅ The controller marks it with a special 'independent' badge

**"This is useful for:"**
- Organizations that need complete autonomy
- Testing scenarios where you don't want controller interference
- Compliance requirements where data must stay isolated

### Toggle Independence Mode

**"I'll toggle independence mode for org-002 right now."**

#### Option 1: Via UI
- Open http://4.155.149.35/organizations
- Expand the org-002 card
- Find the "Independence Mode" toggle
- Click it to enable

#### Option 2: Via API
```bash
# Enable independence
curl -X PUT http://4.155.149.35/api/v1/internal/orchestrators/org-002/independence \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer fake-dev-token" \
  -d '{
    "is_independent": true,
    "privacy_mode": false
  }'
```

### Watch the Logs Change

```bash
ssh -i ~/Desktop/Controller_key.pem azureuser@4.155.149.35 "cd ~/moolai/mooli_orchestrator_package && sudo docker-compose logs controller -f --tail=20 | grep -E 'org-002|Ignoring|Processing'"
```

**"Before toggling, you saw:**
- `[C-OCS] Processing heartbeat from orchestrator org-002`

**"After toggling independence ON, you'll see:**
- `[C-OCS] Ignoring heartbeat from independent orchestrator org-002`

**"The heartbeats still arrive every 30 seconds, but the controller intentionally ignores them. The database `last_seen` timestamp is frozen at the moment independence was enabled."**

### Toggle Back to Managed Mode

```bash
# Disable independence
curl -X PUT http://4.155.149.35/api/v1/internal/orchestrators/org-002/independence \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer fake-dev-token" \
  -d '{
    "is_independent": false,
    "privacy_mode": false
  }'
```

**"Once you toggle it back OFF, the controller immediately resumes processing heartbeats, and the `last_seen` timestamp starts updating again."**

---

## 📨 Part 6: Message System (2 minutes)

**"The controller supports a bidirectional message system for recommendations and monitoring alerts."**

### Send a Recommendation Message

```bash
curl -X POST http://4.155.149.35/api/v1/internal/orchestrators/org-002/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer fake-dev-token" \
  -d '{
    "message_type": "recommendation",
    "content": "Consider enabling caching to improve performance by 40%",
    "metadata": {
      "severity": "medium",
      "category": "performance",
      "estimated_impact": "40% faster response time"
    }
  }'
```

**"This creates a message that the orchestrator can retrieve and act upon."**

### Send a Monitoring Alert

```bash
curl -X POST http://4.155.149.35/api/v1/internal/orchestrators/org-002/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer fake-dev-token" \
  -d '{
    "message_type": "monitoring",
    "content": "High memory usage detected: 85% of available RAM in use",
    "metadata": {
      "severity": "high",
      "metric": "memory_usage",
      "current_value": "85%",
      "threshold": "80%"
    }
  }'
```

### Retrieve Messages

```bash
curl -X GET "http://4.155.149.35/api/v1/internal/orchestrators/org-002/messages" \
  -H "Authorization: Bearer fake-dev-token" | jq
```

**"Messages are stored in the `orchestrator_messages` table and can be queried by type (recommendation/monitoring) and status (pending/accepted/dismissed)."**

### Check in Database

```bash
ssh -i ~/Desktop/Controller_key.pem azureuser@4.155.149.35 "cd ~/moolai/mooli_orchestrator_package && sudo docker exec moolai-postgres psql -U moolai -d moolai_controller -c 'SELECT id, orchestrator_id, message_type, content, status, created_at FROM orchestrator_messages ORDER BY created_at DESC LIMIT 5;'"
```

---

## 🗂️ Part 7: In-Memory State & Buffers (1 minute)

**"In addition to database persistence, the controller maintains in-memory state for performance."**

### Controller State

**"The controller uses two in-memory managers:"**

1. **`controller_state.py`** - Tracks:
   - Active WebSocket connections
   - Last handshake time for each orchestrator
   - Last keepalive (heartbeat) time
   - Maps orchestrator IDs to their WebSocket objects

2. **`buffer_manager.py`** - Maintains activity logs:
   - Connection events (handshakes, disconnections)
   - Keepalive events (heartbeat received)
   - Configuration provisioning events
   - Message dispatch events

**"These are used for:"**
- Fast status checks (no database query needed)
- Real-time dashboard updates
- Debugging and operational visibility

**"The buffers are ephemeral - they reset when the controller restarts, but the database preserves all persistent state."**

---

## 🔄 Part 8: Configuration Provisioning (1 minute)

**"The controller can push configuration updates to orchestrators in real-time."**

### How It Works

**"When an orchestrator connects:"**
1. Handshake is completed
2. Controller sends an initial `provision_config` message
3. The message contains features, settings, and policies
4. Orchestrator applies the configuration immediately

**"You can also push config updates at any time via the internal API, and they'll be delivered through the WebSocket connection instantly."**

**"This enables centralized management of features like:"**
- Cache enabled/disabled
- Firewall rules
- Session timeouts
- Feature flags

---

## 📊 Part 9: Complete Data Flow (1 minute)

**"Let me summarize the complete data flow:"**

### Orchestrator Startup
1. **Orchestrator starts** → Reads environment variables (ORCHESTRATOR_ID, CONTROLLER_WS_URL)
2. **Creates config file** → Stores in `orchestrator/app/db/orchestrator_config.json`
3. **Opens WebSocket** → Connects to `ws://4.155.149.35/ws`
4. **Sends handshake** → Includes metadata (name, location, features, version)

### Controller Processing
1. **Accepts connection** → Validates handshake
2. **Registers in memory** → Updates `controller_state` with active connection
3. **Registers in database** → Inserts/updates both `organizations` and `orchestrator_instances` tables
4. **Sends acknowledgment** → `handshake_ack` back to orchestrator
5. **Sends initial config** → `provision_config` message

### Heartbeat Loop
1. **Every 30 seconds** → Orchestrator sends `i_am_alive` message
2. **Controller receives** → Checks `is_independent` flag in database
3. **If NOT independent** → Updates `last_seen` timestamp, marks as active
4. **If independent** → Logs "Ignoring heartbeat", no database update
5. **Buffer update** → Adds activity to in-memory buffer

### Frontend Updates
1. **Every 10 seconds** → Frontend polls `/api/v1/controller/orchestrators/live`
2. **Returns live orchestrators** → Based on in-memory state (WebSocket connections)
3. **UI updates** → Status badges change (green = active, gray = inactive, red = independent)

---

## 🛠️ Part 10: Creating Organizations (1 minute)

**"There are two ways to create organizations:"**

### Method 1: Via UI
1. Click "Add New Organization"
2. Enter:
   - Organization ID (e.g., `org-005`)
   - Name (e.g., `Demo Company`)
   - Location (e.g., `us-west-2`)
3. Click "Create"

**"This calls the `/api/v1/internal/orchestrators/register` endpoint."**

### Method 2: Via API

```bash
curl -X POST http://4.155.149.35/api/v1/internal/orchestrators/register \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer fake-dev-token" \
  -d '{
    "orchestrator_id": "org-005",
    "organization_id": "org-005",
    "name": "Demo Company",
    "location": "us-west-2"
  }'
```

**"Both methods create entries in both the `organizations` and `orchestrator_instances` tables."**

### What Gets Created

**"When you create an organization:"**
- ✅ Entry in `organizations` table (organization metadata)
- ✅ Entry in `orchestrator_instances` table (instance configuration)
- ✅ Status starts as `inactive` (no orchestrator connected yet)
- ✅ When an orchestrator with that ID connects, status changes to `active`

---

## 🧪 Part 11: Live Demo - Full Workflow (2 minutes)

**"Let me show you a complete workflow from start to finish."**

### Step 1: Create New Organization

```bash
curl -X POST http://4.155.149.35/api/v1/internal/orchestrators/register \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer fake-dev-token" \
  -d '{
    "orchestrator_id": "org-demo",
    "organization_id": "org-demo",
    "name": "Demo Organization",
    "location": "live-demo"
  }'
```

**"Organization created! Now it shows as inactive in the UI."**

### Step 2: Check Database

```bash
ssh -i ~/Desktop/Controller_key.pem azureuser@4.155.149.35 "cd ~/moolai/mooli_orchestrator_package && sudo docker exec moolai-postgres psql -U moolai -d moolai_controller -c 'SELECT orchestrator_id, status, last_seen FROM orchestrator_instances WHERE orchestrator_id = '\''org-demo'\'';'"
```

**"Status is `inactive`, `last_seen` is NULL."**

### Step 3: Start Orchestrator Client

```bash
# Clean config
rm -f /Users/michelleprabhu/Desktop/mooli_orchestrator_package/orchestrator/app/db/orchestrator_config.json

# Start client
cd /Users/michelleprabhu/Desktop/mooli_orchestrator_package && \
export ORCHESTRATOR_ID=org-demo && \
export CONTROLLER_WS_URL=ws://4.155.149.35/ws && \
export HEARTBEAT_INTERVAL_SEC=30 && \
export ORCHESTRATOR_HTTP_ENABLED=false && \
python -m orchestrator.app.ws_client &
```

**"Orchestrator connects, sends handshake, starts heartbeats."**

### Step 4: Watch Logs

```bash
ssh -i ~/Desktop/Controller_key.pem azureuser@4.155.149.35 "cd ~/moolai/mooli_orchestrator_package && sudo docker-compose logs controller --tail=20 | grep org-demo"
```

**"You'll see: `Orchestrator org-demo connected`, `Processing heartbeat from orchestrator org-demo`"**

### Step 5: Check Database Again

```bash
ssh -i ~/Desktop/Controller_key.pem azureuser@4.155.149.35 "cd ~/moolai/mooli_orchestrator_package && sudo docker exec moolai-postgres psql -U moolai -d moolai_controller -c 'SELECT orchestrator_id, status, last_seen FROM orchestrator_instances WHERE orchestrator_id = '\''org-demo'\'';'"
```

**"Now status is `active`, `last_seen` has a recent timestamp!"**

### Step 6: Refresh UI

**"Open http://4.155.149.35/organizations and you'll see org-demo with a green 'active' badge!"**

### Step 7: Toggle Independence

**"In the UI, expand org-demo and toggle independence mode ON."**

### Step 8: Watch Logs Change

```bash
ssh -i ~/Desktop/Controller_key.pem azureuser@4.155.149.35 "cd ~/moolai/mooli_orchestrator_package && sudo docker-compose logs controller -f --tail=10 | grep org-demo"
```

**"Now it says: `Ignoring heartbeat from independent orchestrator org-demo`"**

**"The orchestrator is still running, still sending heartbeats, but the controller is no longer processing them. That's independence mode in action!"**

---

## 🎬 Conclusion (30 seconds)

**"To summarize what we've demonstrated today:"**

1. ✅ **Real-time WebSocket communication** between controller and orchestrators
2. ✅ **Heartbeat mechanism** with 30-second intervals to track liveness
3. ✅ **Dual database storage** in `organizations` and `orchestrator_instances` tables
4. ✅ **In-memory state management** for fast status checks and activity logging
5. ✅ **Independence mode** allowing orchestrators to operate autonomously
6. ✅ **Message system** for recommendations and monitoring alerts
7. ✅ **React dashboard** with real-time updates every 10 seconds
8. ✅ **Complete API** for programmatic management

**"The Moolai Controller provides a robust, scalable platform for managing multiple orchestrator instances across different organizations, with flexibility to run them in supervised or independent mode as needed."**

**"Thank you! Any questions?"**

---

## 📝 Quick Reference Commands

### Start Orchestrator
```bash
rm -f /Users/michelleprabhu/Desktop/mooli_orchestrator_package/orchestrator/app/db/orchestrator_config.json && \
cd /Users/michelleprabhu/Desktop/mooli_orchestrator_package && \
export ORCHESTRATOR_ID=org-002 && \
export CONTROLLER_WS_URL=ws://4.155.149.35/ws && \
export HEARTBEAT_INTERVAL_SEC=30 && \
export ORCHESTRATOR_HTTP_ENABLED=false && \
python -m orchestrator.app.ws_client &
```

### Watch Controller Logs
```bash
ssh -i ~/Desktop/Controller_key.pem azureuser@4.155.149.35 "cd ~/moolai/mooli_orchestrator_package && sudo docker-compose logs controller -f --tail=30"
```

### Check Database
```bash
ssh -i ~/Desktop/Controller_key.pem azureuser@4.155.149.35 "cd ~/moolai/mooli_orchestrator_package && sudo docker exec moolai-postgres psql -U moolai -d moolai_controller -c 'SELECT orchestrator_id, status, is_independent, last_seen FROM orchestrator_instances ORDER BY last_seen DESC NULLS LAST;'"
```

### Toggle Independence
```bash
# Enable
curl -X PUT http://4.155.149.35/api/v1/internal/orchestrators/org-002/independence -H "Content-Type: application/json" -H "Authorization: Bearer fake-dev-token" -d '{"is_independent": true, "privacy_mode": false}'

# Disable
curl -X PUT http://4.155.149.35/api/v1/internal/orchestrators/org-002/independence -H "Content-Type: application/json" -H "Authorization: Bearer fake-dev-token" -d '{"is_independent": false, "privacy_mode": false}'
```

### Send Message
```bash
curl -X POST http://4.155.149.35/api/v1/internal/orchestrators/org-002/messages -H "Content-Type: application/json" -H "Authorization: Bearer fake-dev-token" -d '{"message_type":"recommendation","content":"Enable caching for better performance","metadata":{"severity":"medium"}}'
```

### Stop Orchestrator
```bash
ps aux | grep "python -m orchestrator.app.ws_client" | grep -v grep | awk '{print $2}' | xargs kill
```

---

**End of Demo Script** 🎉





