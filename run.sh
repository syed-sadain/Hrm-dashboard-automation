#!/usr/bin/env bash
# Convenience launcher: sets up venv (if missing), installs deps, runs the app.
set -e

if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate

echo "Installing dependencies..."
pip install -q -r requirements.txt

if [ ! -f ".env" ]; then
  echo "Creating .env from .env.example..."
  cp .env.example .env
fi

echo "Starting dashboard at http://localhost:5000 ..."
python app.py
