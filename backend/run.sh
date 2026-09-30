#!/bin/bash

#python3.13 -m venv myenv

# Mongo db name
export DB_NAME="${DB_NAME:-bong_hneshel_db}"
PORT="${PORT:-8002}"

if [ -d "myenv" ]; then
  source myenv/bin/activate
elif [ -d ".venv" ]; then
  source .venv/bin/activate
fi

# pip3 install -r requirements.txt
uvicorn server:app --reload --port $PORT


