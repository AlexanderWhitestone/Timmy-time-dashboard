"""Database schema for distributed brain.

SQL to initialize rqlite with memories and tasks tables.
"""

# Schema version for migrations
SCHEMA_VERSION = 1

INIT_SQL = """
-- Enable SQLite extensions
.load vector0
.load vec0

-- Memories table with vector search
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY,
    content TEXT NOT NULL,
    embedding BLOB,  -- 384-dim float32 array (normalized)
    source TEXT,     -- 'timmy', 'zeroclaw', 'worker', 'user'
    tags TEXT,       -- JSON array
    metadata TEXT,   -- JSON object
    created_at TEXT  -- ISO8601
);

-- Tasks table (distributed queue)
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    content TEXT NOT NULL,
    task_type TEXT DEFAULT 'general',  -- shell, creative, code, research, general
    priority INTEGER DEFAULT 0,        -- Higher = process first
    status TEXT DEFAULT 'pending',     -- pending, claimed, done, failed
    claimed_by TEXT,                   -- Node ID
    claimed_at TEXT,
    result TEXT,
    error TEXT,
    metadata TEXT,                     -- JSON
    created_at TEXT,
    completed_at TEXT
);

-- Node registry (who's online)
CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    capabilities TEXT,  -- JSON array
    last_seen TEXT,     -- ISO8601
    load_average REAL
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_memories_source ON memories(source);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_status_priority ON tasks(status, priority DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_claimed ON tasks(claimed_by, status);
CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(task_type);

-- Virtual table for vector search (if using sqlite-vec)
-- Note: This requires sqlite-vec extension loaded
CREATE VIRTUAL TABLE IF NOT EXISTS vec_memories USING vec0(
    embedding float[384]
);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT
);

INSERT OR REPLACE INTO schema_version (version, applied_at) 
VALUES (1, datetime('now'));
"""

MIGRATIONS = {
    # Future migrations go here
    # 2: "ALTER TABLE ...",
}


def get_init_sql() -> str:
    """Get SQL to initialize fresh database."""
    return INIT_SQL


def get_migration_sql(from_version: int, to_version: int) -> str:
    """Get SQL to migrate between versions."""
    if to_version <= from_version:
        return ""
    
    sql_parts = []
    for v in range(from_version + 1, to_version + 1):
        if v in MIGRATIONS:
            sql_parts.append(MIGRATIONS[v])
            sql_parts.append(f"UPDATE schema_version SET version = {v}, applied_at = datetime('now');")
    
    return "\n".join(sql_parts)
