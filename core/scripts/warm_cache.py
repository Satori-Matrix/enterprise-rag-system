#!/usr/bin/env python3
"""
Cache Warming Script for RAG System
Pulls real user queries from Chainlit history and pre-populates LLM cache.

Usage:
    python warm_cache.py [--limit 30] [--delay 2]

Run after raganything container restart to warm the cache.
"""

import os
import sys
import time
import argparse
import requests
import psycopg2
from datetime import datetime

# Configuration from environment or defaults
RAG_API_URL = os.getenv("RAG_API_URL", "http://localhost:9621")
RAG_USERNAME = os.getenv("RAG_USERNAME", "admin")
RAG_PASSWORD = os.getenv("RAG_PASSWORD", "S3c0ndL1f3143!!")

CHAINLIT_DB_HOST = os.getenv("CHAINLIT_DB_HOST", "postgres_chainlit")
CHAINLIT_DB_PORT = os.getenv("CHAINLIT_DB_PORT", "5432")
CHAINLIT_DB_USER = os.getenv("CHAINLIT_DB_USER", "chainlit")
CHAINLIT_DB_PASS = os.getenv("CHAINLIT_DB_PASS", "chainlit_secure_2025")
CHAINLIT_DB_NAME = os.getenv("CHAINLIT_DB_NAME", "chainlit_db")


def get_token():
    """Get authentication token from RAG API."""
    try:
        resp = requests.post(
            f"{RAG_API_URL}/login",
            data={"username": RAG_USERNAME, "password": RAG_PASSWORD},
            timeout=10
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception as e:
        print(f"❌ Failed to get token: {e}")
        return None


def get_user_queries(limit=30):
    """
    Fetch most common user queries from Chainlit database.
    Returns list of unique queries ordered by frequency.
    """
    try:
        conn = psycopg2.connect(
            host=CHAINLIT_DB_HOST,
            port=CHAINLIT_DB_PORT,
            user=CHAINLIT_DB_USER,
            password=CHAINLIT_DB_PASS,
            database=CHAINLIT_DB_NAME
        )
        cursor = conn.cursor()
        
        # Get user queries (type='run' contains the user input)
        # Group similar queries and count frequency
        query = """
            SELECT input, COUNT(*) as freq
            FROM "Step"
            WHERE type = 'run' 
              AND input IS NOT NULL 
              AND input != ''
              AND input != '{}'
              AND LENGTH(input) > 10
            GROUP BY input
            ORDER BY freq DESC, LENGTH(input) DESC
            LIMIT %s;
        """
        
        cursor.execute(query, (limit,))
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Extract just the query strings
        queries = [row[0] for row in results if row[0]]
        return queries
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        return []


def get_fallback_queries():
    """Fallback common queries if database is empty or unavailable."""
    return [
        "What is desulphation?",
        "What is battery regeneration?",
        "How does Revive Battery's pulse charging work?",
        "What types of batteries can be regenerated?",
        "Tell me about Revive Battery",
        "What is the regeneration process?",
        "How long does battery regeneration take?",
        "What are the benefits of battery regeneration?",
        "Can old batteries be regenerated?",
        "What causes battery sulfation?",
    ]


def warm_cache(queries, token, delay=2, mode="hybrid"):
    """
    Run queries against RAG API to populate cache.
    
    Args:
        queries: List of query strings
        token: Auth token
        delay: Seconds between queries (to avoid overloading)
        mode: Query mode (hybrid or naive)
    """
    success = 0
    failed = 0
    
    print(f"\n🔥 Warming cache with {len(queries)} queries...")
    print(f"   Mode: {mode}, Delay: {delay}s between queries")
    print("-" * 60)
    
    for i, query in enumerate(queries, 1):
        try:
            start = time.time()
            
            resp = requests.post(
                f"{RAG_API_URL}/query",
                json={"query": query, "mode": mode},
                headers={"Authorization": f"Bearer {token}"},
                timeout=300  # 5 min timeout for slow CPU inference
            )
            
            latency = time.time() - start
            
            if resp.status_code == 200:
                result = resp.json()
                refs = len(result.get("references", []))
                print(f"✅ [{i}/{len(queries)}] {latency:.1f}s | {refs} refs | {query[:50]}...")
                success += 1
            else:
                print(f"❌ [{i}/{len(queries)}] HTTP {resp.status_code} | {query[:50]}...")
                failed += 1
                
        except requests.exceptions.Timeout:
            print(f"⏱️ [{i}/{len(queries)}] Timeout | {query[:50]}...")
            failed += 1
        except Exception as e:
            print(f"❌ [{i}/{len(queries)}] Error: {e}")
            failed += 1
        
        # Delay between queries to avoid overloading
        if i < len(queries):
            time.sleep(delay)
    
    return success, failed


def main():
    parser = argparse.ArgumentParser(description="Warm RAG cache with user queries")
    parser.add_argument("--limit", type=int, default=30, help="Max queries to warm")
    parser.add_argument("--delay", type=float, default=2, help="Delay between queries (seconds)")
    parser.add_argument("--mode", choices=["hybrid", "naive"], default="hybrid")
    parser.add_argument("--fallback-only", action="store_true", help="Use only fallback queries")
    args = parser.parse_args()
    
    print("=" * 60)
    print("🔥 RAG CACHE WARMING SCRIPT")
    print(f"   Started: {datetime.now().isoformat()}")
    print("=" * 60)
    
    # Get auth token
    print("\n📡 Connecting to RAG API...")
    token = get_token()
    if not token:
        print("❌ Failed to authenticate. Exiting.")
        sys.exit(1)
    print("✅ Authenticated")
    
    # Get queries
    if args.fallback_only:
        queries = get_fallback_queries()
        print(f"\n📋 Using {len(queries)} fallback queries")
    else:
        print(f"\n📋 Fetching user queries from Chainlit database...")
        queries = get_user_queries(limit=args.limit)
        
        if not queries:
            print("⚠️ No queries found, using fallback queries")
            queries = get_fallback_queries()
        else:
            print(f"✅ Found {len(queries)} unique user queries")
    
    # Warm cache
    start_time = time.time()
    success, failed = warm_cache(queries, token, delay=args.delay, mode=args.mode)
    total_time = time.time() - start_time
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 CACHE WARMING COMPLETE")
    print("=" * 60)
    print(f"   Successful: {success}")
    print(f"   Failed:     {failed}")
    print(f"   Total time: {total_time:.1f}s")
    print(f"   Avg/query:  {total_time/len(queries):.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()


