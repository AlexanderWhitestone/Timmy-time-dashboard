# integrations/ — Module Guide

External platform bridges. All are optional dependencies.

## Structure
- `chat_bridge/` — Vendor-agnostic chat platform abstraction (Discord impl)
- `telegram_bot/` — Telegram bot bridge
- `shortcuts/` — iOS Siri Shortcuts API metadata
- `voice/` — Local NLU intent detection (regex-based, no cloud)

## Testing
```bash
pytest tests/integrations/ -q
```
