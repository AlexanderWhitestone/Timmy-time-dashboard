# Sprint v2.0.0 - Remaining Tasks

## ✅ Completed
- [x] Swarm E2E (auto-spawn, WebSocket broadcasts)
- [x] MCP Tools (search, file, shell, Python)
- [x] timmy-serve L402 implementation
- [x] Browser notifications
- [x] Test coverage (436 tests, 0 warnings)
- [x] PR #18 created

## 🔄 Next Up (Priority Order)

### P0 - Critical
- [ ] Review PR #18 feedback and merge
- [ ] Deploy to staging and verify

### P1 - Features
- [ ] SQLite connection pooling (retry with proper test isolation)
- [ ] Add more persona agents (Mace, Helm, Quill)
- [ ] Task result caching
- [ ] Agent-to-agent messaging

### P2 - Polish
- [ ] Dark mode toggle
- [ ] Mobile app improvements
- [ ] Performance metrics dashboard

## 📝 Notes

- SQLite pooling was reverted - need different approach
- All tests passing - maintain 0 warning policy
- Docker swarm mode working - test with `make docker-up`
