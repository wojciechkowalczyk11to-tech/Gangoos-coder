#!/bin/bash
# Uruchamia N równoległych pętli battle.py
# Użycie: ./run_parallel.sh [N=4] [max_per_loop=125]
# Wynik: output/loop_{0..N}/mojo_dataset.jsonl → merge → output/final.jsonl

N=${1:-4}
MAX=${2:-125}   # 4 × 125 = 500 łącznie
LEVELS=(1 1 2 2)  # poziomy trudności per loop

echo "[*] Uruchamiam $N pętli × $MAX zadań = $((N * MAX)) łącznie"
echo "[*] PID-y będą zapisane do /tmp/battle_pids"
> /tmp/battle_pids

for i in $(seq 0 $((N - 1))); do
    OUTDIR="output/loop_$i"
    mkdir -p "$OUTDIR"
    LEVEL=${LEVELS[$i]:-1}
    LOG="$OUTDIR/battle.log"

    python3 orchestrator/battle.py \
        --level "$LEVEL" \
        --max "$MAX" \
        --out "$OUTDIR/mojo_dataset.jsonl" \
        > "$LOG" 2>&1 &

    PID=$!
    echo "$PID" >> /tmp/battle_pids
    echo "[loop_$i] PID=$PID level=$LEVEL → $OUTDIR/mojo_dataset.jsonl (log: $LOG)"
done

echo ""
echo "[*] Wszystkie pętle uruchomione. Monitoruj:"
echo "    tail -f output/loop_*/battle.log"
echo ""
echo "[*] Czekam na zakończenie wszystkich..."
wait

echo ""
echo "[*] Merge wyników..."
python3 -c "
import json, glob, os
examples = []
seen = set()
for f in sorted(glob.glob('output/loop_*/mojo_dataset.jsonl')):
    with open(f) as fh:
        for line in fh:
            line = line.strip()
            if not line: continue
            ex = json.loads(line)
            key = ex.get('metadata',{}).get('task','')[:80]
            if key not in seen:
                seen.add(key)
                examples.append(ex)
os.makedirs('output', exist_ok=True)
with open('output/final_mojo_dataset.jsonl','w') as out:
    for ex in examples:
        out.write(json.dumps(ex, ensure_ascii=False) + '\n')
print(f'Merged: {len(examples)} unique examples → output/final_mojo_dataset.jsonl')
"
