# Timmy Time — Workset Plan (Post-Quality Review)

**Date:** 2026-02-25  
**Based on:** QUALITY_ANALYSIS.md + QUALITY_REVIEW_REPORT.md

---

## Executive Summary

This workset addresses critical security vulnerabilities, hardens the tool system for reliability, improves privacy alignment with the "sovereign AI" vision, and enhances agent intelligence.

---

## Workset A: Security Fixes (P0) 🔒

### A1: XSS Vulnerabilities (SEC-01)
**Priority:** P0 — Critical  
**Files:** `mobile.html`, `swarm_live.html`

**Issues:**
- `mobile.html` line ~85 uses raw `innerHTML` with unsanitized user input
- `swarm_live.html` line ~72 uses `innerHTML` with WebSocket agent data

**Fix:** Replace `innerHTML` string interpolation with safe DOM methods (`textContent`, `createTextNode`, or DOMPurify if available).

### A2: Hardcoded Secrets (SEC-02)
**Priority:** P1 — High  
**Files:** `l402_proxy.py`, `payment_handler.py`

**Issue:** Default secrets are production-safe strings instead of `None` with startup assertion.

**Fix:** 
- Change defaults to `None`
- Add startup assertion requiring env vars to be set
- Fail fast with clear error message

---

## Workset B: Tool System Hardening ⚙️

### B1: SSL Certificate Fix
**Priority:** P1 — High  
**File:** Web search via DuckDuckGo

**Issue:** `CERTIFICATE_VERIFY_FAILED` errors prevent web search from working.

**Fix Options:**
- Option 1: Use `certifi` package for proper certificate bundle
- Option 2: Add `verify_ssl=False` parameter (less secure, acceptable for local)
- Option 3: Document SSL fix in troubleshooting

### B2: Tool Usage Instructions
**Priority:** P2 — Medium  
**File:** `prompts.py`

**Issue:** Agent makes unnecessary tool calls for simple questions.

**Fix:** Add tool usage instructions to system prompt:
- Only use tools when explicitly needed
- For simple chat/questions, respond directly
- Tools are for: web search, file operations, code execution

### B3: Tool Error Handling
**Priority:** P2 — Medium  
**File:** `tools.py`

**Issue:** Tool failures show stack traces to user.

**Fix:** Add graceful error handling with user-friendly messages.

---

## Workset C: Privacy & Sovereignty 🛡️

### C1: Agno Telemetry (Privacy)
**Priority:** P2 — Medium  
**File:** `agent.py`, `backends.py`

**Issue:** Agno sends telemetry to `os-api.agno.com` which conflicts with "sovereign" vision.

**Fix:**
- Add `telemetry_enabled=False` parameter to Agent
- Document how to disable for air-gapped deployments
- Consider environment variable `TIMMY_TELEMETRY=0`

### C2: Secrets Validation
**Priority:** P1 — High  
**File:** `config.py`, startup

**Issue:** Default secrets used without warning in production.

**Fix:**
- Add production mode detection
- Fatal error if default secrets in production
- Clear documentation on generating secrets

---

## Workset D: Agent Intelligence 🧠

### D1: Enhanced System Prompt
**Priority:** P2 — Medium  
**File:** `prompts.py`

**Enhancements:**
- Tool usage guidelines (when to use, when not to)
- Memory awareness ("You remember previous conversations")
- Self-knowledge (capabilities, limitations)
- Response style guidelines

### D2: Memory Improvements
**Priority:** P2 — Medium  
**File:** `agent.py`

**Enhancements:**
- Increase history runs from 10 to 20 for better context
- Add memory summarization for very long conversations
- Persistent session tracking

---

## Execution Order

| Order | Workset | Task | Est. Time |
|-------|---------|------|-----------|
| 1 | A | XSS fixes | 30 min |
| 2 | A | Secrets hardening | 20 min |
| 3 | B | SSL certificate fix | 15 min |
| 4 | B | Tool instructions | 20 min |
| 5 | C | Telemetry disable | 15 min |
| 6 | C | Secrets validation | 20 min |
| 7 | D | Enhanced prompts | 30 min |
| 8 | — | Test everything | 30 min |

**Total: ~3 hours**

---

## Success Criteria

- [ ] No XSS vulnerabilities (verified by code review)
- [ ] Secrets fail fast in production
- [ ] Web search works without SSL errors
- [ ] Agent uses tools appropriately (not for simple chat)
- [ ] Telemetry disabled by default
- [ ] All 895+ tests pass
- [ ] New tests added for security fixes
