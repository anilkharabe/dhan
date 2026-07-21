#!/bin/bash

# Setup Cron Job for Automatic Token Refresh
# This script adds a cron job to refresh the Upstox token daily

echo "=================================="
echo "Upstox Token Auto-Refresh Setup"
echo "=================================="
echo ""

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "📁 Script directory: $SCRIPT_DIR"
echo ""

# Create the cron job command
CRON_CMD="0 7 * * * cd $SCRIPT_DIR && /usr/bin/python3 refresh_token.py >> token_refresh.log 2>&1"

echo "⏰ Cron job will run daily at 7:00 AM"
echo "📝 Command: $CRON_CMD"
echo ""

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "refresh_token.py"; then
    echo "⚠️  Cron job already exists!"
    echo ""
    echo "Current cron jobs:"
    crontab -l | grep refresh_token.py
    echo ""
    read -p "Do you want to remove and re-add it? (y/N): " response
    
    if [[ "$response" =~ ^[Yy]$ ]]; then
        # Remove existing job
        crontab -l | grep -v refresh_token.py | crontab -
        echo "✓ Removed existing job"
    else
        echo "Cancelled."
        exit 0
    fi
fi

# Add the cron job
(crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -

echo ""
echo "✅ Cron job added successfully!"
echo ""
echo "The token will automatically refresh daily at 7:00 AM"
echo ""
echo "To verify, run: crontab -l"
echo "To remove, run: crontab -e (and delete the line)"
echo ""
echo "Logs will be saved to: $SCRIPT_DIR/token_refresh.log"
echo ""
