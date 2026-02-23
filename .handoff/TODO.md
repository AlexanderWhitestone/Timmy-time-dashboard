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
- [x] ~~SQLite connection pooling~~ REVERTED - not needed
- [x] Lightning interface layer (mock + LND stub)
- [x] Intelligent swarm routing with audit logging
- [x] Sovereignty audit report
- [x] TimAgent substrate-agnostic interface
- [ ] Generate LND protobuf stubs for real backend
- [ ] Add more persona agents (Mace, Helm, Quill)
- [ ] Task result caching
- [ ] Agent-to-agent messaging

### P2 - Polish
- [ ] Dark mode toggle
- [ ] Mobile app improvements
- [ ] Performance metrics dashboard
- [ ] Circuit breakers for graceful degradation

## ✅ Completed (This Session)

- Lightning backend interface with mock + LND stubs
- Capability-based swarm routing with audit logging
- Sovereignty audit report (9.2/10 score)
- 36 new tests for Lightning and routing
- Substrate-agnostic TimAgent interface (embodiment foundation)

## 📝 Notes

- 472 tests passing (36 new)
- SQLite pooling reverted - premature optimization
- Docker swarm mode working - test with `make docker-up`
- LND integration needs protobuf generation (documented)
