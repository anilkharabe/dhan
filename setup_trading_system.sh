#!/bin/bash

echo "Setting up automated trading system..."

# 1. Setup auto token refresh
bash setup_auto_refresh.sh

# 2. Generate initial token
echo ""
echo "Generating initial token..."
python3 generate_token.py

echo ""
echo "✅ Setup complete!"
echo ""
echo "From now on, just run: python3 main.py"
echo "Token will auto-refresh daily at 7 AM"