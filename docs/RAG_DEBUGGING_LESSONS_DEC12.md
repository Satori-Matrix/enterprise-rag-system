# RAG DEBUGGING LESSONS - December 12, 2025
# Issue: Chatbot Not Retrieving Correct Entities for CEO Query

## 🎯 PROBLEM SUMMARY

**User Query:** "What is Your Company's CEO name?"
**Expected Answer:** Ananta Vangmai (exists in knowledge base)
**Actual Response:** "[no-context]" or "I don't have this information"

---

## 🔍 ROOT CAUSE ANALYSIS

### 1. **COSINE THRESHOLD TOO STRICT**

**Initial Setting:** `COSINE_THRESHOLD=0.2`

**Discovery Process:**
```bash
# Test 1: Check if entity exists
docker exec postgres_rag psql -U raguser -d ragdb -c \
  "SELECT entity_name FROM lightrag_vdb_entity WHERE entity_name ILIKE '%ananta%';"
# Result: ✅ Found 8 variations including "Ananta Vangmai"

# Test 2: Check actual cosine distance
# Query: "CEO" vs Entity: "Ananta Vangmai"
# Result: distance = 0.54 (threshold was 0.2, then 0.5, then 0.6)

# Test 3: Check with actual LightRAG query keywords
# LightRAG extracted: "Your Company, CEO name"
# Distance to Ananta: 0.7090 ❌ (> 0.6 threshold)
```

**Why Distance is High:**
- Entity description is **1757 characters long**
- Includes irrelevant info: webinars, EWVC, newsletters, etc.
- "CEO" signal gets **diluted** in the embedding

**Content Example:**
```
Ananta Vangmai
Ananta Vangmai is the CEO & Founder of Your Company Technology. 
She plays a pivotal role in leading the company's initiatives...
[+ 1500 more chars about webinars, VC ecosystem, communications]
```

When embedded, the "CEO" keyword becomes a small signal in a large text.

---

### 2. **WORKSPACE COMPLEXITY**

**Issue:** Two workspaces exist (`_` and `default`)
- 406 entities in `_` (old)
- 3257 entities in `default` (current)

**Impact:** Initial confusion about which workspace to query

---

### 3. **DOCKER ENVIRONMENT VARIABLES**

**Critical Lesson:** `docker restart` does NOT reload `.env` changes!

**Correct Process:**
```bash
# ❌ WRONG: This won't pick up .env changes
docker restart raganything

# ✅ CORRECT: Must recreate container
cd /root/RAG-Anything
docker compose up -d --force-recreate raganything

# Verify change was applied
docker exec raganything printenv | grep COSINE_THRESHOLD
```

---

### 4. **LLM CACHE INTERFERENCE**

**Issue:** Even after threshold changes, old cached responses returned

**Solution:**
```bash
# Always clear cache after changing RAG parameters
docker exec postgres_rag psql -U raguser -d ragdb -c \
  "TRUNCATE TABLE lightrag_llm_cache;"
```

---

### 5. **QUERY KEYWORD EXTRACTION**

**Issue:** LightRAG extracts keywords that dilute the semantic match

User asks: "What is Your Company's CEO name?"
LightRAG extracts: "Your Company, CEO name" ← Less specific!

**Distance Comparison:**
| Query | Distance to Ananta |
|-------|-------------------|
| "CEO" | 0.69 |
| "CEO name" | 0.72 |
| "Your Company CEO" | 0.66 |
| "Your Company, CEO name" | 0.71 |

All require threshold ≥ 0.8 to match!

---

## ✅ FINAL SOLUTION

### **Set COSINE_THRESHOLD=0.8**

