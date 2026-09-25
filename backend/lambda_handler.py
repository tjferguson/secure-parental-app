import json
import os
import re
import string
import random
import uuid
import decimal
from datetime import datetime, timezone

try:
    import boto3
    from boto3.dynamodb.conditions import Key, Attr
except ImportError:
    boto3 = None  # Will be monkey-patched in memory mode
    Key = None
    Attr = None

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
CHILDREN_TABLE = os.environ.get("CHILDREN_TABLE", "parentchat-children")
REGISTRATION_CODES_TABLE = os.environ.get("REGISTRATION_CODES_TABLE", "parentchat-registration-codes")
MESSAGES_TABLE = os.environ.get("MESSAGES_TABLE", "parentchat-messages")
SCREENSHOT_REQUESTS_TABLE = os.environ.get("SCREENSHOT_REQUESTS_TABLE", "parentchat-screenshot-requests")
S3_BUCKET = os.environ.get("S3_BUCKET", "parentchat-screenshots")
LOCAL_DEV = os.environ.get("LOCAL_DEV", "false").lower() == "true"

# ---------------------------------------------------------------------------
# AWS resources (lazily initialised so monkey-patching works)
# ---------------------------------------------------------------------------
_dynamodb = None
_s3 = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb


def _get_s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def _table(name):
    return _get_dynamodb().Table(name)


# ---------------------------------------------------------------------------
# Custom JSON encoder that handles Decimal
# ---------------------------------------------------------------------------
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            if o % 1 == 0:
                return int(o)
            return float(o)
        return super().default(o)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def build_response(status, body):
    """Return an API-Gateway-compatible response with CORS headers."""
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Child-Token,X-Parent-Id",
            "Access-Control-Allow-Methods": "*",
        },
        "body": json.dumps(body, cls=DecimalEncoder),
    }


def get_parent_id(event):
    """Extract the parent id from Cognito claims or the X-Parent-Id header (local dev)."""
    if LOCAL_DEV:
        headers = event.get("headers") or {}
        # Normalise header keys to lower-case for robustness
        lc_headers = {k.lower(): v for k, v in headers.items()}
        parent_id = lc_headers.get("x-parent-id")
        if parent_id:
            return parent_id
    try:
        return event["requestContext"]["authorizer"]["claims"]["sub"]
    except (KeyError, TypeError):
        return None


def get_child_by_token(token):
    """Scan the children table for a record whose authToken matches *token*."""
    table = _table(CHILDREN_TABLE)
    resp = table.scan(FilterExpression=Attr("authToken").eq(token))
    items = resp.get("Items", [])
    return items[0] if items else None


def get_sender_identity(event):
    """
    Try parent auth first, then child auth.
    Returns (sender_id, sender_type) or (None, None).
    """
    parent_id = get_parent_id(event)
    if parent_id:
        return parent_id, "parent"

    headers = event.get("headers") or {}
    lc_headers = {k.lower(): v for k, v in headers.items()}
    child_token = lc_headers.get("x-child-token")
    if child_token:
        child = get_child_by_token(child_token)
        if child:
            return child["childId"], "child"

    return None, None


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _generate_code(length=8):
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


def _conversation_id(parent_id, child_id):
    """Deterministic conversation id from parentId and childId."""
    parts = sorted([parent_id, child_id])
    return f"{parts[0]}#{parts[1]}"


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

def handle_generate_code(event):
    """POST /api/children/generate-code"""
    parent_id = get_parent_id(event)
    if not parent_id:
        return build_response(401, {"error": "Unauthorized"})

    body = json.loads(event.get("body") or "{}")
    child_name = body.get("childName")
    if not child_name:
        return build_response(400, {"error": "childName is required"})

    code = _generate_code()
    table = _table(REGISTRATION_CODES_TABLE)
    table.put_item(Item={
        "code": code,
        "parentId": parent_id,
        "childName": child_name,
        "used": False,
        "createdAt": _now_iso(),
    })

    return build_response(200, {"code": code, "childName": child_name})


