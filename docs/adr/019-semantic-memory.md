# ADR 019: Semantic Memory (Vector Store)

## Status
Accepted

## Context
The Echo agent needed the ability to remember conversations, facts, and context across sessions. Simple keyword search was insufficient for finding relevant historical context.

## Decision
Implement a vector-based semantic memory store using SQLite with optional sentence-transformers embeddings.

## Context Types

| Type | Description |
|------|-------------|
| `conversation` | User/agent dialogue |
| `fact` | Extracted facts about user/system |
| `document` | Uploaded documents |

## Schema
```sql
CREATE TABLE memory_entries (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    source TEXT NOT NULL,
    context_type TEXT NOT NULL DEFAULT 'conversation',
    agent_id TEXT,
    task_id TEXT,
    session_id TEXT,
    metadata TEXT,  -- JSON
    embedding TEXT,  -- JSON array of floats
    timestamp TEXT NOT NULL
);
```

## Embedding Strategy

**Primary**: sentence-transformers `all-MiniLM-L6-v2` (384 dimensions)
- High quality semantic similarity
- Local execution (no cloud)
- ~80MB model download

**Fallback**: Character n-gram hash embedding
- No external dependencies
- Lower quality but functional
- Enables system to work without heavy ML deps

## Usage

```python
from memory.vector_store import (
    store_memory,
    search_memories,
    get_memory_context,
)

# Store a memory
store_memory(
    content="User prefers dark mode",
    source="user",
    context_type="fact",
    agent_id="echo",
)

# Search for relevant context
results = search_memories(
    query="user preferences",
    agent_id="echo",
    limit=5,
)

# Get formatted context for LLM
context = get_memory_context(
    query="what does user like?",
    max_tokens=1000,
)
```

## Integration Points

### Echo Agent
Echo should store all conversations and retrieve relevant context when answering questions about "what we discussed" or "what we know".

### Task Context
Task handlers can query for similar past tasks:
```python
similar = search_memories(
    query=task.description,
    context_type="conversation",
    limit=3,
)
```

## Similarity Scoring

**Cosine Similarity** (when embeddings available):
```python
score = dot(a, b) / (norm(a) * norm(b))  # -1 to 1
```

**Keyword Overlap** (fallback):
```python
score = len(query_words & content_words) / len(query_words)
```

## Consequences
- **Positive**: Semantic search finds related content even without keyword matches
- **Negative**: Embedding computation adds latency (~10-100ms per query)
- **Mitigation**: Background embedding computation, caching

## Future Work
- sqlite-vss extension for vector similarity index
- Memory compression for long-term storage
- Automatic fact extraction from conversations
