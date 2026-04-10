#!/usr/bin/env python3
"""
🔧 MCP Connection Diagnostic Tool
Helps debug why Streamlit can't connect to MCP server
"""

import sys
import json
from pathlib import Path

print("\n" + "="*60)
print("🔧 MCP DIAGNOSTICS")
print("="*60 + "\n")

# 1. Check if weather.py exists
print("✅ Step 1: Checking files...")
weather_py = Path("server/weather.py")
weather_json = Path("server/weather.json")

if weather_py.exists():
    print(f"   ✅ server/weather.py exists")
else:
    print(f"   ❌ server/weather.py NOT FOUND")
    sys.exit(1)

if weather_json.exists():
    print(f"   ✅ server/weather.json found")
    with open(weather_json) as f:
        config = json.load(f)
    print(f"   📋 Config: {json.dumps(config, indent=6)}")
else:
    print(f"   ❌ server/weather.json NOT FOUND")
    sys.exit(1)

# 2. Check if FastMCP can be imported
print("\n✅ Step 2: Checking FastMCP import...")
try:
    from mcp.server.fastmcp import FastMCP
    print("   ✅ FastMCP imported successfully")
except ImportError as e:
    print(f"   ❌ FastMCP import failed: {e}")
    sys.exit(1)

# 3. Check if server module can be imported
print("\n✅ Step 3: Importing weather server...")
try:
    from server.weather import mcp
    print("   ✅ server.weather imported successfully")
    print(f"   📋 MCP instance: {mcp}")
except Exception as e:
    print(f"   ❌ Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 4. Check if MCPClient can load config
print("\n✅ Step 4: Testing MCPClient config loading...")
try:
    from mcp_use import MCPClient
    config_path = str(weather_json.absolute())
    print(f"   📋 Loading from: {config_path}")
    
    # Try to create client
    client = MCPClient.from_config_file(str(weather_json))
    print(f"   ✅ MCPClient loaded successfully")
    print(f"   📋 Client tools: {len(client.tools) if hasattr(client, 'tools') else 'unknown'}")
    
except Exception as e:
    print(f"   ⚠️  MCPClient loading warning: {e}")
    import traceback
    traceback.print_exc()

# 5. Check environment
print("\n✅ Step 5: Checking environment...")
import os
groq_key = os.getenv("GROQ_API_KEY")
if groq_key:
    print(f"   ✅ GROQ_API_KEY set (first 10 chars: {groq_key[:10]}...)")
else:
    print(f"   ❌ GROQ_API_KEY not set")

mcp_tool = os.getenv("MCP_TOOL_PATH", "not set")
print(f"   📋 MCP_TOOL_PATH: {mcp_tool}")

# 6. Summary
print("\n" + "="*60)
print("✅ DIAGNOSTICS COMPLETE")
print("="*60)
print("\n📋 Next Steps:")
print("   1. If all checks passed → Start Streamlit: streamlit run Weather_streamlit_app.py")
print("   2. If FastMCP failed → Run: pip install mcp")
print("   3. If MCPClient failed → Check weather.json path is absolute")
print("   4. If GROQ_API_KEY missing → Add to .env file")
print("\n")
