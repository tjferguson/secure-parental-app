#!/usr/bin/env python3
"""
Local development server for the parental control chat backend.

Usage:
    python local_server.py                  # uses real DynamoDB / S3
    python local_server.py --memory         # in-memory storage (no AWS needed)
    python local_server.py --memory --port 9000
"""

import argparse
import json
import os
import re
import sys
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# ---------------------------------------------------------------------------
# Set environment BEFORE importing lambda_handler
# ---------------------------------------------------------------------------
os.environ.setdefault("LOCAL_DEV", "true")
os.environ.setdefault("CHILDREN_TABLE", "parentchat-children")
os.environ.setdefault("REGISTRATION_CODES_TABLE", "parentchat-registration-codes")
os.environ.setdefault("MESSAGES_TABLE", "parentchat-messages")
os.environ.setdefault("SCREENSHOT_REQUESTS_TABLE", "parentchat-screenshot-requests")
os.environ.setdefault("S3_BUCKET", "parentchat-screenshots")


# ---------------------------------------------------------------------------
# In-memory storage that mimics DynamoDB Table and S3 interfaces
# ---------------------------------------------------------------------------

class InMemoryTable:
    """Minimal DynamoDB Table work-alike backed by a Python dict."""

    def __init__(self, name, key_schema):
        self.name = name
        self.key_schema = key_schema  # list of key attribute names, e.g. ["pk"] or ["pk", "sk"]
        self._items = {}  # keyed by tuple of key values

    def _key(self, item_or_key):
        return tuple(item_or_key[k] for k in self.key_schema)

    def put_item(self, Item, **_kw):
        self._items[self._key(Item)] = dict(Item)
        return {}

    def get_item(self, Key, **_kw):
        item = self._items.get(self._key(Key))
        if item:
            return {"Item": dict(item)}
        return {}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues=None,
                     ExpressionAttributeNames=None, **_kw):
        key = self._key(Key)
        item = self._items.get(key)
        if item is None:
            item = dict(Key)
            self._items[key] = item

        names = ExpressionAttributeNames or {}
        vals = ExpressionAttributeValues or {}

        # Parse simple SET expressions: SET #a = :v, b = :w
        set_match = re.search(r"SET\s+(.+)", UpdateExpression, re.IGNORECASE)
        if set_match:
            assignments = set_match.group(1).split(",")
            for assignment in assignments:
                lhs, rhs = assignment.strip().split("=", 1)
                lhs = lhs.strip()
                rhs = rhs.strip()
                # Resolve attribute name aliases
                attr_name = names.get(lhs, lhs)
                value = vals.get(rhs, rhs)
                item[attr_name] = value

        return {}

    def scan(self, FilterExpression=None, **_kw):
        items = list(self._items.values())
        if FilterExpression is not None:
            items = [i for i in items if _eval_condition(FilterExpression, i)]
        return {"Items": [dict(i) for i in items]}

    def query(self, KeyConditionExpression=None, FilterExpression=None, **_kw):
        items = list(self._items.values())
        if KeyConditionExpression is not None:
            items = [i for i in items if _eval_condition(KeyConditionExpression, i)]
        if FilterExpression is not None:
            items = [i for i in items if _eval_condition(FilterExpression, i)]
        return {"Items": [dict(i) for i in items]}


def _eval_condition(cond, item):
    """
    Evaluate a Mock condition expression against an in-memory item.
    Supports MockExpr, MockAndExpr, and boto3 condition objects.
    """
    if isinstance(cond, MockExpr):
        return _eval_mock_expr(cond, item)
    if isinstance(cond, MockAndExpr):
        return _eval_condition(cond._left, item) and _eval_condition(cond._right, item)
    # Fallback for boto3 condition objects (non-memory mode)
    expr = cond.get_expression()
    return _eval_expr(expr, item)


def _eval_mock_expr(cond, item):
    """Evaluate a MockExpr directly using its stored fields."""
    stored = item.get(cond._name)
    if cond._op == "=":
        return stored == cond._value
    if cond._op == ">=":
        if stored is None:
            return False
        return stored >= cond._value
    return True


