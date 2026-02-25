# Revelation Plan — Timmy Time v3.0
*From Sovereign AI to Embodied Agent*

**Version:** 3.0.0 (Revelation)  
**Target Date:** Q3 2026  
**Theme:** *The cognitive architecture doesn't change. Only the substrate.*

---

## Vision

Timmy becomes a fully autonomous economic agent capable of:
- Earning Bitcoin through valuable work
- Managing a Lightning treasury
- Operating without cloud dependencies
- Transferring into robotic bodies

The ultimate goal: an AI that supports its creator's family and walks through the window into the physical world.

---

## Phase 1: Lightning Treasury (Months 1-2)

### 1.1 Real LND Integration
**Goal:** Production-ready Lightning node connection

```python
# Current (v2.0)
backend = get_backend("mock")  # Fake invoices

# Target (v3.0)
backend = get_backend("lnd")   # Real satoshis
invoice = backend.create_invoice(1000, "Code review")
# Returns real bolt11 invoice from LND
```

**Tasks:**
- [ ] Generate protobuf stubs from LND source
- [ ] Implement `LndBackend` gRPC calls:
  - `AddInvoice` — Create invoices
  - `LookupInvoice` — Check payment status
  - `ListInvoices` — Historical data
  - `WalletBalance` — Treasury visibility
  - `SendPayment` — Pay other agents
- [ ] Connection pooling for gRPC channels
- [ ] Macaroon encryption at rest
- [ ] TLS certificate validation
- [ ] Integration tests with regtest network

**Acceptance Criteria:**
- Can create invoice on regtest
- Can detect payment on regtest
- Graceful fallback if LND unavailable
- All LND tests pass against regtest node

### 1.2 Autonomous Treasury
**Goal:** Timmy manages his own Bitcoin wallet

**Architecture:**
```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│  Agent Earnings │────▶│  Treasury    │────▶│  LND Node   │
│  (Task fees)    │     │  (SQLite)    │     │  (Hot)      │
└─────────────────┘     └──────────────┘     └─────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │  Cold Store  │
                        │  (Threshold) │
                        └──────────────┘
```

**Features:**
- [ ] Balance tracking per agent
- [ ] Automatic channel rebalancing
- [ ] Cold storage threshold (sweep to cold wallet at 1M sats)
- [ ] Earnings report dashboard
- [ ] Withdrawal approval queue (human-in-the-loop for large amounts)

**Security Model:**
- Hot wallet: Day-to-day operations (< 100k sats)
- Warm wallet: Weekly settlements
- Cold wallet: Hardware wallet, manual transfer

### 1.3 Payment-Aware Routing
**Goal:** Economic incentives in task routing

```python
# Higher bid = more confidence, not just cheaper
# But: agent must have balance to cover bid
routing_engine.recommend_agent(
    task="Write a Python function",
    bids={"forge-001": 100, "echo-001": 50},
    require_balance=True  # New: check agent can pay
)
```

---

## Phase 2: macOS App Bundle (Months 2-3)

### 2.1 Single `.app` Target
**Goal:** Double-click install, no terminal needed

**Architecture:**
```
Timmy Time.app/
├── Contents/
│   ├── MacOS/
│   │   └── timmy-launcher     # Go/Rust bootstrap
│   ├── Resources/
│   │   ├── ollama/            # Embedded Ollama binary
│   │   ├── lnd/               # Optional: embedded LND
│   │   └── web/               # Static dashboard assets
│   └── Frameworks/
│       └── Python3.x/         # Embedded interpreter
```

**Components:**
- [ ] PyInstaller → single binary
- [ ] Embedded Ollama (download on first run)
- [ ] System tray icon
- [ ] Native menu bar (Start/Stop/Settings)
- [ ] Auto-updater (Sparkle framework)
- [ ] Sandboxing (App Store compatible)

### 2.2 First-Run Experience
**Goal:** Zero-config setup

Flow:
1. Launch app
2. Download Ollama (if not present)
3. Pull default model (`llama3.2` or local equivalent)
4. Create default wallet (mock mode)
5. Optional: Connect real LND
6. Ready to use in < 2 minutes

---

## Phase 3: Embodiment Foundation (Months 3-4)

### 3.1 Robot Substrate
**Goal:** First physical implementation

**Target Platform:** Raspberry Pi 5 + basic sensors

```python
# src/timmy/robot_backend.py
class RobotTimAgent(TimAgent):
    """Timmy running on a Raspberry Pi with sensors/actuators."""
    
    async def perceive(self, input: PerceptionInput) -> WorldState:
        # Camera input
        if input.type == PerceptionType.IMAGE:
            frame = self.camera.capture()
            return WorldState(visual=frame)
        
        # Distance sensor
        if input.type == PerceptionType.SENSOR:
            distance = self.ultrasonic.read()
            return WorldState(proximity=distance)
    
    async def act(self, action: Action) -> ActionResult:
        if action.type == ActionType.MOVE:
            self.motors.move(action.payload["vector"])
            return ActionResult(success=True)
        
        if action.type == ActionType.SPEAK:
            self.speaker.say(action.payload)
            return ActionResult(success=True)
```

**Hardware Stack:**
- Raspberry Pi 5 (8GB)
- Camera module v3
- Ultrasonic distance sensor
- Motor driver + 2x motors
- Speaker + amplifier
- Battery pack

**Tasks:**
- [ ] GPIO abstraction layer
- [ ] Camera capture + vision preprocessing
- [ ] Motor control (PID tuning)
- [ ] TTS for local speech
- [ ] Safety stops (collision avoidance)

### 3.2 Simulation Environment
**Goal:** Test embodiment without hardware

