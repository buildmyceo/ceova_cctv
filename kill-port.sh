#!/bin/bash
PORT=1425
PID=$(lsof -ti tcp:$PORT)

if [ -z "$PID" ]; then
  echo "Port $PORT is free"
else
  echo "Killing process on port $PORT (PID: $PID)"
  kill -9 $PID
fi