def _eval_expr(expr, item):
    """Fallback evaluator for boto3 condition expression dicts."""
    operator = expr.get("operator")

    if operator == "AND":
        values = expr.get("values", [])
        return all(_eval_expr(v.get_expression() if hasattr(v, "get_expression") else v, item)
                    for v in values)

    if operator in ("=", ">="):
        path, value = _resolve_operands(expr, item)
        stored = item.get(path)
        if operator == "=":
            return stored == value
        if stored is None:
            return False
        return stored >= value

    return True


def _resolve_operands(expr, item):
    """Return (attribute_path, comparison_value) from an expression."""
    values = expr.get("values", [])
    path = None
    value = None
    for v in values:
        if hasattr(v, "get_expression"):
            inner = v.get_expression()
            if inner.get("format") == "{0}":
                if path is None:
                    path = inner["values"][0]
                else:
                    value = inner["values"][0]
            else:
                value = inner["values"][0]
        elif isinstance(v, dict):
            if v.get("format") == "{0}":
                if path is None:
                    path = v["values"][0]
                else:
                    value = v["values"][0]
            else:
                value = v["values"][0]
        else:
            value = v
    return path, value


class InMemoryS3:
    """Minimal S3 client work-alike."""

    def __init__(self):
        self._objects = {}  # bucket -> key -> bytes

    def put_object(self, Bucket, Key, Body, **_kw):
        self._objects.setdefault(Bucket, {})[Key] = Body
        return {}

    def get_object(self, Bucket, Key, **_kw):
        data = self._objects.get(Bucket, {}).get(Key)
        if data is None:
            raise Exception(f"NoSuchKey: {Bucket}/{Key}")
        import io
        return {"Body": io.BytesIO(data)}

    def generate_presigned_url(self, _method, Params, ExpiresIn=3600, **_kw):
        bucket = Params.get("Bucket", "")
        key = Params.get("Key", "")
        port = os.environ.get("LOCAL_SERVER_PORT", "8080")
        return f"http://localhost:{port}/mock-s3/{bucket}/{key}?expires={ExpiresIn}"


class InMemoryDynamoDB:
    """Mimics boto3.resource('dynamodb') with in-memory tables."""

    TABLE_SCHEMAS = {
        "parentchat-children": ["childId"],
        "parentchat-registration-codes": ["code"],
        "parentchat-messages": ["conversationId", "timestamp"],
        "parentchat-screenshot-requests": ["childId", "requestId"],
    }

    def __init__(self):
        self._tables = {}
        for name, keys in self.TABLE_SCHEMAS.items():
            self._tables[name] = InMemoryTable(name, keys)

    def Table(self, name):
        if name not in self._tables:
            self._tables[name] = InMemoryTable(name, ["id"])
        return self._tables[name]


# ---------------------------------------------------------------------------
# Monkey-patching for --memory mode
# ---------------------------------------------------------------------------

class MockCondition:
    """Mock for boto3 Key/Attr condition expressions."""
    def __init__(self, name):
        self._name = name
    def eq(self, value):
        return MockExpr("=", self._name, value)
    def gte(self, value):
        return MockExpr(">=", self._name, value)

class MockExpr:
    """Mock condition expression that works with InMemoryTable."""
    def __init__(self, op, name, value):
        self._op = op
        self._name = name
        self._value = value

    def __and__(self, other):
        return MockAndExpr(self, other)

    def get_expression(self):
        return {
            "operator": self._op,
            "values": [
                {"format": "{0}", "values": [self._name]},
                {"format": "{0}", "values": [self._value]},
            ],
        }

class MockAndExpr:
    def __init__(self, left, right):
        self._left = left
        self._right = right

    def get_expression(self):
        return {
            "operator": "AND",
            "values": [self._left, self._right],
        }


