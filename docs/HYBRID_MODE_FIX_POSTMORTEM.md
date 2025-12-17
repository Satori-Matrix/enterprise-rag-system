# Hybrid Mode Fix - Post-Mortem Analysis
**Date:** December 13, 2025  
**Issue:** Hybrid mode retrieved 0 chunks while naive mode retrieved 20 chunks  
**Status:** ✅ RESOLVED

---

## Executive Summary

**Problem:** LightRAG hybrid mode was returning 0 chunks despite having 477 chunks in the database and a functioning knowledge graph with 3,257 entities.

**Root Cause:** The `lightrag_doc_chunks` table (PGKVStorage for text_chunks_db) was empty, while `lightrag_vdb_chunks` (PGVectorStorage for vector search) contained all 477 chunks.

**Solution:** Populated `lightrag_doc_chunks` by copying data from `lightrag_vdb_chunks`.

**Impact:** Hybrid mode now successfully retrieves 20 chunks per query, matching naive mode performance.

---

## 1. Why was lightrag_doc_chunks table empty while lightrag_vdb_chunks had 477 chunks?

### Storage Architecture Understanding

LightRAG uses **three separate storage backends** for different purposes:

```
┌─────────────────────────────────────────────────────────────────┐
│                     LightRAG Storage Layers                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. chunks_vdb (PGVectorStorage)                                │
│     └─> lightrag_vdb_chunks table                               │
│     └─> Purpose: Vector similarity search                       │
│     └─> Used by: Naive mode, entity/relation vector search     │
│                                                                   │
│  2. text_chunks_db (PGKVStorage)                                │
│     └─> lightrag_doc_chunks table                               │
│     └─> Purpose: Fetch full chunk content by ID                │
│     └─> Used by: Hybrid/local/global modes                     │
│                                                                   │
│  3. knowledge_graph_inst (NetworkXStorage)                      │
│     └─> graph_chunk_entity_relation.graphml file                │
│     └─> Purpose: Entity/relation graph with source_id refs     │
│     └─> Used by: Hybrid/local/global modes                     │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Why the Discrepancy?

**During document ingestion, LightRAG should populate BOTH tables:**

1. **chunks_vdb** gets populated during vector embedding creation
2. **text_chunks_db** gets populated during chunk storage

**What went wrong:**

The document processing pipeline on the GPU (RunPod) likely:
- ✅ Created vector embeddings → `lightrag_vdb_chunks` populated
- ✅ Built knowledge graph → NetworkX graph created with entity→chunk references
- ❌ **FAILED** to populate `lightrag_doc_chunks` table

**Possible causes:**
- Configuration mismatch between GPU and CPU environments
- KV storage initialization failure during ingestion
- Database connection issue during chunk storage phase
- Code path that only writes to VDB but skips KV storage

---

## 2. Was this caused by how we synced data from GPU to CPU? If yes, what step was missing?

### Yes, this was likely a sync/configuration issue.

### GPU → CPU Data Sync Process

**Current setup:**
- **GPU (RunPod):** Document processing, embedding generation, graph building
- **CPU (Hostinger VPS):** Query serving, Chainlit UI

**What gets synced:**
1. ✅ PostgreSQL database dump (includes `lightrag_vdb_*` tables)
2. ✅ NetworkX graph file (`graph_chunk_entity_relation.graphml`)
3. ✅ KV store JSON files (entity_chunks, relation_chunks, etc.)

**What was missing:**

The `lightrag_doc_chunks` table was **never populated on the GPU** during document processing.

### Root Cause Analysis

**Theory 1: Configuration Mismatch**

GPU environment may have been configured with:
```python
LIGHTRAG_KV_STORAGE=JsonKVStorage  # Uses JSON files
```

While CPU environment uses:
```python
LIGHTRAG_KV_STORAGE=PGKVStorage  # Uses PostgreSQL
```

If GPU used JsonKVStorage, chunks would be in `kv_store_text_chunks.json` (which we found to be empty), and never synced to PostgreSQL.

**Theory 2: Incomplete Ingestion Pipeline**

The document ingestion code may have:
- Created embeddings and stored in `chunks_vdb` ✅
- Built knowledge graph with entity references ✅
- **Skipped** storing full chunk content in `text_chunks_db` ❌

**Evidence:**
```sql
-- VDB table: 477 chunks
SELECT COUNT(*) FROM lightrag_vdb_chunks WHERE workspace='default';
-- Result: 477