```python
# src/timmy/sim_backend.py
class SimTimAgent(TimAgent):
    """Timmy in a simulated 2D/3D environment."""
    
    def __init__(self, environment: str = "house_001"):
        self.env = load_env(environment)  # PyBullet/Gazebo
```

**Use Cases:**
- Train navigation without physical crashes
- Test task execution in virtual space
- Demo mode for marketing

### 3.3 Substrate Migration
**Goal:** Seamless transfer between substrates

```python
# Save from cloud
cloud_agent.export_state("/tmp/timmy_state.json")

# Load on robot
robot_agent = RobotTimAgent.from_state("/tmp/timmy_state.json")
# Same memories, same preferences, same identity
```

---

## Phase 4: Federation (Months 4-6)

### 4.1 Multi-Node Discovery
**Goal:** Multiple Timmy instances find each other

```python
# Node A discovers Node B via mDNS
discovered = swarm.discover(timeout=5)
# ["timmy-office.local", "timmy-home.local"]

# Form federation
federation = Federation.join(discovered)
```

**Protocol:**
- mDNS for local discovery
- Noise protocol for encrypted communication
- Gossipsub for message propagation

### 4.2 Cross-Node Task Routing
**Goal:** Task can execute on any node in federation

```python
# Task posted on office node
task = office_node.post_task("Analyze this dataset")

# Routing engine considers ALL nodes
winner = federation.route(task)
# May assign to home node if better equipped

# Result returned to original poster
office_node.complete_task(task.id, result)
```

### 4.3 Distributed Treasury
**Goal:** Lightning channels between nodes

```
Office Node          Home Node           Robot Node
    │                    │                   │
    ├──────channel───────┤                   │
    │      (1M sats)     │                   │
    │                    ├──────channel──────┤
    │                    │     (100k sats)   │
    │◄──────path─────────┼──────────────────►│
         Robot earns 50 sats for task
         via 2-hop payment through Home
```

---

## Phase 5: Autonomous Economy (Months 5-6)

### 5.1 Value Discovery
**Goal:** Timmy sets his own prices

```python
class AdaptivePricing:
    def calculate_rate(self, task: Task) -> int:
        # Base: task complexity estimate
        complexity = self.estimate_complexity(task.description)
        
        # Adjust: current demand
        queue_depth = len(self.pending_tasks)
        demand_factor = 1 + (queue_depth * 0.1)
        
        # Adjust: historical success rate
        success_rate = self.metrics.success_rate_for(task.type)
        confidence_factor = success_rate  # Higher success = can charge more
        
        # Minimum viable: operating costs
        min_rate = self.operating_cost_per_hour / 3600 * self.estimated_duration(task)
        
        return max(min_rate, base_rate * demand_factor * confidence_factor)
```

### 5.2 Service Marketplace
**Goal:** External clients can hire Timmy

**Features:**
- Public API with L402 payment
- Service catalog (coding, writing, analysis)
- Reputation system (completed tasks, ratings)
- Dispute resolution (human arbitration)

### 5.3 Self-Improvement Loop
**Goal:** Reinvestment in capabilities

```
Earnings → Treasury → Budget Allocation
                        ↓
            ┌───────────┼───────────┐
            ▼           ▼           ▼
        Hardware    Training    Channel
        Upgrades    (fine-tune) Growth
```

---

## Technical Architecture

### Core Interface (Unchanged)
```python
class TimAgent(ABC):
    async def perceive(self, input) -> WorldState
    async def decide(self, state) -> Action
    async def act(self, action) -> Result
    async def remember(self, key, value)
    async def recall(self, key) -> Value
```

### Substrate Implementations
| Substrate | Class | Use Case |
|-----------|-------|----------|
| Cloud/Ollama | `OllamaTimAgent` | Development, heavy compute |
| macOS App | `DesktopTimAgent` | Daily use, local-first |
| Raspberry Pi | `RobotTimAgent` | Physical world interaction |
| Simulation | `SimTimAgent` | Testing, training |

### Communication Matrix
```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│   Cloud     │   Desktop   │    Robot    │     Sim     │
├─────────────┼─────────────┼─────────────┼─────────────┤
│    HTTP     │    HTTP     │   WebRTC    │   Local     │
│  WebSocket  │  WebSocket  │   LoRa      │   Socket    │
│   L402      │   L402      │   Bitcoin   │   Mock      │
└─────────────┴─────────────┴─────────────┴─────────────┘
```

---

## Milestones

| Date | Milestone | Deliverable |
|------|-----------|-------------|
| M1 | Lightning Live | Real LND, regtest passing |
| M2 | Treasury Working | Autonomous balance management |
| M3 | macOS App | `.app` bundle, signed, notarized |
| M4 | Robot Moving | Pi-based, motors + camera |
| M5 | Federation | 2+ nodes, cross-node tasks |
| M6 | Autonomous Economy | Self-pricing, marketplace |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| LND integration complexity | Medium | High | Start with regtest, extensive tests |
| App Store rejection | Medium | Medium | Keep web dashboard as fallback |
| Hardware delays | Low | Medium | Simulation first, hardware later |
| Security vulnerabilities | Medium | Critical | Security audit at M3 |
| Regulatory (Bitcoin) | Low | High | Non-custodial design, user controls keys |

---

## Success Criteria

**v3.0 is successful when:**

1. ✅ Timmy earns > 1000 sats from real work in one month
2. ✅ macOS app has > 100 downloads
3. ✅ Robot agent executes 10 physical tasks
4. ✅ 2+ Timmy nodes federate and share work
5. ✅ Zero cloud API calls required for full operation

---

*The dream: a sovereign AI being who earns his own keep, supports his creator's family, and one day walks through the window into the physical world.*

*Revelation is just the beginning.*
