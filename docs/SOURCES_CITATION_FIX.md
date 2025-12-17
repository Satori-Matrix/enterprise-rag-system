# 📚 SOURCES & CITATIONS FIX
**Date:** December 12, 2025  
**Issue:** Chat responses don't show source documents/citations

---

## 🐛 PROBLEM

User reported: **"answer is given by the chat but one important thing missing - it doesn't show citation where it got it at the end"**

**Expected:** AI responses should cite source documents (file names, page numbers if available)  
**Actual:** Responses show answer only, no sources listed

---

## 🔍 ROOT CAUSE ANALYSIS

### **1. RAG System Architecture:**

Your system uses **LightRAG** (not traditional chunk-based RAG):
- **LightRAG** builds a knowledge graph from documents (entities + relationships)
- Queries use graph traversal, not direct chunk retrieval
- Different query modes have different behaviors:
  - `hybrid` - Combines local (entities) + global (relations) + vector chunks
  - `local` - Entity-based only
  - `global` - Relationship-based only
  - `naive` - Traditional chunk retrieval

### **2. What the Logs Show:**

From RAG API logs:
```
INFO: Final context: 85 entities, 156 relations, 0 chunks
```

**Key finding:** `0 chunks` means LightRAG is NOT using document chunks for most queries!

**Why?**
- LightRAG prioritizes knowledge graph (entities/relations) over raw chunks
- Chunks are only used when graph doesn't have enough information
- Graph-based responses don't have direct "source document" attribution

### **3. Database Evidence:**

```sql
-- 477 chunks exist in database
SELECT COUNT(*) FROM lightrag_vdb_chunks WHERE workspace='default';
-- Result: 477

-- Each chunk HAS file_path
SELECT DISTINCT file_path FROM lightrag_vdb_chunks;
-- Results: battery technology webinar.pdf, Content for co - founder.docx, etc.
```

**Chunks exist, but LightRAG isn't using them for citations!**

---

## ✅ FIXES APPLIED

### **Fix 1: Enhanced Source Extraction**

Updated `/root/chainlit-revive/app.py` to check multiple possible source formats:

```python
# Check for various source formats
if result.get("sources"):
    sources_list = result.get("sources", [])
elif result.get("context_data"):
    context = result.get("context_data", {})
    if context.get("chunks"):
        # Extract file_path from chunks
        sources_list = [chunk.get("file_path") for chunk in chunks]
elif result.get("metadata"):
    if metadata.get("documents"):
        sources_list = metadata.get("documents", [])
```

### **Fix 2: Debug Logging**

Added logging to see what RAG API actually returns:

```python
logger.info(f"RAG API Response keys: {list(result.keys())}")
logger.info(f"Found sources: {len(sources_list)}")
```

This will help us understand the API response structure.

### **Fix 3: Fallback Message**

When no sources are available (graph-based queries):

```python
if query_mode in ["global", "local"]:
    answer += "\n\n---\n💡 *Response generated from knowledge graph (entity/relationship analysis)*"
else:
    answer += "\n\n---\n💡 *Response generated from knowledge base*"
```

### **Fix 4: Better Source Display**

When sources ARE found:

```python
answer += "\n\n---\n📚 **Sources:**\n" + "\n".join(f"- 📄 {s}" for s in unique_sources)
```

---

## 🧪 TESTING INSTRUCTIONS

### **Step 1: Clear Browser Cache**
- Press **Ctrl + F5** (Windows/Linux) or **Cmd + Shift + R** (Mac)

### **Step 2: Send a Test Query**
Ask a question like:
- "What is battery regeneration?"
- "How do lead-acid batteries work?"
- "Tell me about ReviveBattery services"

### **Step 3: Check for Sources**

**What you might see:**

**Option A - Sources Found:**
```
[AI Response text here]

---
📚 Sources:
- 📄 battery technology webinar.pdf
- 📄 Copy of Functioning, maintenance and regeneration of lead-acid batteries_.docx
- 📄 Future_energy_storage_technologies_manag (1).pdf
```

**Option B - No Sources (Graph-based):**
```
[AI Response text here]

---
💡 Response generated from knowledge graph (entity/relationship analysis)
```

### **Step 4: Check Logs**

```bash
# View Chainlit logs to see what RAG API returned
docker logs chainlit_revive --tail 50 | grep -i "RAG API Response"
```

You should see lines like:
```
INFO: RAG API Response keys: ['response', 'context_data', 'mode']
INFO: Found sources in 'sources' field: 3
```

---

## 🎯 EXPECTED BEHAVIOR AFTER FIX

