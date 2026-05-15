#!/bin/bash
# ============================================================
# Mac Launcher: Runs 3 workers (chunks 0, 1, 2) in parallel
# Usage: chmod +x run_mac.sh && ./run_mac.sh
# ============================================================

cd "$(dirname "$0")"

echo "============================================================"
echo "Starting 3 annotation workers on Mac (chunks 0, 1, 2)"
echo "============================================================"
echo ""

# Keep Mac awake
caffeinate -s &
CAFFEINATE_PID=$!
echo "caffeinate started (PID $CAFFEINATE_PID)"

# Create log directory
mkdir -p logs

# Start workers in background, with logs
echo "Starting Worker 0..."
python3 worker.py 0 > logs/worker_0.log 2>&1 &
W0=$!
sleep 3

echo "Starting Worker 1..."
python3 worker.py 1 > logs/worker_1.log 2>&1 &
W1=$!
sleep 3

echo "Starting Worker 2..."
python3 worker.py 2 > logs/worker_2.log 2>&1 &
W2=$!

echo ""
echo "All workers started:"
echo "  Worker 0: PID $W0 → logs/worker_0.log"
echo "  Worker 1: PID $W1 → logs/worker_1.log"
echo "  Worker 2: PID $W2 → logs/worker_2.log"
echo ""
echo "Monitor progress:"
echo "  tail -f logs/worker_0.log"
echo "  tail -f logs/worker_1.log"
echo "  tail -f logs/worker_2.log"
echo ""
echo "Or check all at once:"
echo "  wc -l results/worker_*.jsonl"
echo ""

# Wait for all workers to finish
wait $W0 $W1 $W2

# Stop caffeinate
kill $CAFFEINATE_PID 2>/dev/null

echo ""
echo "============================================================"
echo "All 3 Mac workers complete!"
echo "  Check results/worker_0.jsonl, worker_1.jsonl, worker_2.jsonl"
echo "============================================================"