def handle_register_child(event):
    """POST /api/children/register"""
    body = json.loads(event.get("body") or "{}")
    code = body.get("code")
    if not code:
        return build_response(400, {"error": "code is required"})

    codes_table = _table(REGISTRATION_CODES_TABLE)
    resp = codes_table.get_item(Key={"code": code})
    item = resp.get("Item")

    if not item:
        return build_response(404, {"error": "Invalid registration code"})
    if item.get("used"):
        return build_response(400, {"error": "Registration code already used"})

    child_id = str(uuid.uuid4())
    auth_token = str(uuid.uuid4())
    parent_id = item["parentId"]
    display_name = item["childName"]

    children_table = _table(CHILDREN_TABLE)
    children_table.put_item(Item={
        "childId": child_id,
        "authToken": auth_token,
        "parentId": parent_id,
        "displayName": display_name,
        "createdAt": _now_iso(),
    })

    # Mark code as used
    codes_table.update_item(
        Key={"code": code},
        UpdateExpression="SET used = :val",
        ExpressionAttributeValues={":val": True},
    )

    return build_response(200, {
        "childId": child_id,
        "authToken": auth_token,
        "parentId": parent_id,
        "displayName": display_name,
    })


def handle_list_children(event):
    """GET /api/children"""
    parent_id = get_parent_id(event)
    if not parent_id:
        return build_response(401, {"error": "Unauthorized"})

    table = _table(CHILDREN_TABLE)
    resp = table.scan(FilterExpression=Attr("parentId").eq(parent_id))
    children = resp.get("Items", [])

    return build_response(200, children)


def handle_send_message(event):
    """POST /api/messages"""
    sender_id, sender_type = get_sender_identity(event)
    if not sender_id:
        return build_response(401, {"error": "Unauthorized"})

    body = json.loads(event.get("body") or "{}")
    content = body.get("content")
    if not content:
        return build_response(400, {"error": "content is required"})

    if sender_type == "parent":
        parent_id = sender_id
        child_id = body.get("childId")
        if not child_id:
            return build_response(400, {"error": "childId is required"})
    else:
        child_id = sender_id
        parent_id = body.get("parentId")
        # Auto-resolve parentId from children table
        if not parent_id:
            child_rec = _table(CHILDREN_TABLE).get_item(Key={"childId": child_id}).get("Item")
            if child_rec:
                parent_id = child_rec.get("parentId")
        if not parent_id:
            return build_response(400, {"error": "parentId is required"})

    conversation_id = _conversation_id(parent_id, child_id)
    timestamp = f"{_now_iso()}_{uuid.uuid4()}"

    table = _table(MESSAGES_TABLE)
    table.put_item(Item={
        "conversationId": conversation_id,
        "timestamp": timestamp,
        "senderId": sender_id,
        "senderType": sender_type,
        "content": content,
    })

    return build_response(200, {
        "messageId": timestamp,
        "conversationId": conversation_id,
    })


def handle_get_messages(event):
    """GET /api/messages"""
    sender_id, sender_type = get_sender_identity(event)
    if not sender_id:
        return build_response(401, {"error": "Unauthorized"})

    params = event.get("queryStringParameters") or {}
    child_id = params.get("childId")
    parent_id = params.get("parentId")
    since = params.get("since")

    if sender_type == "parent":
        parent_id = sender_id
        # Look up parentId from children table if not provided
        if child_id and not parent_id:
            child_rec = _table(CHILDREN_TABLE).get_item(Key={"childId": child_id}).get("Item")
            if child_rec:
                parent_id = child_rec.get("parentId", sender_id)
    else:
        child_id = sender_id
        # Look up parentId from children table if not provided
        if not parent_id:
            child_rec = _table(CHILDREN_TABLE).get_item(Key={"childId": child_id}).get("Item")
            if child_rec:
                parent_id = child_rec.get("parentId")

    if not child_id or not parent_id:
        return build_response(400, {"error": "childId and parentId are required"})

    conversation_id = _conversation_id(parent_id, child_id)
    table = _table(MESSAGES_TABLE)

    if since:
        resp = table.query(
            KeyConditionExpression=Key("conversationId").eq(conversation_id)
            & Key("timestamp").gte(since),
        )
    else:
        resp = table.query(
            KeyConditionExpression=Key("conversationId").eq(conversation_id),
        )

    messages = sorted(resp.get("Items", []), key=lambda m: m["timestamp"])
    return build_response(200, messages)


def handle_screenshot_request(event):
    """POST /api/screenshots/request"""
    parent_id = get_parent_id(event)
    if not parent_id:
        return build_response(401, {"error": "Unauthorized"})

    body = json.loads(event.get("body") or "{}")
    child_id = body.get("childId")
    if not child_id:
        return build_response(400, {"error": "childId is required"})

    request_id = str(uuid.uuid4())
    table = _table(SCREENSHOT_REQUESTS_TABLE)
    table.put_item(Item={
        "childId": child_id,
        "requestId": request_id,
        "status": "pending",
        "requestedAt": _now_iso(),
        "parentId": parent_id,
    })

    return build_response(200, {"requestId": request_id})


