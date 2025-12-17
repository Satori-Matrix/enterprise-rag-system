#!/usr/bin/env python3
"""
Chainlit 2.9.3 Bug Fix - showInput Type Mismatch (COMPREHENSIVE)
=================================================================
Bug: Chainlit uses string "json" for showInput, but PostgreSQL expects boolean
Error: "invalid input for query argument $11: 'json' (a boolean is required)"
Fix: Patch BOTH step.py and chainlit_data_layer.py
Date: December 2025
"""
import re

print("🔧 Applying comprehensive Chainlit 2.9.3 showInput patch...")

# Patch 1: chainlit_data_layer.py (database insertion)
file1 = "/usr/local/lib/python3.11/site-packages/chainlit/data/chainlit_data_layer.py"
with open(file1, 'r') as f:
    content1 = f.read()

original1 = content1
content1 = re.sub(
    r'"show_input":\s*str\(step_dict\.get\("showInput",\s*"json"\)\)',
    '"show_input": step_dict.get("showInput", True)',
    content1
)

if content1 != original1:
    with open(file1, 'w') as f:
        f.write(content1)
    print("✅ Patched chainlit_data_layer.py")
else:
    print("⚠️  chainlit_data_layer.py: Pattern not found or already patched")

# Patch 2: step.py (Step class defaults)
file2 = "/usr/local/lib/python3.11/site-packages/chainlit/step.py"
with open(file2, 'r') as f:
    content2 = f.read()

original2 = content2

# Replace string default "json" with boolean True
content2 = re.sub(
    r'show_input:\s*Union\[bool,\s*str\]\s*=\s*"json"',
    'show_input: bool = True',
    content2
)

# Also fix the type hint to only accept bool
content2 = re.sub(
    r'show_input:\s*Union\[bool,\s*str\]',
    'show_input: bool',
    content2
)

if content2 != original2:
    with open(file2, 'w') as f:
        f.write(content2)
    print("✅ Patched step.py")
else:
    print("⚠️  step.py: Pattern not found or already patched")

print("\n📝 Comprehensive patch complete!")
print("   - chainlit_data_layer.py: Database insertion fixed")
print("   - step.py: Default value and type hints fixed")

