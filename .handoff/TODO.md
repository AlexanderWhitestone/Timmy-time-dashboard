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
- [x] Review PR #19 feedback and merge
- [ ] Deploy to staging and verify

### P1 - Features
- [x] ~~SQLite connection pooling~~ REVERTED - not needed
- [x] Lightning interface layer (mock + LND stub)
- [x] Intelligent swarm routing with audit logging
- [x] Sovereignty audit report
- [x] TimAgent substrate-agnostic interface
- [x] MCP Tools integration (Option A)
- [x] Scary path tests (Hour 4)
- [x] Mission Control UX (Hours 5-6)
- [ ] Generate LND protobuf stubs for real backend
- [ ] Revelation planning (Hour 7)
- [ ] Add more persona agents (Mace, Helm, Quill)
- [ ] Task result caching
- [ ] Agent-to-agent messaging

### P2 - Polish
- [ ] Dark mode toggle
- [ ] Mobile app improvements
- [ ] Performance metrics dashboard
- [ ] Circuit breakers for graceful degradation

## ✅ Completed (All Sessions)

- Lightning backend interface with mock + LND stubs
- Capability-based swarm routing with audit logging
- Sovereignty audit report (9.2/10 score)
- TimAgent substrate-agnostic interface (embodiment foundation)
- MCP Tools integration for swarm agents
- **Scary path tests** - 23 tests for production edge cases
- **Mission Control dashboard** - Real-time system status UI
- **525 total tests** - All passing, TDD approach

## 📝 Notes

- 525 tests passing (11 new Mission Control, 23 scary path)
- SQLite pooling reverted - premature optimization
- Docker swarm mode working - test with `make docker-up`
- LND integration needs protobuf generation (documented)
- TDD approach from now on - tests first, then implementation