def handle_pending_screenshots(event):
    """GET /api/screenshots/pending"""
    sender_id, sender_type = get_sender_identity(event)
    if not sender_id or sender_type != "child":
        # Also allow with query param for flexibility
        pass

    params = event.get("queryStringParameters") or {}
    child_id = params.get("childId") or sender_id
    if not child_id:
        return build_response(400, {"error": "childId is required"})

    table = _table(SCREENSHOT_REQUESTS_TABLE)
    resp = table.query(
        KeyConditionExpression=Key("childId").eq(child_id),
        FilterExpression=Attr("status").eq("pending"),
    )

    return build_response(200, resp.get("Items", []))


def handle_screenshot_upload(event):
    """POST /api/screenshots/upload"""
    sender_id, sender_type = get_sender_identity(event)
    if not sender_id:
        return build_response(401, {"error": "Unauthorized"})

    body = json.loads(event.get("body") or "{}")
    request_id = body.get("requestId")
    child_id = body.get("childId")
    image_data = body.get("imageData")

    if not all([request_id, child_id, image_data]):
        return build_response(400, {"error": "requestId, childId, and imageData are required"})

    import base64
    image_bytes = base64.b64decode(image_data)

    s3_key = f"screenshots/{child_id}/{request_id}.png"
    s3 = _get_s3()
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=s3_key,
        Body=image_bytes,
        ContentType="image/png",
    )

    table = _table(SCREENSHOT_REQUESTS_TABLE)
    table.update_item(
        Key={"childId": child_id, "requestId": request_id},
        UpdateExpression="SET #s = :status, s3Key = :key, completedAt = :ts",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":status": "completed",
            ":key": s3_key,
            ":ts": _now_iso(),
        },
    )

    return build_response(200, {"success": True})


def handle_get_screenshot(event, request_id):
    """GET /api/screenshots/{requestId}"""
    parent_id = get_parent_id(event)
    if not parent_id:
        return build_response(401, {"error": "Unauthorized"})

    params = event.get("queryStringParameters") or {}
    child_id = params.get("childId")
    if not child_id:
        return build_response(400, {"error": "childId is required"})

    table = _table(SCREENSHOT_REQUESTS_TABLE)
    resp = table.get_item(Key={"childId": child_id, "requestId": request_id})
    item = resp.get("Item")
    if not item:
        return build_response(404, {"error": "Screenshot request not found"})

    result = {"status": item["status"]}

    if item["status"] == "completed" and item.get("s3Key"):
        s3 = _get_s3()
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": item["s3Key"]},
            ExpiresIn=3600,
        )
        result["url"] = url

    return build_response(200, result)


# ---------------------------------------------------------------------------
# Route table
# ---------------------------------------------------------------------------
ROUTES = [
    ("POST", r"^/api/children/generate-code$", handle_generate_code),
    ("POST", r"^/api/children/register$", handle_register_child),
    ("GET", r"^/api/children$", handle_list_children),
    ("POST", r"^/api/messages$", handle_send_message),
    ("GET", r"^/api/messages$", handle_get_messages),
    ("POST", r"^/api/screenshots/request$", handle_screenshot_request),
    ("GET", r"^/api/screenshots/pending$", handle_pending_screenshots),
    ("POST", r"^/api/screenshots/upload$", handle_screenshot_upload),
    ("GET", r"^/api/screenshots/(?P<request_id>[^/]+)$", handle_get_screenshot),
]


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------
def handler(event, context):
    """Main Lambda handler that routes based on httpMethod and path."""
    try:
        method = event.get("httpMethod", "")
        path = event.get("path", "")

        # Global OPTIONS handling
        if method == "OPTIONS":
            return build_response(200, {})

        for route_method, pattern, route_handler in ROUTES:
            if method != route_method:
                continue
            match = re.match(pattern, path)
            if match:
                groups = match.groupdict()
                if groups:
                    return route_handler(event, **groups)
                return route_handler(event)

        return build_response(404, {"error": "Not found", "path": path, "method": method})

    except Exception as exc:
        print(f"Unhandled error: {exc}")
        import traceback
        traceback.print_exc()
        return build_response(500, {"error": "Internal server error"})
