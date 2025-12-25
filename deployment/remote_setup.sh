#!/bin/bash

# Remote Setup Script
# This script runs ON THE SERVER (ser6)
# It expects 'deploy.tar.gz' to be in the home directory

TARGET_DIR="flask-schedule-webapp"

echo "----------------------------------------"
echo "Starting Remote Setup on $(hostname)"
echo "----------------------------------------"

# 1. Create directory if it doesn't exist
mkdir -p "$TARGET_DIR"

# 2. Unpack archive
echo "Unpacking code..."
tar -xzf ~/deploy.tar.gz -C "$TARGET_DIR"

# 3. Cleanup archive
rm ~/deploy.tar.gz

# 4. Enter directory
cd "$TARGET_DIR" || exit 1

# FIX: Grant write permissions to the database for the container
chmod -R 777 instance

# 5. Restart Docker containers
echo "Restarting application..."
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build

echo "----------------------------------------"
echo "Remote Setup Complete!"
echo "----------------------------------------"
