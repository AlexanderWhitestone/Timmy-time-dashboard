# Timmy Time Issue Resolution Plan

This document outlines the identified issues within the Timmy Time application and the Test-Driven Development (TDD) strategy to address them, ensuring a robust and functional system.

## Identified Issues

Based on the initial investigation and interview process, the following key issues have been identified:

1.  **Ollama Model Availability and Reliability:**
    *   **Problem:** The preferred `llama3.1:8b-instruct` model could not be pulled from Ollama, leading to a fallback to `llama3.2`. The `llama3.2` model is noted in the `prompts.py` file as being 
less reliable for tool calling. This impacts Timmy's ability to effectively use tools and potentially other agents in the swarm.

2.  **Dashboard Responsiveness:**
    *   **Problem:** The web dashboard did not respond to `curl` requests after startup, indicating a potential issue with the Uvicorn server or the application itself. The previous attempt to start the dashboard showed a `briefing_scheduler` and other persona agents being spawned, which might be resource-intensive and blocking the main thread.

3.  **Background Task Management:**
    *   **Problem:** The `briefing_scheduler` and other background tasks might be causing performance bottlenecks or preventing the main application from starting correctly. Their execution needs to be optimized or managed asynchronously.

4.  **Dockerization:**
    *   **Problem:** The current setup involves manual installation of Ollama and Python dependencies. The user explicitly requested dockerization for a more robust and portable deployment.

## Test-Driven Development (TDD) Strategy

To address these issues, I will employ a comprehensive TDD approach, focusing on creating automated tests before implementing any fixes or upgrades. This will ensure that each change is validated and that regressions are prevented.

### Phase 1: Itemize Issues and Define TDD Strategy (Current Phase)

*   **Action:** Complete this document, detailing all identified issues and the TDD strategy.
*   **Deliverable:** `issue_resolution_plan.md`

### Phase 2: Implement Functional E2E Tests for Identified Issues

*   **Objective:** Create end-to-end (E2E) tests that replicate the identified issues and verify the desired behavior after fixes.
*   **Focus Areas:**
    *   **Ollama Model:** Test Timmy's ability to use tools with the `llama3.2` model and, if possible, with `llama3.1:8b-instruct` once available. This will involve mocking Ollama responses or ensuring the model is correctly loaded and utilized.
    *   **Dashboard Responsiveness:** Develop E2E tests that assert the dashboard is accessible and responsive after startup. This will involve making HTTP requests to various endpoints and verifying the responses.
    *   **Background Tasks:** Create tests to ensure background tasks (e.g., `briefing_scheduler`) run without blocking the main application thread and complete their operations successfully.
*   **Tools:** `pytest`, `pytest-asyncio`, `httpx` (for HTTP requests), `unittest.mock` (for mocking external dependencies like Ollama).
*   **Deliverable:** New test files (e.g., `tests/e2e/test_dashboard.py`, `tests/e2e/test_ollama_integration.py`).

### Phase 3: Fix Dashboard Responsiveness and Optimize Background Tasks

*   **Objective:** Implement code changes to resolve the dashboard's unresponsiveness and optimize background task execution.
*   **Focus Areas:**
    *   **Asynchronous Operations:** Investigate and refactor blocking operations in the dashboard's startup and background tasks to use asynchronous programming (e.g., `asyncio`, `FastAPI`'s background tasks).
    *   **Resource Management:** Optimize resource usage for background tasks to prevent them from monopolizing CPU or memory.
    *   **Error Handling:** Improve error handling and logging for robustness.
*   **Deliverable:** Modified source code files (e.g., `src/dashboard/app.py`, `src/timmy/briefing.py`).

### Phase 4: Dockerize the Application and Verify Container Orchestration

*   **Objective:** Create Dockerfiles and Docker Compose configurations to containerize the Timmy Time application and its dependencies.
*   **Focus Areas:**
    *   **Dockerfile:** Create a `Dockerfile` for the main application, including Python dependencies and the Ollama client.
    *   **Docker Compose:** Set up `docker-compose.yml` to orchestrate the application, Ollama server, and any other necessary services (e.g., Redis for swarm communication).
    *   **Volume Mounting:** Ensure proper volume mounting for persistent data (e.g., Ollama models, SQLite databases).
*   **Tools:** `Dockerfile`, `docker-compose.yml`.
*   **Deliverable:** `Dockerfile`, `docker-compose.yml`.

### Phase 5: Run Full Test Suite and Perform Final Validation

*   **Objective:** Execute the entire test suite (unit, integration, and E2E tests) within the Dockerized environment to ensure all issues are resolved and no regressions have been introduced.
*   **Focus Areas:**
    *   **Automated Testing:** Run `make test` (or equivalent Dockerized command) to execute all tests.
    *   **Manual Verification:** Perform manual checks of the dashboard and core agent functionality.
*   **Deliverable:** Test reports, confirmation of successful application startup and operation.

### Phase 6: Deliver Final Report and Functional System to User