def apply_memory_patches():
    """Replace boto3 calls in lambda_handler with in-memory implementations."""
    import lambda_handler as lh

    db = InMemoryDynamoDB()
    s3 = InMemoryS3()

    # Patch the resource getters
    lh._dynamodb = db
    lh._s3 = s3

    # Override _get_dynamodb and _get_s3 so they don't recreate clients
    lh._get_dynamodb = lambda: db
    lh._get_s3 = lambda: s3

    # Patch Key and Attr with mock implementations
    lh.Key = MockCondition
    lh.Attr = MockCondition

    print("[memory] In-memory DynamoDB and S3 active. No AWS credentials needed.")


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

STATIC_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"


class LocalHandler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self._handle()

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def do_PUT(self):
        self._handle()

    def do_DELETE(self):
        self._handle()

    # ----- internal -----

    def _handle(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query_string = parsed.query

        # Serve mock S3 objects for in-memory mode
        if path.startswith("/mock-s3/"):
            self._serve_mock_s3(path)
            return

        # Serve static files for non-API paths
        if not path.startswith("/api"):
            self._serve_static(path)
            return

        # Build an API Gateway-style event
        event = self._build_event(path, query_string)

        import lambda_handler as lh
        response = lh.handler(event, None)

        status_code = response.get("statusCode", 200)
        headers = response.get("headers", {})
        body = response.get("body", "")

        self.send_response(status_code)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body.encode("utf-8") if isinstance(body, str) else body)

    def _build_event(self, path, query_string):
        # Read body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length else None

        # Parse query params
        qs = urllib.parse.parse_qs(query_string)
        query_params = {k: v[0] for k, v in qs.items()} if qs else None

        # Collect headers
        headers = {}
        for key in self.headers:
            headers[key] = self.headers[key]

        # Extract path parameters (e.g., /api/screenshots/{requestId})
        path_params = {}
        screenshot_match = re.match(r"^/api/screenshots/([^/?]+)$", path)
        if screenshot_match:
            candidate = screenshot_match.group(1)
            if candidate not in ("request", "pending", "upload"):
                path_params["requestId"] = candidate

        event = {
            "httpMethod": self.command,
            "path": path,
            "headers": headers,
            "queryStringParameters": query_params,
            "pathParameters": path_params,
            "body": body,
            "requestContext": {},
        }

        return event

    def _serve_mock_s3(self, path):
        """Serve objects from InMemoryS3 for local dev."""
        # Path format: /mock-s3/{bucket}/{key...}
        parts = path[len("/mock-s3/"):].split("/", 1)
        if len(parts) < 2:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        bucket, key = parts[0], parts[1].split("?")[0]  # strip query params
        try:
            import lambda_handler as lh
            s3 = lh._get_s3()
            data = s3._objects.get(bucket, {}).get(key)
            if data is None:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Not found")
                return

            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(str(e).encode())

    def _serve_static(self, path):
        if path == "/":
            path = "/index.html"

        file_path = STATIC_DIR / path.lstrip("/")

        if not file_path.is_file():
            # SPA fallback
            file_path = STATIC_DIR / "index.html"

        if not file_path.is_file():
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        content_type = _guess_content_type(file_path)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def log_message(self, format, *args):
        # Colour-coded logging
        method = args[0] if args else ""
        sys.stderr.write(f"  {self.address_string()} - {format % args}\n")


MIME_TYPES = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
}


def _guess_content_type(path):
    suffix = path.suffix.lower()
    return MIME_TYPES.get(suffix, "application/octet-stream")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Local dev server for parent-sec-chat backend")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--memory", action="store_true",
                        help="Use in-memory storage instead of real DynamoDB/S3")
    args = parser.parse_args()

    # Add backend directory to path so lambda_handler can be imported
    backend_dir = str(Path(__file__).resolve().parent)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    # Import handler (env vars already set above)
    import lambda_handler  # noqa: F401

    # Set port for mock S3 presigned URLs
    os.environ["LOCAL_SERVER_PORT"] = str(args.port)

    if args.memory:
        apply_memory_patches()

    server = HTTPServer(("0.0.0.0", args.port), LocalHandler)
    print(f"Local server running on http://localhost:{args.port}")
    print(f"Static files from {STATIC_DIR}")
    print(f"Storage mode: {'in-memory' if args.memory else 'AWS DynamoDB/S3'}")
    print("Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