-- KV storage table: 0 chunks
SELECT COUNT(*) FROM lightrag_doc_chunks WHERE workspace='default';
-- Result: 0

-- JSON KV store: 0 entries
cat /app/rag_storage/default/kv_store_text_chunks.json
-- Result: {}
```

This suggests the text_chunks_db write operation was **never executed** during ingestion.

---

## 3. How do we prevent this in future document uploads? What validation should we add?

### Prevention Strategy

#### A. Pre-Upload Validation

**Before processing documents:**

```python
async def validate_storage_config():
    """Ensure all storage backends are properly initialized"""
    
    # Check 1: Verify KV storage is writable
    test_chunk = {"test_id": {"content": "test", "tokens": 1}}
    await text_chunks_db.upsert(test_chunk)
    result = await text_chunks_db.get("test_id")
    assert result is not None, "KV storage not writable!"
    await text_chunks_db.delete("test_id")
    
    # Check 2: Verify VDB storage is writable
    test_vector = np.random.rand(768)
    await chunks_vdb.upsert([{"id": "test", "vector": test_vector}])
    results = await chunks_vdb.query("test", top_k=1)
    assert len(results) > 0, "VDB storage not writable!"
    
    # Check 3: Verify graph storage is writable
    await knowledge_graph_inst.upsert_node("test_node", {"test": "data"})
    node = await knowledge_graph_inst.get_node("test_node")
    assert node is not None, "Graph storage not writable!"
    
    print("✅ All storage backends validated")
```

#### B. Post-Upload Validation

**After processing documents:**

```python
async def validate_chunk_consistency():
    """Ensure chunks are stored in BOTH VDB and KV storage"""
    
    # Get counts from both storages
    vdb_count = await chunks_vdb.count()
    kv_count = await text_chunks_db.count()
    
    # They should match (or KV should have at least 90% of VDB)
    if kv_count < vdb_count * 0.9:
        raise ValueError(
            f"Chunk storage mismatch! "
            f"VDB has {vdb_count} chunks but KV only has {kv_count}. "
            f"This will break hybrid/local/global modes!"
        )
    
    # Verify entity references are valid
    entities = await knowledge_graph_inst.get_all_nodes()
    invalid_refs = 0
    
    for entity in entities[:100]:  # Sample check
        source_id = entity.get("source_id", "")
        chunk_ids = source_id.split("<SEP>")
        
        for chunk_id in chunk_ids:
            chunk = await text_chunks_db.get(chunk_id)
            if chunk is None:
                invalid_refs += 1
    
    if invalid_refs > 10:
        raise ValueError(
            f"Found {invalid_refs} invalid chunk references in knowledge graph! "
            f"Entities reference chunks that don't exist in text_chunks_db."
        )
    
    print(f"✅ Chunk consistency validated: {kv_count} chunks in both storages")
```

#### C. Sync Validation Script

**For GPU → CPU sync:**

```bash
#!/bin/bash
# validate_sync.sh - Run after syncing data from GPU to CPU

echo "🔍 Validating data sync..."

# Check PostgreSQL tables
echo "Checking PostgreSQL tables..."
VDB_COUNT=$(docker exec postgres_rag psql -U raguser -d ragdb -t -c \
  "SELECT COUNT(*) FROM lightrag_vdb_chunks WHERE workspace='default';")