*   **Objective:** Provide a comprehensive report to the user, detailing the fixes, upgrades, and the fully functional, Dockerized Timmy Time system.
*   **Deliverable:** Final report, Docker Compose files, and instructions for deployment.


## Identified Issues

Based on the initial investigation and interview process, the following key issues have been identified:

1.  **Ollama Model Availability and Reliability:**
    *   **Problem:** The preferred `llama3.1:8b-instruct` model could not be pulled from Ollama, leading to a fallback to `llama3.2`. The `llama3.2` model is noted in the `prompts.py` file as being less reliable for tool calling. This impacts Timmy's ability to effectively use tools and potentially other agents in the swarm.

2.  **Dashboard Responsiveness:**
    *   **Problem:** The web dashboard did not respond to `curl` requests after startup, indicating a potential issue with the Uvicorn server or the application itself. The previous attempt to start the dashboard showed a `briefing_scheduler` and other persona agents being spawned, which might be resource-intensive and blocking the main thread.

3.  **Background Task Management:**
    *   **Problem:** The `briefing_scheduler` and other background tasks might be causing performance bottlenecks or preventing the main application from starting correctly. Their execution needs to be optimized or managed asynchronously.

4.  **Dockerization:**
    *   **Problem:** The current setup involves manual installation of Ollama and Python dependencies. The user explicitly requested dockerization for a more robust and portable deployment.

## Test-Driven Development (TDD) Strategy

To address these issues, I will employ a comprehensive TDD approach, focusing on creating automated tests before implementing any fixes or upgrades. This will ensure that each change is validated and that regressions are prevented.

### Phase 1: Itemize Issues and Define TDD Strategy (Current Phase)

*   **Action:** Complete this document, detailing all identified issues and the TDD strategy.
*   **Deliverable:** `issue_resolution_plan.md`

### Phase 2: Implement Functional E2E Tests for Identified Issues

*   **Objective:** Create end-to-end (E2E) tests that replicate the identified issues and verify the desired behavior after fixes.
*   **Focus Areas:**
    *   **Ollama Model:** Test Timmy's ability to use tools with the `llama3.2` model and, if possible, with `llama3.1:8b-instruct` once available. This will involve mocking Ollama responses or ensuring the model is correctly loaded and utilized.
    *   **Dashboard Responsiveness:** Develop E2E tests that assert the dashboard is accessible and responsive after startup. This will involve making HTTP requests to various endpoints and verifying the responses.
    *   **Background Tasks:** Create tests to ensure background tasks (e.g., `briefing_scheduler`) run without blocking the main application thread and complete their operations successfully.
*   **Tools:** `pytest`, `pytest-asyncio`, `httpx` (for HTTP requests), `unittest.mock` (for mocking external dependencies like Ollama).
*   **Deliverable:** New test files (e.g., `tests/e2e/test_dashboard.py`, `tests/e2e/test_ollama_integration.py`).

### Phase 3: Fix Dashboard Responsiveness and Optimize Background Tasks

*   **Objective:** Implement code changes to resolve the dashboard's unresponsiveness and optimize background task execution.
*   **Focus Areas:**
    *   **Asynchronous Operations:** Investigate and refactor blocking operations in the dashboard's startup and background tasks to use asynchronous programming (e.g., `asyncio`, `FastAPI`'s background tasks).
    *   **Resource Management:** Optimize resource usage for background tasks to prevent them from monopolizing CPU or memory.
    *   **Error Handling:** Improve error handling and logging for robustness.
*   **Deliverable:** Modified source code files (e.g., `src/dashboard/app.py`, `src/timmy/briefing.py`).

### Phase 4: Dockerize the Application and Verify Container Orchestration

*   **Objective:** Create Dockerfiles and Docker Compose configurations to containerize the Timmy Time application and its dependencies.
*   **Focus Areas:**
    *   **Dockerfile:** Create a `Dockerfile` for the main application, including Python dependencies and the Ollama client.
    *   **Docker Compose:** Set up `docker-compose.yml` to orchestrate the application, Ollama server, and any other necessary services (e.g., Redis for swarm communication).
    *   **Volume Mounting:** Ensure proper volume mounting for persistent data (e.g., Ollama models, SQLite databases).
*   **Tools:** `Dockerfile`, `docker-compose.yml`.
*   **Deliverable:** `Dockerfile`, `docker-compose.yml`.

### Phase 5: Run Full Test Suite and Perform Final Validation

*   **Objective:** Execute the entire test suite (unit, integration, and E2E tests) within the Dockerized environment to ensure all issues are resolved and no regressions have been introduced.
*   **Focus Areas:**
    *   **Automated Testing:** Run `make test` (or equivalent Dockerized command) to execute all tests.
    *   **Manual Verification:** Perform manual checks of the dashboard and core agent functionality.
*   **Deliverable:** Test reports, confirmation of successful application startup and operation.

### Phase 6: Deliver Final Report and Functional System to User

*   **Objective:** Provide a comprehensive report to the user, detailing the fixes, upgrades, and the fully functional, Dockerized Timmy Time system.
*   **Deliverable:** Final report, Docker Compose files, and instructions for deployment.
