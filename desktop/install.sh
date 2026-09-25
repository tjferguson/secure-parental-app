#!/bin/bash
set -e

echo "Installing ParentChat Desktop Client..."

# Install system dependencies
sudo apt-get update
sudo apt-get install -y \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-3.0 \
    gir1.2-appindicator3-0.1 \
    gir1.2-notify-0.7 \
    ffmpeg \
    x11-apps \
    imagemagick \
    python3-venv \
    python3-pip

# Create application directory
sudo mkdir -p /opt/parentchat
sudo cp *.py /opt/parentchat/
sudo cp requirements.txt /opt/parentchat/

# Create virtual environment and install deps
sudo python3 -m venv /opt/parentchat/venv
sudo /opt/parentchat/venv/bin/pip install -r /opt/parentchat/requirements.txt

# Create wrapper script
sudo tee /opt/parentchat/run.sh > /dev/null << 'SCRIPT'
#!/bin/bash
cd /opt/parentchat
/opt/parentchat/venv/bin/python3 main.py "$@"
SCRIPT
sudo chmod +x /opt/parentchat/run.sh

# Update desktop file to use wrapper
sed 's|Exec=python3 /opt/parentchat/main.py|Exec=/opt/parentchat/run.sh|' parentchat.desktop > /tmp/parentchat.desktop

# Install autostart
mkdir -p ~/.config/autostart
cp /tmp/parentchat.desktop ~/.config/autostart/

# Install application menu entry
sudo cp /tmp/parentchat.desktop /usr/share/applications/ 2>/dev/null || true

echo "Installation complete!"
echo "ParentChat will start automatically on next login."
echo "To start now, run: /opt/parentchat/run.sh"
