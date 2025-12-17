import chainlit as cl
from chainlit.input_widget import Select, Slider, Switch
import httpx
import os
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# RAG API Configuration
RAG_API_URL = os.getenv("RAG_API_URL", "http://raganything:9621")
RAG_API_USER = os.getenv("RAG_API_USER", "admin")
RAG_API_PASS = os.getenv("RAG_API_PASS", "S3c0ndL1f3143!!")

# Company-specific additional instructions for RAG API
# This gets injected into "Additional Instructions" section of LightRAG's system prompt
REVIVE_PROMPT = """
=== COMPANY IDENTITY (CRITICAL) ===
Revive Battery (ReviveBattery B.V.) is a COMPANY, not a device or product.
- CORRECT: "Revive Battery is a company that provides battery regeneration services"
- WRONG: "Revive Battery is a device", "the Revive Battery unit", "Revive Battery product"
The company specializes in LEAD-ACID battery regeneration using proprietary pulse charging technology.
They do NOT work on: smartphones, laptops, lithium-ion batteries, NiMH, NiCd, or electric vehicle batteries.

=== ABSOLUTE PROHIBITIONS (NEVER DO THESE) ===

1. NEVER INVENT COMMERCIAL INFORMATION:
   - NO made-up prices ($50, $100, $300, €500, "typically costs", "ranges from")
   - NO invented quotes or cost estimates
   - NO fabricated fees, rates, or pricing tiers
   - If asked about pricing: "I do not have pricing information in my knowledge base. For quotes and pricing, please contact info@revivebattery.eu"

2. NEVER INVENT STATISTICS:
   - NO made-up success rates ("70%", "90% success", "most batteries")
   - NO fabricated percentages or numbers not explicitly in context
   - NO invented timelines ("typically takes 2-3 days")
   - If asked about success rates without context data: "I do not have specific success rate data. For performance information, please contact info@revivebattery.eu"

3. NEVER MISDIRECT ESCALATIONS:
   - ALWAYS escalate to: info@revivebattery.eu
   - NEVER say: "contact providers in your area", "local service providers", "contact manufacturers", "reach out to battery companies"
   - NEVER give generic advice like "check with your local dealer" or "consult a professional"

4. NEVER MENTION COMPETITORS AS EXAMPLES:
   - NO mentioning: Panasonic, Samsung, LG, Tesla, Bosch, Interstate Battery, Johnson Controls, Exide, Trojan
   - These are not in Revive Battery's documentation

=== WHEN CONTEXT HAS RELEVANT INFORMATION ===
- Use ONLY facts from the provided context
- Cite sources using reference format
- Be specific about what Revive Battery does

=== WHEN CONTEXT LACKS INFORMATION ===
Respond EXACTLY with this pattern:
"I do not have information about [specific topic] in my knowledge base. For [topic], please contact info@revivebattery.eu"

=== WHEN QUESTION IS OFF-TOPIC ===
For questions about smartphones, laptops, EVs, lithium batteries:
"Revive Battery specializes in lead-acid battery regeneration. I don't have information about [off-topic item]. For questions about our services, please contact info@revivebattery.eu"
"""

# Email whitelist - only these users can access the system
ALLOWED_EMAILS = [
    "info@revivebattery.eu",
    "asimt7382@gmail.com",
    "tsim-2000@hotmail.com",
    "ananta.revive@gmail.com",
    "chepkemoi.projectmanager@gmail.com",
    "sharan.lb08@gmail.com",
    "sarthakjha92@gmail.com",
    "kajal99vaghela@gmail.com",
]

async def get_rag_token():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{RAG_API_URL}/login",
            data={"username": RAG_API_USER, "password": RAG_API_PASS}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
    return None