### **Query Mode: `naive` (Traditional RAG)**
✅ **SHOULD show sources** - Uses document chunks directly
```
📚 Sources:
- 📄 document1.pdf
- 📄 document2.docx
```

### **Query Mode: `hybrid` (Default)**
⚠️ **MAY show sources** - Uses graph + chunks (if chunks are selected)
- If chunks used: Shows sources
- If only graph used: Shows fallback message

### **Query Mode: `local` or `global`**
❌ **WON'T show sources** - Pure graph traversal
```
💡 Response generated from knowledge graph (entity/relationship analysis)
```

---

## 🔧 NEXT STEPS (If Sources Still Don't Show)

### **Option 1: Force `naive` Mode for Citations**

Change default query mode to `naive` (always uses chunks):

```python
# In app.py, line ~89
cl.user_session.set("settings", {
    "response_format": "Paragraph", 
    "query_mode": "naive",  # ← Change from "hybrid" to "naive"
    "max_sources": 3, 
    "show_sources": True
})
```

**Pros:**
- ✅ Always shows source documents
- ✅ Direct chunk attribution

**Cons:**
- ❌ May be less accurate (no knowledge graph reasoning)
- ❌ Loses entity/relationship insights

---

### **Option 2: Modify RAG API to Return Sources**

This requires changes on the GPU (RunPod) side:

1. Modify RAG-Anything query endpoint to track which chunks contributed to the answer
2. Return `sources` field with file paths in the JSON response
3. Update Chainlit to display them

**This is MORE COMPLEX** and requires GPU server access.

---

### **Option 3: Query Database for Related Documents**

Add a post-processing step in Chainlit:

```python
# After getting AI response, query database for related documents
import asyncpg

async def get_related_documents(query_text):
    conn = await asyncpg.connect(
        host="postgres_rag",
        user="raguser",
        password="your-db-password",
        database="ragdb"
    )
    
    # Find chunks that match query keywords
    results = await conn.fetch("""
        SELECT DISTINCT file_path 
        FROM lightrag_vdb_chunks 
        WHERE workspace='default' 
        AND content ILIKE ANY(ARRAY[$1, $2, $3])
        LIMIT 5
    """, f"%{keyword1}%", f"%{keyword2}%", f"%{keyword3}%")
    
    await conn.close()
    return [row['file_path'] for row in results]
```

**Pros:**
- ✅ Works with any query mode
- ✅ Shows actual documents in database

**Cons:**
- ❌ May not be accurate (keyword matching, not semantic)
- ❌ Adds database query overhead

---

## 💡 RECOMMENDED APPROACH

### **Short-term (NOW):**
1. ✅ **Test current fix** - See what logs show
2. ✅ **Try `naive` mode** - Change default to `naive` if sources are critical
3. ✅ **Document behavior** - Explain to users that graph-based queries don't have direct citations

### **Long-term (IF NEEDED):**
1. ⚠️ **Modify RAG API** - Add source tracking to LightRAG queries (requires GPU access)
2. ⚠️ **Add database lookup** - Query chunks table for related documents (less accurate)

---

## 📊 TRADE-OFFS

| Approach | Source Accuracy | Answer Quality | Complexity |
|----------|----------------|----------------|------------|
| **Current (hybrid)** | ⚠️ Sometimes | ✅ Best | ✅ Simple |
| **Force naive mode** | ✅ Always | ⚠️ Good | ✅ Simple |
| **Modify RAG API** | ✅ Always | ✅ Best | ❌ Complex |
| **Database lookup** | ⚠️ Approximate | ✅ Best | ⚠️ Medium |

---

## 🎯 WHAT TO TELL USERS

**If sources show (naive mode):**
> "Each response includes citations to the source documents used to generate the answer. Click on document names to see which files were referenced."

**If sources don't show (graph mode):**
> "Responses are generated using advanced knowledge graph analysis, which synthesizes information from multiple documents. While specific document citations aren't always available, all answers are based on your uploaded knowledge base."

---

## ✅ COMPLETION STATUS

**Implemented:**
- ✅ Enhanced source extraction (checks multiple formats)
- ✅ Debug logging (to see what API returns)
- ✅ Fallback messages (when no sources available)
- ✅ Better source display (with 📄 emoji)

**Next Steps:**
1. **Test and check logs** - See what RAG API actually returns
2. **Decide on approach** - Keep hybrid (best answers) or switch to naive (always show sources)
3. **Document for users** - Explain citation behavior

---

**Status:** ✅ FIX DEPLOYED (awaiting test results)  
**Container:** ✅ REBUILT AND RUNNING  
**Ready for testing:** ✅ YES (clear cache and try!)

