#!/bin/bash

echo "🚀 Starting setup..."

# Install requirements
pip install -r requirements.txt

# Ask for .env values if not exists
if [ ! -f ".env" ]; then
    echo "Enter your Discord Bot Token:"
    read BOT_TOKEN

    echo "Enter Admin User ID (comma separated if multiple):"
    read ADMIN_IDS

    echo "Enter Admin Role ID:"
    read ADMIN_ROLE_ID

    cat <<EOL > .env
DISCORD_TOKEN=$BOT_TOKEN
ADMIN_IDS=$ADMIN_IDS
ADMIN_ROLE_ID=$ADMIN_ROLE_ID
EOL

    echo ".env file created ✅"
fi

# Create unixnodes user if not exists
if ! id -u unixnodes >/dev/null 2>&1; then
    sudo useradd -r -s /bin/false unixnodes
    sudo usermod -aG docker unixnodes
    echo "User unixnodes created ✅"
fi

# Copy service file
sudo cp unixnodes-bot.service /etc/systemd/system/unixnodes-bot.service
sudo systemctl daemon-reload
sudo systemctl enable unixnodes-bot.service
sudo systemctl start unixnodes-bot.service

echo "✅ Bot service installed & started!"

# Show service status
sudo systemctl status unixnodes-bot.service --no-pager

# Show logs (follow mode)
echo "📜 Showing live logs (Ctrl+C to exit)..."
sudo journalctl -u unixnodes-bot.service -f
