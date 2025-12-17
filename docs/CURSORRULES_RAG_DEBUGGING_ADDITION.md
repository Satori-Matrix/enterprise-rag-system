# ADDITION TO .cursorrules - RAG DEBUGGING SECTION

**Location:** Add this after the "LESSONS LEARNED (FROM PAST MISTAKES)" section

---

## ═══════════════════════════════════════════════════════════════════
## RAG DEBUGGING - SYSTEMATIC APPROACH
## ═══════════════════════════════════════════════════════════════════

### COSINE THRESHOLD TUNING

**Current Setting:** `COSINE_THRESHOLD=0.8` (as of Dec 12, 2025)

**Why 0.8?**
- Entity descriptions are long (500-2000 chars)
- "CEO" signal gets diluted in verbose text
- `nomic-embed-text` model requires higher threshold for long texts

**Threshold Guide:**
```
0.2 = Very strict (only near-identical) - DEFAULT but TOO STRICT for us
0.4 = Strict (high similarity required)
0.6 = Moderate (good for short descriptions)
0.8 = Lenient (good for long descriptions) ← OUR SETTING
0.9 = Very lenient (may retrieve irrelevant)
```

**Symptoms of wrong threshold:**

| Issue | Too Low (< 0.6) | Too High (> 0.9) |
|-------|----------------|------------------|
| Logs | "Raw search results: 0 entities" | "Raw search results: 500+ entities" |
| Response | "[no-context]" | Generic/off-topic answers |
| Fix | Increase to 0.8 | Decrease to 0.7 |

**Testing process:**
```bash
# 1. Check entity exists
docker exec postgres_rag psql -U raguser -d ragdb -c \
  "SELECT entity_name, LEFT(content, 100) FROM lightrag_vdb_entity 
   WHERE content ILIKE '%KEYWORD%' AND workspace = 'default';"

# 2. Test similarity manually (see VECTOR SIMILARITY DEBUGGING section)

# 3. Adjust threshold in .env
nano /root/RAG-Anything/.env  # Edit COSINE_THRESHOLD=X

# 4. Recreate container (NOT restart!)
cd /root/RAG-Anything && docker compose up -d --force-recreate raganything

# 5. Clear cache
docker exec postgres_rag psql -U raguser -d ragdb -c "TRUNCATE TABLE lightrag_llm_cache;"

# 6. Test query and check logs
docker logs raganything --tail 50 | grep "Raw search results"
```

---

### ENVIRONMENT VARIABLE CHANGES - CRITICAL WORKFLOW

