# Security Policy & Audit Report

This document outlines the security architecture, threat model, and recent audit findings for Timmy Time Mission Control.

## Sovereignty-First Security

Timmy Time is built on the principle of **AI Sovereignty**. Security is not just about preventing unauthorized access, but about ensuring the user maintains full control over their data and AI models.

1.  **Local-First Execution:** All primary AI inference (Ollama/AirLLM) runs on localhost. No data is sent to third-party cloud providers unless explicitly configured (e.g., Grok).
2.  **Air-Gapped Ready:** The system is designed to run without an internet connection once dependencies and models are cached.
3.  **Secret Management:** Secrets are never hard-coded. They are managed via Pydantic-settings from `.env` or environment variables.

## Threat Model

| Threat | Mitigation |
| :--- | :--- |
| **Command Injection** | Use of `asyncio.create_subprocess_exec` with explicit argument lists instead of shell strings where possible. |
| **XSS** | Jinja2 auto-escaping is enabled. Manual `innerHTML` usage in templates is combined with `DOMPurify` and `marked`. |
| **Unauthorized Access** | L402 Lightning-gated API server (`timmy-serve`) provides cryptographic access control. |
| **Malicious Self-Modify** | Self-modification is disabled by default (`SELF_MODIFY_ENABLED=false`). It requires manual approval in the dashboard and runs on isolated git branches. |

## Audit Findings (Feb 2026)

A manual audit of the codebase identified the following security-sensitive areas:

### 1. Self-Modification Loop *(planned, not yet implemented)*
- **Observation:** When implemented, the self-modify loop will use `subprocess.run` for git and test commands.
- **Risk:** Potential for command injection if user-provided instructions are improperly handled.
- **Mitigation:** Input should be restricted to git operations and pytest. Future versions should sandbox these executions.

### 2. Model Registration (`src/dashboard/routes/models.py`)
- **Observation:** Allows registering models from arbitrary local paths.
- **Risk:** Path traversal if an attacker can call this API.
- **Mitigation:** API is intended for local use. In production, ensure this endpoint is firewalled or authenticated.

### 3. XSS in Chat (`src/dashboard/templates/partials/chat_message.html`)
- **Observation:** Uses `innerHTML` for rendering Markdown.
- **Mitigation:** Already uses `DOMPurify.sanitize()` to prevent XSS from LLM-generated content.

## Security Recommendations

1.  **Enable L402:** For any deployment exposed to the internet, ensure `timmy-serve` is used with a real Lightning backend.
2.  **Audit `self_edit`:** The `SelfEditTool` has significant power. Keep `SELF_MODIFY_ENABLED=false` unless actively developing the agent's self-coding capabilities.
3.  **Production Secrets:** Always generate unique `L402_HMAC_SECRET` and `L402_MACAROON_SECRET` for production deployments.

---

*Last Updated: Feb 28, 2026*