KV_COUNT=$(docker exec postgres_rag psql -U raguser -d ragdb -t -c \
  "SELECT COUNT(*) FROM lightrag_doc_chunks WHERE workspace='default';")

echo "  lightrag_vdb_chunks: $VDB_COUNT"
echo "  lightrag_doc_chunks: $KV_COUNT"

if [ "$KV_COUNT" -lt "$((VDB_COUNT * 9 / 10))" ]; then
    echo "❌ ERROR: KV storage has too few chunks!"
    echo "   This will break hybrid mode. Run fix_hybrid_populate_chunks.py"
    exit 1
fi

# Check NetworkX graph
echo "Checking NetworkX graph..."
GRAPH_SIZE=$(docker exec raganything stat -f%z /app/rag_storage/default/graph_chunk_entity_relation.graphml 2>/dev/null || echo "0")
if [ "$GRAPH_SIZE" -lt 100000 ]; then
    echo "❌ ERROR: Graph file is too small or missing!"
    exit 1
fi

# Check entity-chunk references
echo "Checking entity-chunk references..."
docker exec raganything python3 << 'EOF'
import networkx as nx
G = nx.read_graphml('/app/rag_storage/default/graph_chunk_entity_relation.graphml')
nodes = list(G.nodes(data=True))
sample = nodes[:10]
missing = sum(1 for _, data in sample if not data.get('source_id'))
print(f"  Sample check: {len(sample)-missing}/{len(sample)} entities have source_id")
if missing > 2:
    print("❌ ERROR: Too many entities missing source_id!")
    exit(1)
EOF

echo "✅ Sync validation passed!"
```

---

## 4. Should we add a health check that verifies both tables have matching data?

### Yes, absolutely! Here's the implementation:

#### Health Check Script

**Location:** `/root/monitoring/health_check_hybrid.sh`

```bash
#!/bin/bash
# Health check for hybrid mode chunk retrieval
# Verifies that text_chunks_db and chunks_vdb are in sync

set -e

echo "🔍 Hybrid Mode Health Check"
echo "================================"

# 1. Check chunk counts
VDB_COUNT=$(docker exec postgres_rag psql -U raguser -d ragdb -t -c \
  "SELECT COUNT(*) FROM lightrag_vdb_chunks WHERE workspace='default';" | tr -d ' ')

KV_COUNT=$(docker exec postgres_rag psql -U raguser -d ragdb -t -c \
  "SELECT COUNT(*) FROM lightrag_doc_chunks WHERE workspace='default';" | tr -d ' ')

echo "Chunk counts:"
echo "  VDB (vector search): $VDB_COUNT"
echo "  KV (text storage):   $KV_COUNT"

# 2. Validate counts match (within 10% tolerance)
MIN_EXPECTED=$((VDB_COUNT * 9 / 10))

if [ "$KV_COUNT" -lt "$MIN_EXPECTED" ]; then
    echo "❌ CRITICAL: KV storage has too few chunks!"
    echo "   Expected at least $MIN_EXPECTED, got $KV_COUNT"
    echo "   Hybrid mode will return 0 chunks!"
    echo ""
    echo "🔧 Fix: Run /root/RAG-Anything/fix_hybrid_populate_chunks.py"
    exit 1
fi

