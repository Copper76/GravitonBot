#!/bin/bash

# Define process name for identifying running bot instances
PROCESS_NAME="main.py"

# Fetch the latest change
echo "Fetching latest changes from Git..."
git fetch

# Move to master branch
echo "Switching to master branch..."
git checkout master

# Pull the latest changes
echo "Pulling latest changes..."
git pull

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install additional requirements
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Kill existing bot instances
echo "Stopping existing bot instances..."
pkill -f "$PROCESS_NAME"

# Start the bot in the background with nohup
echo "Starting new bot instance..."
nohup python3 main.py > bot.log 2>&1 &

echo "Bot started with PID $!"