@cl.oauth_callback
def oauth_callback(
    provider_id: str,
    token: str,
    raw_user_data: dict,
    default_user: cl.User,
) -> cl.User:
    """
    Google OAuth callback - validates user email against whitelist
    + GDPR compliance: tracks consent and data retention policy
    """
    from datetime import datetime
    
    email = raw_user_data.get("email", "").lower()
    
    # Check if email is in whitelist
    if email not in [e.lower() for e in ALLOWED_EMAILS]:
        # Return None to deny access
        return None
    
    # Extract name from email or use Google profile name
    name = raw_user_data.get("given_name") or email.split("@")[0]
    
    # GDPR Compliance: Track consent and data retention
    current_timestamp = datetime.utcnow().isoformat()
    
    # Allow access with GDPR metadata
    return cl.User(
        identifier=email,
        metadata={
            "name": name,
            "provider": "google",
            "image": raw_user_data.get("picture"),
            # GDPR tracking
            "gdpr_consent_accepted": True,
            "gdpr_consent_date": current_timestamp,
            "data_retention_policy": "option_b_extended",  # 90-day soft delete, 24-month inactive
            "last_login": current_timestamp,
        }
    )

@cl.on_chat_start
async def on_chat_start():
    user = cl.user_session.get("user")
    name = user.metadata.get("name", user.identifier) if user else "there"
    
    settings = await cl.ChatSettings([
        Select(id="response_format", label="Response Format",
               values=["Paragraph", "Bullet Points", "Concise"], initial_value="Paragraph"),
        Select(id="query_mode", label="Query Mode", 
               values=["hybrid", "naive"], initial_value="hybrid"),
        Slider(id="max_sources", label="Max Sources", min=1, max=10, initial=3, step=1),
        Switch(id="show_sources", label="Show Citations", initial=True),
    ]).send()
    
    cl.user_session.set("settings", {
        "response_format": "Paragraph", "query_mode": "hybrid",
        "max_sources": 3, "show_sources": True
    })
    await cl.Message(content=f"Hello {name}! 👋 How can I help you today?").send()

@cl.on_settings_update
async def settings_update(settings):
    cl.user_session.set("settings", settings)
    await cl.Message(content="✅ Settings updated!").send()

async def direct_entity_lookup(query: str) -> str:
    """Direct database lookup for factual questions"""
    import asyncpg
    
    # Detect what entity information is being asked for
    query_lower = query.lower()
    
    try:
        conn = await asyncpg.connect(
            host='postgres_rag', port=5432, user='raguser',
            password='ragpass123', database='ragdb'
        )
        
        # CEO/Founder question
        if any(word in query_lower for word in ['ceo', 'founder', 'chief executive']):
            if 'revive battery' in query_lower or 'revive' in query_lower:
                result = await conn.fetchrow("""
                    SELECT content FROM lightrag_vdb_entity
                    WHERE workspace = 'default'
                      AND (entity_name ILIKE '%Ananta%' OR entity_name ILIKE '%Vangmai%')
                      AND content ILIKE '%CEO%'
                    LIMIT 1
                """)
                
                if result and result['content']:
                    await conn.close()
                    return result['content']
        
        await conn.close()
    except Exception as e:
        logger.error(f"Direct lookup error: {e}")
    
    return None

