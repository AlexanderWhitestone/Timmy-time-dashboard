# lightning/ — Module Guide

**Security-sensitive.** Bitcoin Lightning payment gating (L402).
Never hard-code secrets. Use `from config import settings` for all credentials.

## Testing
```bash
pytest tests/lightning/ -q
```
