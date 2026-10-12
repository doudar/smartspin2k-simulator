#!/bin/sh
set -eu
# All /inputs mounts are read-only; no token environment or Docker socket exists.
mkdir -p /tmp/work
cd /tmp/work
for item in simulator adapter baseline candidate; do cp -a "/inputs/$item" "$item"; done
cp /inputs/experiment-plan.json .
cp -a /inputs/fixtures fixtures
export PYTHONPATH=/tmp/work/simulator
exec python simulator/dashboard/automation_batch.py --plan experiment-plan.json --revision "$1" --suite "$2" --output /output