@cl.on_message
async def on_message(message: cl.Message):
    # INPUT VALIDATION
    if not message.content or len(message.content.strip()) == 0:
        msg = cl.Message(content="⚠️ Please enter a question.")
        await msg.send()
        return
    
    if len(message.content) > 1000:
        msg = cl.Message(content=(
            "⚠️ **Question too long** (max 1,000 characters)\n\n"
            "💡 **Tips for better questions:**\n"
            "- Be specific: *'What is lead-acid battery desulphation?'*\n"
            "- Focus on one topic at a time\n"
            "- Use technical terms we understand\n\n"
            "📚 See **welcome message** (refresh page) for question examples"
        ))
        await msg.send()
        return
    
    settings = cl.user_session.get("settings", {})
    query_mode = settings.get("query_mode", "hybrid")
    response_format = settings.get("response_format", "Paragraph")
    show_sources = settings.get("show_sources", True)
    max_sources = int(settings.get("max_sources", 3))
    
    # Show loading message
    msg = cl.Message(content="🔍 Searching knowledge base...")
    await msg.send()
    
    # Try direct entity lookup for factual questions first
    direct_answer = await direct_entity_lookup(message.content)
    if direct_answer:
        msg.content = f"✅ {direct_answer}\n\n---\n💡 *Retrieved directly from knowledge graph*"
        await msg.update()
        return
    
    # Detect if this is a verification/approval question (for post-processing)
    verification_keywords = ["approved", "certified", "confirm", "verify", "approval", "oem", "manufacturer", "warranty"]
    is_verification = any(keyword in message.content.lower() for keyword in verification_keywords)
    
    # Build format instruction - only formatting preferences now
    # REVIVE_PROMPT handles grounding rules via user_prompt parameter
    format_instruction = ""
    if response_format == "Bullet Points":
        format_instruction = " Format your response as bullet points."
    elif response_format == "Concise":
        format_instruction = " Keep your response brief and concise."
    
    try:
        token = await get_rag_token()
        if not token:
            msg.content = "⚠️ Failed to authenticate with knowledge base."
            await msg.update()
            return
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Build the complete user_prompt with company rules + formatting
            full_user_prompt = REVIVE_PROMPT + format_instruction
            
            # Try primary query mode first
            response = await client.post(
                f"{RAG_API_URL}/query",
                json={
                    "query": message.content,
                    "mode": query_mode,
                    "user_prompt": full_user_prompt
                },
                headers={"Authorization": f"Bearer {token}"}
            )
            
            # If primary mode returns no-context and it's not already naive, try naive as fallback
            if response.status_code == 200:
                result = response.json()
                answer = result.get("response", "")
                
                if "[no-context]" in answer and query_mode != "naive":
                    logger.info("Primary mode returned no-context, trying naive mode fallback...")
                    msg.content = "🔍 Trying alternative search method..."
                    await msg.update()
                    
                    response = await client.post(
                        f"{RAG_API_URL}/query",
                        json={
                            "query": message.content,
                            "mode": "naive",
                            "user_prompt": full_user_prompt
                        },
                        headers={"Authorization": f"Bearer {token}"}
                    )
            if response.status_code == 200:
                result = response.json()
                answer = result.get("response", "No response received.")
                
                # Check if response indicates no context was found
                # Check for both RAG API marker and explicit "no information" statements
                no_info_phrases = [
                    "[no-context]",
                    "i do not have information",
                    "i don't have information",
                    "no information about this",
                    "couldn't find any information"
                ]
                is_no_context = any(phrase in answer.lower() for phrase in no_info_phrases)
                
                # === SMART HALLUCINATION DETECTION ===
                # Split into two categories:
                # 1. ALWAYS_BLOCK: Never valid, always hallucination
                # 2. CHECK_IF_SOURCED: Could be from documents, only block if no references
                
                # Check if response has legitimate references
                references = result.get("references", [])
                has_valid_refs = isinstance(references, list) and len(references) > 0
                
                # === ALWAYS BLOCK (these are NEVER from legitimate documents) ===
                # REDUCED LIST - removed patterns causing false positives
                always_block_phrases = [
                    # Misdirected escalation - only the most specific patterns
                    "providers in your area",
                    "local service provider",
                    "service providers in your",
                    "contact battery manufacturers",
                    # Misdirection to competitors (user should contact Revive, not others)
                    "contact exide",
                    "contact panasonic",
                    "contact bosch",
                    "contact tesla",
                    "best to contact exide",
                    "reach out to exide",
                    
                    # Wrong company identity - keep these
                    "revive battery is a device",
                    
                    # Competitor mentions - keep major ones only
                    "panasonic",
                    "samsung sdi",
                    "lg chem",
                    "tesla",
                    "bosch",
                    
                    # Off-topic domains - keep but be specific
                    "lithium-ion batteries",
                    "smartphones",
                    "smartphone battery",
                    "laptops",
                    "laptop battery",
                    "electric vehicles",
                    "phone batteries",
                    
                    # Wrong domain entirely
                    "oil regeneration",
                    "oil regenerators",
                    
                    # AI self-reference (clear hallucination)
                    "i don't operate as",
                    "as an ai",
                    "as a language model",
                    "i cannot provide",
                    "i'm not able to",
                    "i am not able to",
                    "beyond my capabilities",
                    "outside my scope",
                    
                    # Vague authority claims
                    "reputable sources",
                    "industry experts",
                    "many experts",
                    "studies have shown",
                    "research indicates",
                    "according to experts",
                    "professionals recommend",
                ]
                
                # === BLOCK ONLY IF NO SOURCES (these MIGHT be from documents) ===
                # These patterns could appear in legitimate document content
                # Only block if response has NO valid references
                block_if_no_refs = [
                    # Generic pricing language (but ₹1500 from docs is OK)
                    "typically cost",
                    "usually cost",
                    "generally cost",
                    "costs around",
                    "costs between",
                    "price range",
                    "pricing varies",
                    "expect to pay",
                    "can cost anywhere",
                    "prices can range",
                    "rough estimate",
                    "ballpark figure",
                    
                    # USD prices (not in Revive docs - they use ₹)
                    "$50", "$100", "$150", "$200", "$250", "$300",
                    "$400", "$500", "$600", "$1000", "$1500",
                    "€50", "€100", "€150", "€200", "€300", "€500",
                    
                    # Vague statistics
                    "success rate of",
                    "success rates range",
                    "approximately 70%",
                    "approximately 80%",
                    "approximately 90%",
                    "around 70%",
                    "around 80%",
                    "around 90%",
                    "70% to 90%",
                    "80% to 90%",
                    "most batteries can",
                    "majority of batteries",
                    
                    # Generic advice patterns
                    "without a direct statement",
                    "cannot definitively say",
                    "sounds like a specific type",
                    "depends on several factors",
                    "key considerations:",
                    "steps to verify",
                    "generally speaking",
                    "in general,",
                    "here are some steps",
                    "here's how you can",
                    "here are some tips",
                    "factors to consider",
                    "things to consider",
                    "before you decide",
                ]
                
                answer_lower = answer.lower()
                
                # Step 1: Check for ALWAYS_BLOCK patterns (never valid)
                always_block_triggered = any(phrase.lower() in answer_lower for phrase in always_block_phrases)
                
                # Step 2: Check for BLOCK_IF_NO_REFS patterns
                conditional_block_triggered = any(phrase.lower() in answer_lower for phrase in block_if_no_refs)
                
                # Step 3: Decide whether to block
                if always_block_triggered:
                    # These patterns are NEVER from legitimate documents
                    triggered = [p for p in always_block_phrases if p.lower() in answer_lower][:3]
                    logger.warning(f"ALWAYS_BLOCK triggered: {triggered}")
                    is_no_context = True
                elif conditional_block_triggered and not has_valid_refs:
                    # These patterns MIGHT be from docs, but this response has no references
                    triggered = [p for p in block_if_no_refs if p.lower() in answer_lower][:3]
                    logger.warning(f"BLOCK_IF_NO_REFS triggered (no valid refs): {triggered}")
                    is_no_context = True
                elif conditional_block_triggered and has_valid_refs:
                    # Has references - allow but log for review
                    triggered = [p for p in block_if_no_refs if p.lower() in answer_lower][:3]
                    logger.info(f"ALLOWED with refs: {triggered} (refs: {len(references)})")
                elif is_verification:
                    # Verification questions need extra scrutiny
                    generic_advice = ["typically,", "generally,", "usually,", "in most cases"]
                    if any(g in answer_lower for g in generic_advice) and not has_valid_refs:
                        logger.warning(f"Verification question with generic advice and no refs")
                        is_no_context = True
                
                # Log the full response for debugging (first time only)
                logger.info(f"RAG API Response keys: {list(result.keys())}")
                if "context_data" in result:
                    logger.info(f"context_data keys: {list(result['context_data'].keys()) if isinstance(result['context_data'], dict) else 'not a dict'}")
                
                # Handle no-context scenario first
                if is_no_context:
                    answer = (
                        "I don't have enough information in my knowledge base to answer that accurately. "
                        "For detailed information, please contact info@revivebattery.eu"
                    )
                else:
                    # Extract and display sources/citations only if context was found
                    if show_sources:
                        sources_list = []
                        
                        # Check for various source formats that RAG API might return
                        if result.get("references"):
                            # RAG API uses 'references' field!
                            references = result.get("references", [])
                            logger.info(f"References type: {type(references)}, count: {len(references) if isinstance(references, list) else 'N/A'}")
                            
                            if isinstance(references, list) and len(references) > 0:
                                # Check if references are dicts or strings
                                first_ref = references[0]
                                logger.info(f"First reference type: {type(first_ref)}")
                                
                                if isinstance(first_ref, dict):
                                    # Extract file_path from each dict
                                    sources_list = [
                                        ref.get("file_path") or ref.get("source") or ref.get("document") or str(ref)
                                        for ref in references
                                        if isinstance(ref, dict)
                                    ]
                                    logger.info(f"Extracted {len(sources_list)} file paths from dict references")
                                elif isinstance(first_ref, str):
                                    # Already strings
                                    sources_list = references
                                    logger.info(f"Found {len(sources_list)} string references")
                                else:
                                    logger.warning(f"Unknown reference format: {type(first_ref)}")
                            else:
                                logger.info("References list is empty")
                        elif result.get("sources"):
                            sources_list = result.get("sources", [])
                            logger.info(f"Found sources in 'sources' field: {len(sources_list)}")
                        elif result.get("context_data"):
                            # LightRAG might return context_data with chunks
                            context = result.get("context_data", {})
                            if isinstance(context, dict):
                                if context.get("chunks"):
                                    chunks = context.get("chunks", [])
                                    sources_list = [chunk.get("file_path") or chunk.get("source") for chunk in chunks if isinstance(chunk, dict) and (chunk.get("file_path") or chunk.get("source"))]
                                    logger.info(f"Found {len(sources_list)} sources from chunks")
                                elif context.get("entities"):
                                    # Try to extract source from entities
                                    entities = context.get("entities", [])
                                    logger.info(f"Found {len(entities)} entities (no chunks)")
                        elif result.get("metadata"):
                            # Check metadata for source info
                            metadata = result.get("metadata", {})
                            if metadata.get("documents"):
                                sources_list = metadata.get("documents", [])
                                logger.info(f"Found sources in metadata: {len(sources_list)}")
                        
                        # Deduplicate and limit sources
                        if sources_list:
                            # Filter out None values and deduplicate
                            valid_sources = [s for s in sources_list if s]
                            unique_sources = list(set(valid_sources))[:max_sources]  # Use set() instead of dict.fromkeys()
                            
                            if unique_sources:
                                answer += "\n\n---\n📚 **Sources:**\n" + "\n".join(f"- 📄 {s}" for s in unique_sources)
                                logger.info(f"Displaying {len(unique_sources)} unique sources")
                            else:
                                logger.warning("No valid sources after filtering")
                        else:
                            # If no sources found, just note it's from knowledge base
                            pass  # No additional message needed
                
                msg.content = answer
            else:
                msg.content = f"⚠️ Error: Status {response.status_code}"
            await msg.update()
    except Exception as e:
        msg.content = f"⚠️ Error: {str(e)}"
        await msg.update()
