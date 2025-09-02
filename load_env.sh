#!/bin/bash
# Load environment variables from .env file and run the specified command
# Usage: ./load_env.sh <script_name> [args...]

if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
    echo "Environment variables loaded from .env"
    "$@"
else
    echo "Error: .env file not found. Please create .env file with your API credentials."
    exit 1
fi
