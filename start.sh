#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if running as root
if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run as root"
    exit 1
fi

# Check config.ini exists
if [ ! -f "$SCRIPT_DIR/config.ini" ]; then
    echo "Error: config.ini not found in $SCRIPT_DIR"
    exit 1
fi

# Install Python 3 if not present
if ! command -v python3 &> /dev/null; then
    apt-get update && apt-get install -y python3 python3-pip
fi

# Install Python dependencies
pip3 install -r "$SCRIPT_DIR/requirements.txt"

# Run the automation
python3 "$SCRIPT_DIR/main.py"