**❌ WRONG (doesn't reload .env):**
```bash
docker restart raganything  # Container keeps OLD env vars!
```

**✅ CORRECT (reloads .env):**
```bash
# 1. Edit .env
nano /root/RAG-Anything/.env

# 2. Recreate container
cd /root/RAG-Anything
docker compose up -d --force-recreate raganything

# 3. Verify change took effect
docker exec raganything printenv | grep VARIABLE_NAME

# 4. If RAG-related, clear cache
docker exec postgres_rag psql -U raguser -d ragdb -c "TRUNCATE TABLE lightrag_llm_cache;"
```

**Why this happens:**
- Docker containers capture env vars at creation time
- `restart` reuses existing container → keeps old env
- `--force-recreate` makes new container → loads new env

**Checklist for ANY .env change:**
- [ ] Container recreated (not restarted)
- [ ] Env var verified inside container
- [ ] Cache cleared if affects queries/prompts
- [ ] Service restarted if needed (e.g., chainlit_revive)

---

### WORKSPACE THREE-WAY DEPENDENCY (ENHANCED)

**Original rule still applies:**
```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│    .env     │ ←→ │ File System │ ←→ │ PostgreSQL  │
│ WORKSPACE=X │    │/rag_storage/X/│   │ workspace='X'│
└─────────────┘    └─────────────┘    └─────────────┘
```

**New: Multiple workspaces can exist in DB!**

Common scenario:
- Old data in workspace `_` (406 entities)
- New data in workspace `default` (3257 entities)
- .env set to `default` ← Correct

**Diagnosis:**
```bash
# 1. Check .env
cat /root/RAG-Anything/.env | grep WORKSPACE

# 2. Check DB workspaces
docker exec postgres_rag psql -U raguser -d ragdb -c \
  "SELECT workspace, 
          COUNT(*) as entities,
          MAX(create_time) as last_updated
   FROM lightrag_vdb_entity 
   GROUP BY workspace 
   ORDER BY entities DESC;"

# 3. Check filesystem
ls -la /root/RAG-Anything/rag_storage/

# 4. If mismatch:
#    - Use workspace with MOST entities and LATEST updates
#    - Update .env to match
#    - Recreate container
```

**Decision matrix:**

| Scenario | Action |
|----------|--------|
| All 3 match | ✅ No action |
| .env = `default`, DB has both | ✅ Correct (uses `default`) |
| .env = `_`, DB has `default` with more data | ❌ Update .env to `default` |
| Filesystem missing current workspace folder | ❌ Check document ingestion |

---

### LLM CACHE MANAGEMENT

**Cache table:** `lightrag_llm_cache` in `ragdb`

**When to clear (ALWAYS after):**
- Changing `COSINE_THRESHOLD`
- Changing `LLM_MODEL` or `EMBED_MODEL`
- Patching prompt files (prompt.py, query.py)
- Patching LightRAG code (operate.py, lightrag.py)
- Re-ingesting documents
- Testing fixes (to avoid cached wrong answers)

**Command:**
```bash
docker exec postgres_rag psql -U raguser -d ragdb -c "TRUNCATE TABLE lightrag_llm_cache;"
```

**How cache works:**
```
Cache key format: {mode}:{stage}:{hash}
Examples:
- hybrid:keywords:e95a2da... (keyword extraction)
- hybrid:query:cccfeccc2a... (final answer)
- naive:query:256fa613... (naive mode answer)

Stages:
1. keywords → extracts query keywords (e.g., "Your Company, CEO")
2. query → generates final answer with context
```

**Debug cache issues:**
```bash
# See recent cache entries
docker exec postgres_rag psql -U raguser -d ragdb -c \
  "SELECT 
     LEFT(cache_key, 40) as key_prefix,
     mode,
     cache_type,
     created_at
   FROM lightrag_llm_cache 
   ORDER BY created_at DESC 
   LIMIT 10;"

# If answer hasn't changed after fix:
# → Cache hit! Clear it.
```

---

### QUERY MODE BEHAVIORS (DETAILED)

| Mode | Retrieval | Citations | Context Size | Best For | Limitations |
|------|-----------|-----------|--------------|----------|-------------|
| **naive** | Doc chunks | ✅ Always | ~20 chunks | Specific facts | Limited to chunk matches |
| **local** | Entity neighbors | ❌ Rarely | ~40 entities | Relationships | No direct doc refs |
| **global** | Entity communities | ❌ Rarely | ~60 entities | Summaries | Very high-level |
| **hybrid** | All combined | ⚠️ Sometimes | Large | General Q&A | Complex, hard to debug |

**Debugging strategy:**
1. **Always test `naive` first** - most reliable, always has sources
2. **If naive works but hybrid doesn't** → entity/relation retrieval issue
3. **If naive also fails** → document chunks missing or threshold too strict

**Example debugging flow:**
```bash
# Test naive mode (should cite documents)
curl -H "Authorization: Bearer $TOKEN" \
  -X POST http://raganything:9621/query \
  -d '{"query": "What is Your Company CEO?", "mode": "naive"}'

# Check response:
# ✅ Has "references" array with file_path → GOOD
# ❌ "No relevant context" → chunks missing or threshold issue

# Test hybrid mode
curl ... -d '{"query": "...", "mode": "hybrid"}'

# Compare results
```

**Mode selection guide:**
- User wants sources → `naive`
- User wants explanation/context → `hybrid`
- User wants high-level overview → `global`
- Debugging → **always start with `naive`**

---

### VECTOR SIMILARITY DEBUGGING

**Manual test script** (run on host):
```bash
docker exec raganything python3 << 'SCRIPT'
import asyncio
from lightrag.llm.ollama import ollama_embed
import asyncpg
from numpy.linalg import norm
import numpy as np

async def test_similarity(query_text, entity_name):
    # Get query embedding
    emb = await ollama_embed([query_text], 
                            embed_model='nomic-embed-text', 
                            host='http://ollama:11434')
    query_vec = np.array(emb[0])
    
    # Connect to DB
    conn = await asyncpg.connect(
        host='postgres', 
        port=5432, 
        user='raguser', 
        password='your-db-password', 
        database='ragdb'
    )
    
    # Get entity
    row = await conn.fetchrow(f"""
        SELECT entity_name, content, content_vector::text 
        FROM lightrag_vdb_entity 
        WHERE entity_name = '{entity_name}' 
        AND workspace = 'default'
    """)
    
    if row is None:
        print(f"❌ Entity '{entity_name}' not found in 'default' workspace")
        await conn.close()
        return
    
    # Parse vector
    vec_str = row['content_vector'].strip('[]')
    entity_vec = np.array([float(x) for x in vec_str.split(',')])
    
    # Calculate similarity
    cosine_sim = np.dot(query_vec, entity_vec) / (norm(query_vec) * norm(entity_vec))
    cosine_dist = 1 - cosine_sim
    
    # Display results
    print(f"Query: {query_text}")
    print(f"Entity: {entity_name}")
    print(f"Content preview: {row['content'][:150]}...")
    print(f"Cosine distance: {cosine_dist:.4f}")
    print(f"Passes 0.8 threshold? {'✅ YES' if cosine_dist < 0.8 else '❌ NO'}")
    
    await conn.close()

# EDIT THESE:
asyncio.run(test_similarity("CEO", "Ananta Vangmai"))
SCRIPT
```

**Use cases:**
1. Check why entity not retrieved
2. Tune threshold for specific queries
3. Verify embeddings are correct
4. Compare different query formulations

---

### PROMPT MODIFICATIONS - VERIFICATION WORKFLOW

**After patching prompt.py or query.py:**

**Step 1: Verify patch applied**
```bash
# For LightRAG internal prompts
docker exec raganything grep -A 10 "PROMPTS\[\"rag_response\"\]" \
  /usr/local/lib/python3.11/site-packages/lightrag/prompt.py

# Should show your custom prompt, not default
```

**Step 2: Clear LLM cache**
```bash
docker exec postgres_rag psql -U raguser -d ragdb -c "TRUNCATE TABLE lightrag_llm_cache;"
```

**Step 3: Enable debug logging (if needed)**
```bash
# Edit .env
LOG_LEVEL=DEBUG

# Recreate
cd /root/RAG-Anything
docker compose up -d --force-recreate raganything
```

**Step 4: Test and check logs**
```bash
# Send test query via Chainlit or API

# Check if prompt is being used
docker logs raganything --tail 200 | grep -E "context_data|user_prompt|RULES"
```

**Step 5: If prompt ignored:**
- Check if there's a system_prompt override in query.py (remove it!)
- Check if LightRAG is using a different prompt key
- Check if .format() placeholders match

---

### NAIVE MODE - CHUNK RETRIEVAL DEBUGGING

**Symptom:** Naive mode returns "No relevant context" but data exists

**Check 1: Do chunks exist?**
```bash
docker exec postgres_rag psql -U raguser -d ragdb -c \
  "SELECT workspace, COUNT(*) 
   FROM lightrag_vdb_chunks 
   GROUP BY workspace;"
```

**Check 2: Do chunks contain expected keywords?**
```bash
docker exec postgres_rag psql -U raguser -d ragdb -c \
  "SELECT LEFT(content, 200), file_path 
   FROM lightrag_vdb_chunks 
   WHERE content ILIKE '%YOUR_KEYWORD%' 
   AND workspace = 'default' 
   LIMIT 5;"
```

**Check 3: Test chunk vector similarity**
```bash
# Similar to entity test, but query lightrag_vdb_chunks table
# (Use script from VECTOR SIMILARITY DEBUGGING section)
```

**Common issues:**
| Issue | Cause | Fix |
|-------|-------|-----|
| 0 chunks | Documents not ingested | Re-upload via WebUI |
| Chunks exist but wrong workspace | Workspace mismatch | Update .env |
| Chunks exist but no matches | Threshold too strict | Increase COSINE_THRESHOLD |
| Chunks match but no citations | app.py parsing issue | Check `references` extraction |

---

### LOG ANALYSIS - WHAT TO LOOK FOR

**Successful query pattern:**
```
INFO:  == LLM cache == saving: hybrid:keywords:abc123
INFO: Query nodes: Your Company, CEO (top_k:40, cosine:0.8)
INFO: Local query: 40 entities, 124 relations  ← Got entities!
INFO: Query edges: CEO name (top_k:40, cosine:0.8)
INFO: Global query: 61 entities, 40 relations   ← Got more entities!
INFO: Raw search results: 87 entities, 152 relations, 0 vector chunks  ← Good!
INFO: Final context: 87 entities, 152 relations, 0 chunks  ← Context built!
INFO:  == LLM cache == saving: hybrid:query:def456
```

**Failed query pattern (threshold too strict):**
```
INFO: Query nodes: Your Company, CEO (top_k:40, cosine:0.2)  ← Too strict!
INFO: Raw search results: 0 entities, 0 relations, 0 vector chunks  ← Nothing found!
INFO: [kg_query] No query context could be built; returning no-result.  ← Failed!
```

**Failed query pattern (workspace mismatch):**
```
INFO: Query nodes: ... (top_k:40, cosine:0.8)
INFO: Local query: 0 entities, 0 relations  ← Wrong workspace!
INFO: Global query: 0 entities, 0 relations
```

**Key metrics to check:**
- **cosine:** value in logs (should match .env)
- **Local query:** entity/relation count (should be > 0 for most queries)
- **Raw search results:** total retrieved (0 = problem)
- **Final context:** what gets sent to LLM

---

### COMPLETE DEBUGGING CHECKLIST

**When RAG gives wrong/missing answer:**

**□ Step 1: Verify data exists**
```bash
docker exec postgres_rag psql -U raguser -d ragdb -c \
  "SELECT entity_name, LEFT(content, 200) FROM lightrag_vdb_entity 
   WHERE content ILIKE '%EXPECTED_KEYWORD%' 
   AND workspace = 'default' LIMIT 5;"
```

**□ Step 2: Check workspace alignment**
```bash
# .env workspace
cat /root/RAG-Anything/.env | grep WORKSPACE

# DB workspaces with counts
docker exec postgres_rag psql -U raguser -d ragdb -c \
  "SELECT workspace, COUNT(*) FROM lightrag_vdb_entity GROUP BY workspace;"

# Must match!
```

**□ Step 3: Test vector similarity**
```bash
# Use script from VECTOR SIMILARITY DEBUGGING section
# Check if distance < current threshold
```

**□ Step 4: Check threshold setting**
```bash
# In .env
grep COSINE_THRESHOLD /root/RAG-Anything/.env

# Inside container (must match!)
docker exec raganything printenv | grep COSINE_THRESHOLD

# If doesn't match → recreate container
```

**□ Step 5: Check logs for retrieval**
```bash
docker logs raganything --tail 100 | grep -E "Query nodes|Raw search|Final context"

# If "0 entities" → threshold or workspace issue
```

**□ Step 6: Clear cache**
```bash
docker exec postgres_rag psql -U raguser -d ragdb -c "TRUNCATE TABLE lightrag_llm_cache;"
```

**□ Step 7: Test different modes**
```bash
# Naive (should always cite sources)
# Local (entity neighborhood)
# Global (entity communities)
# Hybrid (combination)

# If naive works but others don't → entity retrieval issue
```

**□ Step 8: Check prompt patches**
```bash
docker exec raganything grep -A 5 "PROMPTS\[\"rag_response\"\]" \
  /usr/local/lib/python3.11/site-packages/lightrag/prompt.py

# Should show custom prompt with {context_data}, {user_prompt} placeholders
```

---

### COMMON MISTAKES TO AVOID

| Mistake | Why It Fails | Correct Approach |
|---------|--------------|------------------|
| `docker restart` after .env change | Doesn't reload env | `docker compose up -d --force-recreate` |
| Not clearing cache after fix | Returns old cached answer | `TRUNCATE lightrag_llm_cache` |
| Testing without checking logs | Can't see retrieval | Always check `docker logs` |
| Assuming threshold works universally | Depends on model + data | Test and tune per dataset |
| Patching code without recreating | Old code still running | Recreate container |
| Ignoring workspace in queries | Searches wrong data | Always check workspace alignment |
| Not testing naive mode first | Hard to isolate issue | Start with naive (most reliable) |

---

### MONITORING & MAINTENANCE

**Weekly checks:**
```bash
# 1. Check disk space (RAG uses a lot!)
df -h | grep -E "Filesystem|/dev/sda"

# 2. Check database size
docker exec postgres_rag psql -U raguser -d ragdb -c \
  "SELECT 
     pg_size_pretty(pg_database_size('ragdb')) as db_size,
     (SELECT COUNT(*) FROM lightrag_vdb_entity) as entities,
     (SELECT COUNT(*) FROM lightrag_vdb_chunks) as chunks;"

# 3. Check for errors in logs
docker logs raganything --tail 500 | grep -i "ERROR\|WARNING" | tail -20

# 4. Check cache size (clear if > 1000 entries)
docker exec postgres_rag psql -U raguser -d ragdb -c \
  "SELECT COUNT(*) as cache_entries FROM lightrag_llm_cache;"
```

**Monthly tasks:**
- Review threshold effectiveness (any missed queries?)
- Clean up old workspaces (if any)
- Update documentation with new learnings
- Backup database

---

### ESCALATION PATH

**If after all debugging, RAG still fails:**

1. **Document the issue:**
   - Exact query that fails
   - Expected vs actual response
   - All debugging steps tried
   - Relevant log snippets

2. **Check GitHub issues:**
   - LightRAG: https://github.com/HKUDS/LightRAG/issues
   - RAG-Anything: (check project repo)

3. **Consider workarounds:**
   - Add FAQ for specific question
   - Improve entity descriptions (shorter, more focused)
   - Adjust chunk size for better context

4. **Last resort:**
   - Switch embedding model (e.g., try `mxbai-embed-large`)
   - Re-ingest all documents with better preprocessing
   - Consider hybrid approach (RAG + manual knowledge base)

---

**References:**
- Main debugging guide: `/root/RAG_DEBUGGING_LESSONS_DEC12.md`
- LightRAG source analysis: `/root/LIGHTRAG_CONTEXT_ANALYSIS.md`
- System analysis: `/root/SYSTEM_ANALYSIS_DEC2025.md`

---

*Section added: December 12, 2025*  
*Reason: Systematic debugging approach needed after cosine threshold debugging*  
*Owner: Asim (Intern) + AI Assistant*