# 3. Test hybrid mode query
echo ""
echo "Testing hybrid mode query..."
RESULT=$(docker exec raganything python3 -c "
import requests
import sys

try:
    login = requests.post('http://localhost:9621/login',
        data={'username': 'admin', 'password': 'your-secure-password'},
        timeout=10)
    token = login.json()['access_token']
    
    resp = requests.post('http://localhost:9621/query',
        headers={'Authorization': f'Bearer {token}'},
        json={'query': 'What is desulphation?', 'mode': 'hybrid'},
        timeout=30)
    
    answer = resp.json().get('response', '')
    print(len(answer))
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" 2>&1)

if [ $? -eq 0 ] && [ "$RESULT" -gt 200 ]; then
    echo "✅ Hybrid mode query successful ($RESULT chars)"
else
    echo "❌ Hybrid mode query failed or returned empty response"
    echo "   Result: $RESULT"
    exit 1
fi

# 4. Check for missing chunk references
echo ""
echo "Checking entity-chunk reference integrity..."
MISSING_REFS=$(docker exec postgres_rag psql -U raguser -d ragdb -t -c "
WITH all_entity_chunks AS (
    SELECT DISTINCT unnest(chunk_ids) as chunk_id
    FROM lightrag_vdb_entity 
    WHERE workspace='default' AND chunk_ids IS NOT NULL
    LIMIT 100
),
missing_chunks AS (
    SELECT aec.chunk_id
    FROM all_entity_chunks aec
    LEFT JOIN lightrag_doc_chunks c ON c.id = aec.chunk_id AND c.workspace = 'default'
    WHERE c.id IS NULL
)
SELECT COUNT(*) FROM missing_chunks;
" | tr -d ' ')

if [ "$MISSING_REFS" -gt 10 ]; then
    echo "⚠️  WARNING: Found $MISSING_REFS missing chunk references (sample of 100)"
    echo "   Some entities reference chunks that don't exist in KV storage"
else
    echo "✅ Chunk reference integrity OK ($MISSING_REFS missing in sample)"
fi

echo ""
echo "================================"
echo "✅ Hybrid mode health check PASSED"
```

#### Integration with Monitoring

**Add to crontab:**

```bash
# Run hybrid mode health check every hour
0 * * * * /root/monitoring/health_check_hybrid.sh >> /var/log/hybrid_health.log 2>&1
```

**Add to main health check:**

```bash
# In /root/monitoring/health_check.sh, add:

echo ""
echo "🔍 Checking hybrid mode..."
/root/monitoring/health_check_hybrid.sh || echo "⚠️  Hybrid mode health check failed!"
```

---

## Summary of Preventive Measures

| Measure | When | Purpose |
|---------|------|---------|
| **Pre-upload validation** | Before ingestion | Ensure all storage backends are writable |
| **Post-upload validation** | After ingestion | Verify chunks in both VDB and KV storage |
| **Sync validation script** | After GPU→CPU sync | Confirm data integrity after transfer |
| **Hourly health check** | Continuous monitoring | Detect issues before users report them |
| **Startup validation** | Container restart | Catch configuration issues early |

---

## Lessons Learned

1. **Multi-storage architectures are fragile** - If one storage layer fails silently, the system appears to work but specific features break

2. **Validation is critical** - Always verify data consistency across storage backends, especially after sync operations

3. **Test all query modes** - Don't assume that if one mode works, all modes work

4. **Monitor chunk retrieval** - Log and alert on "0 chunks retrieved" scenarios

5. **Document storage dependencies** - Make it clear which modes depend on which storage backends

---

## Technical Debt Identified

1. **No automatic validation** during document ingestion
2. **Silent failures** in KV storage writes
3. **No health checks** for hybrid mode specifically
4. **Unclear error messages** when chunks are missing
5. **No monitoring** of chunk retrieval success rates

---

## Action Items (Completed)

- [x] Populate `lightrag_doc_chunks` from `lightrag_vdb_chunks`
- [x] Verify hybrid mode retrieves chunks correctly
- [x] Test with sample queries
- [x] Document root cause and prevention measures

## Action Items (Recommended)

- [ ] Implement pre-upload validation script
- [ ] Implement post-upload validation script
- [ ] Create sync validation script for GPU→CPU transfers
- [ ] Add hybrid mode health check to monitoring
- [ ] Add startup validation to raganything container
- [ ] Improve error messages for missing chunks
- [ ] Add metrics/logging for chunk retrieval rates

---

**Document Owner:** Asim (Intern)  
**Reviewed By:** N/A  
**Next Review Date:** After next document upload





