# Demo Guide - Moolai Controller Service

## 🎯 **Quick Start Commands**

### **1. Start the Orchestrator Client (Local Machine)**

Open a terminal and run:
```bash
cd /Users/michelleprabhu/Desktop/mooli_orchestrator_package && \
export ORCHESTRATOR_ID=orch-001 && \
export CONTROLLER_WS_URL=ws://4.155.149.35/ws && \
export HEARTBEAT_INTERVAL_SEC=30 && \
export ORCHESTRATOR_HTTP_ENABLED=false && \
python -m orchestrator.app.ws_client
```

**Expected Output:**
```
[O-CCS] booting ws_client…
[O-CCS] WS URL => ws://4.155.149.35/ws
[O-CCS] ORCHESTRATOR_ID => orch-001
[O-CCS] Connecting to ws://4.155.149.35/ws (attempt 1)
[O-CCS] handshake_ack received
[O-CCS] i_am_alive sent #1
[O-CCS] i_am_alive sent #2
[O-CCS] i_am_alive sent #3
...
```

---

### **2. Watch Controller Logs (Optional)**

Open another terminal to see controller activity:
```bash
ssh -i ~/Desktop/Controller_key.pem azureuser@4.155.149.35 "cd ~/moolai/mooli_orchestrator_package && sudo docker-compose logs controller -f --tail=20"
```

You should see:
```
[C-OCS] Processing heartbeat from orchestrator orch-001
[C-OCS] Processing heartbeat from orchestrator orch-001
...
```

---

### **3. Access the Dashboard**

Open your browser and go to:
```
http://4.155.149.35
```

**Login Credentials:**
- Username: `michelleprabhu`
- Password: `password123`

---

## 📊 **Demo Flow**

### **1. Overview Dashboard**
- **URL**: `http://4.155.149.35/dashboard`
- **Shows**: Total orchestrators, active count, organizations
- **Status Badges**:
  - 🟢 "active (heartbeat)" - Normal operation
  - 🔴 "independent" - Autonomous mode
  - ⚪ "inactive" - No recent heartbeats

---

### **2. Organizations Page**
- **URL**: `http://4.155.149.35/organizations`
- **Shows**: List of all organizations
- **Actions**: Click on organization to view details

---

### **3. Organization Details Page**
- **URL**: `http://4.155.149.35/organization-details`
- **Features**:
  - **Independence Toggle**: Switch orchestrators between monitored and independent mode
  - **Status Display**: Shows current orchestrator health
  - **Messages**: Display recommendations and monitoring alerts (when NOT independent)

---

### **4. Independence Mode Demo**

#### **Toggle Independence ON:**
1. Go to Organization Details
2. Find the "Independent Operation" toggle
3. **Switch it ON**
4. Watch the status badge change to "Independent" (red)
5. Check logs - you should see:
   ```
   [C-OCS] Ignoring heartbeat from independent orchestrator orch-001
   ```
6. Note: Messages are now hidden (independence mode active)

#### **Toggle Independence OFF:**
1. Switch the toggle back OFF
2. Wait 30 seconds (next heartbeat)
3. Watch the status badge change to "Active"
4. Check logs - you should see:
   ```
   [C-OCS] Processing heartbeat from orchestrator orch-001
   ```
5. Note: Messages are now visible again

---

### **5. Send Test Messages**

Open a terminal and run:

```bash
# Send a recommendation message
ssh -i ~/Desktop/Controller_key.pem azureuser@4.155.149.35 'curl -X POST http://localhost:8765/api/v1/internal/orchestrators/orch-001/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer fake-dev-token" \
  -d "{
    \"message_type\": \"recommendation\",
    \"content\": \"We recommend enabling cache to improve performance by 40%.\"
  }"'
```

```bash
# Send a monitoring message
ssh -i ~/Desktop/Controller_key.pem azureuser@4.155.149.35 'curl -X POST http://localhost:8765/api/v1/internal/orchestrators/orch-001/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer fake-dev-token" \
  -d "{
    \"message_type\": \"monitoring\",
    \"content\": \"High memory usage detected (85%). Consider scaling up.\"
  }"'
```

