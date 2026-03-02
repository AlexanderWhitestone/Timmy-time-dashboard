# Darlings to Kill: Streamlining Timmy's System

To reduce technical debt and align with standard open-source practices, I have identified 10 custom "homebrew" components in the `Timmy-time-dashboard` repository that should be replaced with established open-source alternatives.

| Component | Current Homebrew Implementation | Proposed Open-Source Replacement | Rationale |
| :--- | :--- | :--- | :--- |
| **1. Event Bus** | `infrastructure/events/bus.py` | **NATS** or **Redis Pub/Sub** | Replaces custom async `EventBus` with a robust, scalable messaging system. |
| **2. Task Queue** | `swarm/task_queue/` | **Celery** or **Temporal** | Replaces manual SQLite polling and task processing with industry-standard distributed task management. |
| **3. Memory Layer** | `brain/memory.py` | **ChromaDB** or **Qdrant** | Replaces custom SQLite/rqlite wrapper with a purpose-built vector database for agentic memory. |
| **4. WebSocket Manager** | `infrastructure/ws_manager/` | **FastAPI's built-in WebSocket support** | Simplifies custom connection tracking and history management using standard FastAPI patterns. |
| **5. CSRF Protection** | `dashboard/middleware/csrf.py` | **fastapi-csrf-protect** | Replaces custom HMAC-based CSRF logic with a community-vetted security middleware. |
| **6. Request Logging** | `dashboard/middleware/request_logging.py` | **Loguru** or **structlog** | Replaces custom logging middleware with powerful, structured logging libraries. |
| **7. Voice NLU** | `integrations/voice/nlu.py` | **Rasa** or **spaCy** | Replaces fragile regex-based intent detection with professional NLP/NLU frameworks. |
| **8. Self-TDD Watchdog** | `self_coding/self_tdd/watchdog.py` | **pytest-watch** | Replaces custom `subprocess.run` polling loop with a dedicated test-watching tool. |
| **9. Notification System** | `infrastructure/notifications/push.py` | **Apprise** | Replaces custom `osascript` and local deque logic with a universal notification library supporting 50+ services. |
| **10. Tool Registry** | `mcp/registry.py` | **LangChain Tools** or **Haystack** | Replaces custom dynamic discovery and health tracking with standardized tool/plugin ecosystems. |

### Summary of Benefits
*   **Reduced Codebase Complexity:** Removing ~2,000 lines of custom infrastructure logic.
*   **Improved Reliability:** Moving from "it works on my machine" to battle-tested community tools.
*   **Scalability:** Standard tools like Redis or NATS allow Timmy to scale beyond a single local machine.
*   **Security:** Using vetted libraries for CSRF and logging reduces the risk of homebrew vulnerabilities.