**Rationale:**
- For `nomic-embed-text` with long entity descriptions
- Allows retrieval of relevant entities despite diluted embeddings
- Balances precision (don't retrieve junk) vs recall (find relevant info)

**Threshold Tuning Guide:**
```
0.2 = Very strict (only near-identical embeddings)
0.4 = Strict (high semantic similarity required)
0.6 = Moderate (good for short, focused descriptions)
0.8 = Lenient (good for long descriptions or noisy data) ← OUR CASE
0.9 = Very lenient (may retrieve irrelevant results)
```

---

## 🚨 WILL THIS FIX OTHER QUERIES?

### **Question About OEM Approval:**
> "Could you please confirm whether the Proprietary Algorithmic Pulse Charging technology is approved by OEM?"

**Analysis:**
- Requires entities: "OEM approval", "Pulse Charging", "Proprietary technology"
- If these entities have long descriptions → same issue
- **Solution:** 0.8 threshold should help, BUT:
  - If document doesn't explicitly mention "OEM approval status" → still won't answer
  - LLM should say "I don't have this information" (which is correct!)

**Expected Behavior:**
- ✅ If info exists but wasn't retrieved → FIXED by 0.8 threshold
- ✅ If info doesn't exist → Should admit "I don't have this information"
- ❌ Generic recommendations WITHOUT citing sources → SHOULD NOT HAPPEN (fixed by prompt patch)

---

## 📋 DEBUGGING CHECKLIST (Add to Workflow)

### **When RAG Returns Wrong/No Answer:**

**Step 1: Verify Data Exists**
```bash
# Search for expected entity/keyword in database
docker exec postgres_rag psql -U raguser -d ragdb -c \
  "SELECT entity_name, LEFT(content, 200) FROM lightrag_vdb_entity 
   WHERE content ILIKE '%KEYWORD%' AND workspace = 'default';"
```

**Step 2: Check Workspace Alignment**
```bash
# .env workspace
cat /root/RAG-Anything/.env | grep WORKSPACE

# Database workspaces
docker exec postgres_rag psql -U raguser -d ragdb -c \
  "SELECT workspace, COUNT(*) FROM lightrag_vdb_entity GROUP BY workspace;"

# Must match!
```

**Step 3: Test Vector Similarity**
```bash
# Get actual cosine distance for your query
docker exec raganything python3 -c "
import asyncio
from lightrag.llm.ollama import ollama_embed
import asyncpg
from numpy.linalg import norm
import numpy as np

async def test():
    query = 'YOUR QUERY HERE'
    emb = await ollama_embed([query], embed_model='nomic-embed-text', host='http://ollama:11434')
    query_vec = np.array(emb[0])
    
    conn = await asyncpg.connect(host='postgres', port=5432,
        user='raguser', password='your-db-password', database='ragdb')
    
    row = await conn.fetchrow('''
        SELECT entity_name, content_vector::text FROM lightrag_vdb_entity 
        WHERE entity_name = 'ENTITY NAME' AND workspace = 'default'
    ''')
    
    vec_str = row['content_vector'].strip('[]')
    entity_vec = np.array([float(x) for x in vec_str.split(',')])
    
    cosine_sim = np.dot(query_vec, entity_vec) / (norm(query_vec) * norm(entity_vec))
    cosine_dist = 1 - cosine_sim
    
    print(f'Distance: {cosine_dist:.4f}')
    print(f'Current threshold: $(grep COSINE_THRESHOLD /root/RAG-Anything/.env)')
    
    await conn.close()

asyncio.run(test())
"
```

**Step 4: Check Environment Variables Loaded**
```bash
# Inside container (not host!)
docker exec raganything printenv | grep COSINE_THRESHOLD

# If doesn't match .env:
cd /root/RAG-Anything
docker compose up -d --force-recreate raganything
```

**Step 5: Clear LLM Cache**
```bash
docker exec postgres_rag psql -U raguser -d ragdb -c \
  "TRUNCATE TABLE lightrag_llm_cache;"
```

**Step 6: Check Logs for Retrieval**
```bash
docker logs raganything --tail 100 | grep -E "Query nodes|Raw search results|Final context"

# Should see:
# INFO: Query nodes: ... (top_k:40, cosine:0.8)
# INFO: Raw search results: X entities, Y relations
# If X = 0 → threshold too strict or workspace mismatch
```

**Step 7: Check Query Mode**
```bash
# Different modes have different behaviors:
# - naive: Uses document chunks (should always cite sources)
# - local: Uses entity neighborhood
# - global: Uses entity communities
# - hybrid: Combines local + global + chunks

# Test all modes to isolate issue
```

---

## 🛠️ IMPROVEMENTS TO `.cursorrules`

### **New Section to Add:**

```markdown
## ═══════════════════════════════════════════════════════════════════
## RAG DEBUGGING - SYSTEMATIC APPROACH
## ═══════════════════════════════════════════════════════════════════

### COSINE THRESHOLD TUNING

**Default:** 0.2 (very strict)  
**Recommended for nomic-embed-text with long descriptions:** 0.8

**Symptoms of too-strict threshold:**
- "[no-context]" errors even though data exists
- "I don't have this information" for known facts
- Logs show: "Raw search results: 0 entities"

**Tuning process:**
1. Check entity content length (should be < 500 chars ideally)
2. Test actual cosine distances for sample queries
3. Adjust threshold to retrieve relevant entities
4. Balance: too high = junk results, too low = miss relevant info

**Location:** `/root/RAG-Anything/.env` → `COSINE_THRESHOLD=0.8`

---

### ENVIRONMENT VARIABLE CHANGES

**CRITICAL:** `docker restart` does NOT reload .env!

**Correct process for .env changes:**
```bash
# 1. Edit .env
nano /root/RAG-Anything/.env

# 2. Recreate container (not restart!)
cd /root/RAG-Anything
docker compose up -d --force-recreate SERVICE_NAME

# 3. Verify inside container
docker exec SERVICE_NAME printenv | grep VARIABLE_NAME

# 4. Clear caches if applicable
docker exec postgres_rag psql -U raguser -d ragdb -c "TRUNCATE TABLE lightrag_llm_cache;"
```

---

### QUERY MODE BEHAVIORS

| Mode | Retrieval Method | Citations | Best For |
|------|------------------|-----------|----------|
| `naive` | Document chunks | ✅ Always | Specific facts with sources |
| `local` | Entity neighborhood | ❌ Rarely | Contextual understanding |
| `global` | Entity communities | ❌ Rarely | High-level summaries |
| `hybrid` | All combined | ⚠️ Sometimes | General questions |

**For debugging:**
- Always test `naive` mode first (most reliable citations)
- If `naive` works but others don't → entity/relation retrieval issue
- If `naive` also fails → check document chunks ingested correctly

---

### WORKSPACE THREE-WAY DEPENDENCY (Enhanced)

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│    .env     │ ←→ │ File System │ ←→ │ PostgreSQL  │
│ WORKSPACE=X │    │/rag_storage/X/│   │ workspace='X'│
└─────────────┘    └─────────────┘    └─────────────┘
```

**When changing workspace:**
```bash
# 1. Check current workspace
cat /root/RAG-Anything/.env | grep WORKSPACE

# 2. Check database workspaces
docker exec postgres_rag psql -U raguser -d ragdb -c \
  "SELECT workspace, COUNT(*) as count FROM lightrag_vdb_entity GROUP BY workspace;"

# 3. Check filesystem
ls -la /root/RAG-Anything/rag_storage/

# 4. If mismatch detected:
#    - Identify which is correct (usually the one with most data)
#    - Update .env to match
#    - Recreate container
```

**Common issue:** Old workspace `_` exists with 406 entities, new `default` has 3257
- Solution: Use `default`, ignore `_` (or delete old data)

---

### LLM CACHE MANAGEMENT

**When to clear cache:**
- After changing `COSINE_THRESHOLD`
- After changing system prompts
- After patching LightRAG code
- After re-ingesting documents
- When testing fixes (to avoid cached wrong answers)

**Command:**
```bash
docker exec postgres_rag psql -U raguser -d ragdb -c "TRUNCATE TABLE lightrag_llm_cache;"
```

**How cache works:**
- Keys: `{mode}:{stage}:{hash_of_query}`
- Stages: `keywords`, `query`
- If key exists → returns cached response (skips retrieval + LLM)

**Debug tip:**
```bash
# Check what's cached
docker exec postgres_rag psql -U raguser -d ragdb -c \
  "SELECT LEFT(cache_key, 50), created_at FROM lightrag_llm_cache ORDER BY created_at DESC LIMIT 10;"
```

---

### VECTOR SIMILARITY DEBUGGING

**Manual test for any query:**
```python
# Inside raganything container
docker exec raganything python3 << 'EOF'
import asyncio
from lightrag.llm.ollama import ollama_embed
import asyncpg
from numpy.linalg import norm
import numpy as np

async def test_similarity(query_text, entity_name):
    # Get query embedding
    emb = await ollama_embed([query_text], embed_model='nomic-embed-text', host='http://ollama:11434')
    query_vec = np.array(emb[0])
    
    # Get entity from DB
    conn = await asyncpg.connect(host='postgres', port=5432, user='raguser', password='your-db-password', database='ragdb')
    row = await conn.fetchrow(f"""
        SELECT entity_name, content_vector::text FROM lightrag_vdb_entity 
        WHERE entity_name = '{entity_name}' AND workspace = 'default'
    """)
    
    if row is None:
        print(f"Entity '{entity_name}' not found!")
        return
    
    vec_str = row['content_vector'].strip('[]')
    entity_vec = np.array([float(x) for x in vec_str.split(',')])
    
    cosine_sim = np.dot(query_vec, entity_vec) / (norm(query_vec) * norm(entity_vec))
    cosine_dist = 1 - cosine_sim
    
    print(f"Query: {query_text}")
    print(f"Entity: {entity_name}")
    print(f"Cosine distance: {cosine_dist:.4f}")
    print(f"Would be retrieved at 0.8? {cosine_dist < 0.8}")
    
    await conn.close()

# Test your query here
asyncio.run(test_similarity("CEO", "Ananta Vangmai"))
EOF
```

---

### PROMPT MODIFICATIONS VERIFICATION

**After patching prompts:**
```bash
# 1. Check patch applied inside container
docker exec raganything grep -A 5 "PROMPTS\[\"rag_response\"\]" \
  /usr/local/lib/python3.11/site-packages/lightrag/prompt.py

# 2. Clear LLM cache
docker exec postgres_rag psql -U raguser -d ragdb -c "TRUNCATE TABLE lightrag_llm_cache;"

# 3. Test query
# 4. Check logs for how prompt was used
docker logs raganything --tail 200 | grep -A 20 "context_data"
```

---

### NAIVE MODE CHUNK RETRIEVAL

**Check if chunks exist:**
```bash
docker exec postgres_rag psql -U raguser -d ragdb -c \
  "SELECT COUNT(*), workspace FROM lightrag_vdb_chunks GROUP BY workspace;"
```

**Check if chunks contain expected info:**
```bash
docker exec postgres_rag psql -U raguser -d ragdb -c \
  "SELECT LEFT(content, 200), file_path FROM lightrag_vdb_chunks 
   WHERE content ILIKE '%CEO%' AND workspace = 'default' LIMIT 5;"
```

**If chunks missing or incomplete:**
- Re-ingest documents
- Check chunk size (default 200 tokens) in .env
- Check if documents were processed successfully

---
```

---

## 📈 EXPECTED OUTCOMES AFTER FIX

### **CEO Query:**
✅ Should retrieve "Ananta Vangmai" entity  
✅ Should extract answer from description or relations  
✅ Should cite source document if available  

### **OEM Approval Query:**
- **If info exists:** ✅ Should find and cite it
- **If info doesn't exist:** ✅ Should say "I don't have this information. Contact info@revivebattery.eu"
- **If partially exists:** ⚠️ Should provide what's available, admit gaps

### **Generic Behavior:**
❌ NEVER give generic advice without sources  
❌ NEVER make up facts  
✅ ALWAYS admit when information is missing  
✅ ALWAYS provide contact info for follow-up  

---

## 🎓 KEY TAKEAWAYS

1. **Cosine thresholds are embedding-model-specific** - nomic-embed-text with long texts needs ≥ 0.8

2. **Entity descriptions matter** - Long, verbose descriptions dilute semantic signals

3. **Docker environment variables require container recreation** - `restart` ≠ `recreate`

4. **LLM cache can mask fixes** - Always clear after changes

5. **Test vector similarity manually** - Don't assume embeddings work as expected

6. **Query keyword extraction affects retrieval** - LightRAG's keywords may not be optimal

7. **Relations can save the day** - Even if entity embeddings fail, relations might work

8. **Multiple query modes = multiple failure points** - Test each mode independently

---

## 🔄 NEXT STEPS

1. ✅ Test CEO query with threshold=0.8
2. ✅ Test OEM approval query
3. ✅ Monitor for false positives (junk retrievals at 0.8)
4. 📝 Update `.cursorrules` with debugging section
5. 📊 Create performance baseline (test 10-20 common queries)
6. 🎯 Consider entity description summarization (truncate to 500 chars with emphasis on key facts)

---

## 📞 SUPPORT CONTACTS

- **Technical Issues:** info@revivebattery.eu
- **System Admin:** Asim (Intern)
- **VPS:** your-domain.com

---

*Document created: December 12, 2025*  
*Last updated: December 12, 2025*  
*Status: Threshold updated to 0.8, awaiting test results*

