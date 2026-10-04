#!/bin/bash
set -euxo pipefail

# ---------------------------------------------------------------
# ParentChat server bootstrap — runs once on first launch.
# Installs Python 3.12, the app, faster-whisper, and a systemd
# service that listens on :8080 behind the ALB.
# ---------------------------------------------------------------

exec > /var/log/user-data.log 2>&1

# --- System packages ---
dnf update -y
dnf install -y python3.12 python3.12-pip git gcc python3.12-devel

# --- App directory ---
APP_DIR=/opt/parentchat
mkdir -p $APP_DIR

# --- Pull app code from S3 (deployed by CI) ---
# On first boot before CI runs, create a minimal placeholder so the
# service starts.  CI will overwrite with real code and restart.
cat > $APP_DIR/health.py << 'HEALTH'
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "starting"}).encode())

if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8080), H).serve_forever()
HEALTH

# --- Python dependencies ---
python3.12 -m pip install --upgrade pip
python3.12 -m pip install boto3 faster-whisper

# --- Environment file for systemd ---
cat > /etc/parentchat.env << 'ENV'
CHILDREN_TABLE=${children_table}
REGISTRATION_CODES_TABLE=${registration_codes_table}
MESSAGES_TABLE=${messages_table}
SCREENSHOT_REQUESTS_TABLE=${screenshot_requests_table}
S3_BUCKET=${s3_bucket}
AWS_DEFAULT_REGION=${aws_region}
COGNITO_USER_POOL_ID=${cognito_user_pool_id}
COGNITO_CLIENT_ID=${cognito_client_id}
SUBTITLE_MODEL=base
ENV

# --- Systemd service ---
cat > /etc/systemd/system/parentchat.service << 'SVC'
[Unit]
Description=ParentChat API Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/parentchat
EnvironmentFile=/etc/parentchat.env
ExecStart=/usr/bin/python3.12 local_server.py --port 8080
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=parentchat

[Install]
WantedBy=multi-user.target
SVC

systemctl daemon-reload
systemctl enable parentchat

# --- Deploy script that CI calls ---
cat > /opt/parentchat/deploy.sh << 'DEPLOY'
#!/bin/bash
set -euo pipefail
APP_DIR=/opt/parentchat
S3_WEB_BUCKET="${s3_web_bucket}"

echo "[deploy] Syncing backend code..."
# CI uploads a tarball to the screenshots bucket under deploy/
aws s3 cp "s3://$${S3_WEB_BUCKET}/deploy/backend.tar.gz" /tmp/backend.tar.gz
tar xzf /tmp/backend.tar.gz -C $APP_DIR --strip-components=1

echo "[deploy] Syncing web dist..."
aws s3 cp "s3://$${S3_WEB_BUCKET}/deploy/web-dist.tar.gz" /tmp/web-dist.tar.gz
mkdir -p $APP_DIR/../web/dist
tar xzf /tmp/web-dist.tar.gz -C $APP_DIR/../web/dist --strip-components=1

echo "[deploy] Restarting service..."
systemctl restart parentchat

echo "[deploy] Done."
DEPLOY
chmod +x /opt/parentchat/deploy.sh

# --- Start placeholder service until first real deploy ---
# If lambda_handler.py is already present (e.g. baked into AMI), start real server
if [ -f $APP_DIR/lambda_handler.py ]; then
    systemctl start parentchat
else
    # Start placeholder health endpoint
    python3.12 $APP_DIR/health.py &
fi

echo "[user-data] Bootstrap complete."
