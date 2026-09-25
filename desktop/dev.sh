#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="/tmp/parentchat-dev"
SERVER_URL="${1:-http://localhost:8080}"

echo "=== ParentChat Desktop - Local Dev ==="
echo "Config dir: $CONFIG_DIR"
echo "Server URL: $SERVER_URL"
echo ""

# Clean up previous dev config if --clean flag is passed
if [[ "$1" == "--clean" || "$2" == "--clean" ]]; then
    echo "Cleaning dev config..."
    rm -rf "$CONFIG_DIR"
fi

# Ensure config dir exists
mkdir -p "$CONFIG_DIR"

# Check if we need to register
if [ ! -f "$CONFIG_DIR/config.json" ] || ! python3 -c "
import json, sys
with open('$CONFIG_DIR/config.json') as f:
    c = json.load(f)
    if c.get('child_id') and c.get('auth_token'):
        sys.exit(0)
    sys.exit(1)
" 2>/dev/null; then
    echo "No registration found. Attempting auto-registration..."
    echo ""

    # Auto-register: generate code then register
    echo "Generating registration code..."
    CODE_RESP=$(python3 -c "
import urllib.request, json
req = urllib.request.Request('$SERVER_URL/api/children/generate-code',
    data=json.dumps({'childName': 'DevChild'}).encode(), method='POST')
req.add_header('Content-Type', 'application/json')
req.add_header('X-Parent-Id', 'dev-parent-001')
resp = urllib.request.urlopen(req, timeout=5)
print(resp.read().decode())
" 2>/dev/null) || {
        echo "ERROR: Could not connect to server at $SERVER_URL"
        echo "Make sure the backend is running: cd backend && python3 local_server.py --memory"
        exit 1
    }

    CODE=$(echo "$CODE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['code'])")
    echo "Generated code: $CODE"

    # Register
    echo "Registering child device..."
    REG_RESP=$(python3 -c "
import urllib.request, json
req = urllib.request.Request('$SERVER_URL/api/children/register',
    data=json.dumps({'code': '$CODE'}).encode(), method='POST')
req.add_header('Content-Type', 'application/json')
resp = urllib.request.urlopen(req, timeout=5)
print(resp.read().decode())
")

    CHILD_ID=$(echo "$REG_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['childId'])")
    AUTH_TOKEN=$(echo "$REG_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['authToken'])")
    PARENT_ID=$(echo "$REG_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('parentId',''))")
    DISPLAY_NAME=$(echo "$REG_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('displayName',''))")

    # Write config
    python3 -c "
import json
config = {
    'child_id': '$CHILD_ID',
    'auth_token': '$AUTH_TOKEN',
    'parent_id': '$PARENT_ID',
    'display_name': '$DISPLAY_NAME',
    'server_url': '$SERVER_URL',
    'last_message_timestamp': None
}
with open('$CONFIG_DIR/config.json', 'w') as f:
    json.dump(config, f, indent=2)
"
    echo "Registered as: $DISPLAY_NAME ($CHILD_ID)"
    echo ""
fi

echo "Starting desktop client..."
echo "---"
cd "$SCRIPT_DIR"
python3 main.py --server-url "$SERVER_URL" --config-dir "$CONFIG_DIR" --allow-quit
