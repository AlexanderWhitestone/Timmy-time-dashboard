# ADR 021: Self-Upgrade Approval Queue

## Status
Proposed

## Context
The self-modification system (`src/self_modify/loop.py`) can generate code changes autonomously. However, it currently either:
- Applies changes immediately (risky)
- Requires manual git review (slow)

We need an approval queue where changes are staged for human review before application.

## Decision
Implement a dashboard-based approval queue for self-modifications with the following states:
`proposed` → `approved` | `rejected` → `applied` | `failed`

## Architecture

### State Machine
```
                    ┌─────────────┐
                    │   PROPOSED  │
                    └──────┬──────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │  APPROVED  │  │  REJECTED  │  │  EXPIRED   │
    └──────┬─────┘  └────────────┘  └────────────┘
           │
           ▼
    ┌────────────┐
    │  APPLIED   │
    └──────┬─────┘
           │
           ▼
    ┌────────────┐
    │   FAILED   │
    └────────────┘
```

### Components

1. **Database Table** (`upgrades` table)
   ```sql
   CREATE TABLE upgrades (
       id TEXT PRIMARY KEY,
       status TEXT NOT NULL,  -- proposed, approved, rejected, applied, failed
       proposed_at TEXT NOT NULL,
       approved_at TEXT,
       applied_at TEXT,
       rejected_at TEXT,
       branch_name TEXT NOT NULL,
       description TEXT NOT NULL,
       files_changed TEXT,  -- JSON array
       diff_preview TEXT,   -- Short diff for review
       test_results TEXT,   -- JSON: {passed: bool, output: str}
       error_message TEXT,
       approved_by TEXT     -- For audit
   );
   ```

2. **Self-Modify Loop** (`src/self_modify/loop.py`)
   - On change proposal: Create `proposed` entry, stop
   - On approval: Checkout branch, apply changes, run tests, commit
   - On rejection: Cleanup branch, mark `rejected`

3. **Dashboard UI** (`/self-modify/queue`)
   - List all proposed changes
   - Show diff preview
   - Approve/Reject buttons
   - Show test results
   - History of past upgrades

4. **API Endpoints**
   - `GET /self-modify/queue` - List pending upgrades
   - `POST /self-modify/queue/{id}/approve` - Approve upgrade
   - `POST /self-modify/queue/{id}/reject` - Reject upgrade
   - `GET /self-modify/queue/{id}/diff` - View full diff

### Integration Points

**Existing: Self-Modify Loop**
- Currently: Proposes change → applies immediately (or fails)
- New: Proposes change → creates DB entry → waits for approval

**Existing: Dashboard**
- New page: Upgrade Queue
- New nav item: "UPGRADES" with badge showing pending count

**Existing: Event Log**
- Logs: `upgrade.proposed`, `upgrade.approved`, `upgrade.applied`, `upgrade.failed`

### Security Considerations

1. **Approval Authentication** - Consider requiring password/PIN for approval
2. **Diff Size Limits** - Reject diffs >10k lines (prevents DoS)
3. **Test Requirement** - Must pass tests before applying
4. **Rollback** - Keep previous commit SHA for rollback

### Approval Flow

```python
# 1. System proposes upgrade
upgrade = UpgradeQueue.propose(
    description="Fix bug in task assignment",
    branch_name="self-modify/fix-task-001",
    files_changed=["src/swarm/coordinator.py"],
    diff_preview="@@ -123,7 +123,7 @@...",
)
# Status: PROPOSED

# 2. Human reviews in dashboard
# - Views diff
# - Sees test results (auto-run on propose)
# - Clicks APPROVE or REJECT

# 3. If approved
upgrade.apply()  # Status: APPLIED or FAILED

# 4. If rejected
upgrade.reject()  # Status: REJECTED, branch deleted
```

## UI Design

### Upgrade Queue Page (`/self-modify/queue`)

```
┌─────────────────────────────────────────┐
│ PENDING UPGRADES (2)                    │
├─────────────────────────────────────────┤
│                                         │
│ Fix bug in task assignment      [VIEW]  │
│ Branch: self-modify/fix-task-001        │
│ Files: coordinator.py                   │
│ Tests: ✓ Passed                         │
│ [APPROVE]  [REJECT]                     │
│                                         │
│ Add memory search feature       [VIEW]  │
│ Branch: self-modify/memory-002          │
│ Files: memory/vector_store.py           │
│ Tests: ✗ Failed (1 error)               │
│ [APPROVE]  [REJECT]                     │
│                                         │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ UPGRADE HISTORY                         │
├─────────────────────────────────────────┤
│ ✓ Fix auth bug           APPLIED 2h ago │
│ ✗ Add new route          FAILED  5h ago │
│ ✗ Change config          REJECTED 1d ago│
└─────────────────────────────────────────┘
```

## Consequences

### Positive
- Human oversight prevents bad changes
- Audit trail of all modifications
- Test-before-apply prevents broken states
- Rejection is clean (no lingering branches)

### Negative
- Adds friction to self-modification
- Requires human availability for urgent fixes
- Database storage for upgrade history

### Mitigations
- Auto-approve after 24h for low-risk changes (configurable)
- Urgent changes can bypass queue (with logging)
- Prune old history after 90 days

## Implementation Plan

1. Create `src/upgrades/models.py` - Database schema and ORM
2. Create `src/upgrades/queue.py` - Queue management logic
3. Modify `src/self_modify/loop.py` - Integrate with queue
4. Create dashboard routes - UI for approval
5. Create templates - Queue page, diff view
6. Add event logging for upgrades
7. Write tests for full workflow

## Dependencies
- Existing `src/self_modify/loop.py`
- New database table `upgrades`
- Existing Event Log system
