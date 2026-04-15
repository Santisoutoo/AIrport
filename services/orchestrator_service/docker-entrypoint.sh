#!/bin/sh
set -e

if [ -n "$GOOGLE_APPLICATION_CREDENTIALS_JSON" ]; then
    echo "$GOOGLE_APPLICATION_CREDENTIALS_JSON" > /tmp/sa-key.json
    export GOOGLE_APPLICATION_CREDENTIALS=/tmp/sa-key.json
fi

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8006}"
