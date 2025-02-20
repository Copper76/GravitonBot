#!/bin/bash

# Fetch the latest change
git fetch

# Move to master branch
git checkout master

# Pull the latest changes
git pull

# Activate virtual environment
source venv/bin/activate

# Install additional requirements
pip install -r requirements.txt

# Run the file
py main.py