Then refresh the Organization Details page to see the messages.

---

## 🎬 **Full Demo Script**

### **Opening (30 seconds)**
1. Pull up the dashboard in browser
2. Show overview with 1 active orchestrator
3. "We have the Moolai Controller Service running on Azure VM, monitoring orchestrator instances in real-time."

### **Independence Mode (2 minutes)**
1. Navigate to Organization Details
2. "Here's our orchestrator 'Default Orchestrator' in active mode."
3. **Toggle independence ON**
4. "Now watch what happens when we switch to independence mode..."
5. Show status changes to "Independent"
6. Show logs with "Ignoring heartbeat"
7. "The orchestrator still sends heartbeats, but the controller ignores them because it's marked as independent."
8. **Toggle independence OFF**
9. "And when we switch it off, the controller resumes processing heartbeats."

### **Messages System (1 minute)**
1. "Let me send a recommendation message..."
2. Run the curl command to send a message
3. Refresh the page
4. "Now we see the recommendation in the UI."
5. "This is only shown when the orchestrator is NOT independent."
6. Show accept/dismiss functionality

### **Configuration Page (30 seconds)**
1. Navigate to Configuration
2. "Here we can see the system health - controller is up, database is up, WebSocket is operational."
3. "The controller is tracking 1 active orchestrator."

### **Conclusion (30 seconds)**
1. "The system supports multiple orchestrators running independently or under controller supervision."
2. "We have independence mode, message routing, and real-time status tracking all working together."

**Total Demo Time: ~4 minutes**

---

## 🔧 **Troubleshooting**

### **Issue: No heartbeats showing in logs**
- **Check**: Is the orchestrator client running?
- **Fix**: Restart the orchestrator client

### **Issue: "Failed to connect"**
- **Check**: Is controller running on VM?
- **Fix**: `ssh ... && sudo docker-compose ps` - check container status

### **Issue: Login not working**
- **Check**: Credentials: `michelleprabhu` / `password123`
- **Fix**: Hard refresh browser (Cmd+Shift+R)

### **Issue: Independence toggle not working**
- **Check**: Look for errors in browser console
- **Fix**: Check controller logs for database errors

---

## 📝 **Talking Points**

### **For Your Manager:**

**Opening:**
> "I've implemented a complete controller service for managing Moolai orchestrators. It's deployed on Azure and provides real-time monitoring, independence mode, and message routing capabilities."

**Architecture:**
> "The system consists of three main components - a PostgreSQL database for persistence, a FastAPI backend handling WebSocket connections and REST APIs, and a React frontend served by Nginx. Everything is containerized with Docker Compose."

**Independence Mode:**
> "One of the key features is independence mode. This allows orchestrators to operate autonomously without controller supervision. When toggled on, the controller ignores heartbeats from that orchestrator. This is useful for situations where an orchestrator needs to operate independently."

**Real-time Updates:**
> "The system uses WebSocket connections for real-time bidirectional communication. Orchestrators send heartbeats every 30 seconds, and the controller updates the database and UI in real-time."

**Message System:**
> "We also support recommendation and monitoring messages from orchestrators. These are displayed in the UI with accept/dismiss functionality, but only when the orchestrator is not in independence mode."

**Closing:**
> "The entire system is production-ready, deployed on Azure, and documented with a comprehensive HLD document. All features are working as expected with proper error handling and monitoring."

---

## 📂 **Files to Reference**

- **HLD Document**: `HLD.md` - Complete high-level design
- **Dashboard**: `controller/app/gui/frontend/src/pages/dashboard/dashboard.tsx`
- **Independence Toggle**: `controller/app/gui/frontend/src/pages/dashboard/organizations-detail.tsx`
- **WebSocket Handler**: `controller/app/main.py` (lines 285-650)
- **Database**: `controller/app/db/database.py`

Good luck with your demo! 🚀

