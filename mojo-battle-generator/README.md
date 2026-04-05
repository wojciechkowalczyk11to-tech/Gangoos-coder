# Mojo Battle Generator — DeepSeek R1 Self-Improvement Loop

Generuje dataset Mojo dla fine-tuningu Qwen 9B na EliteBook (maj/czerwiec 2026).

## Architektura

```
DeepSeek R1 (API) w pętli
    ├── tool: puter.js → Claude Opus FREE (weryfikator)
    ├── tool: mojo_exec → Docker Mojo runtime
    └── tool: web_search → dokumentacja Mojo
         ↓ samodoskonalenie co 10 zadań
    output/mojo_dataset.jsonl
         ↓ RunPod RTX 4090
    Qwen2.5-Coder-7B fine-tuned
         ↓ Q4 quantization
    EliteBook (lokalny model)
```

## Uruchomienie

### 1. Puter bridge (darmowy Opus)
```bash
cd puter-bridge
npm install
node index.js &
```

### 2. Mojo Docker (opcjonalnie, fallback = symulacja)
```bash
docker pull modular/mojo:latest
```

### 3. Generator
```bash
cd orchestrator
python3 battle.py --level 1 --max 500 --out ../output/mojo_dataset.jsonl
```

### 4. Fine-tuning na RunPod
```
GPU: RTX 4090 (24GB) ~$0.74/h
Czas: ~2-4h dla 500 przykładów
```
```bash
# Na RunPod pod:
pip install unsloth[colab-new] trl peft
python3 finetune/train_qwen.py
```

## Struktura datasetu

Każdy przykład = multi-turn conversation:
- User: zadanie Mojo
- Assistant: rozwiązanie + tool calls
- User: wynik wykonania (mojo_exec)
- Assistant: debug/fix
- ... (error→fix flow)
- Final: działający kod z wyjaśnieniem

## Poziomy trudności

| Level | Kategoria | Przykłady |
|-------|-----------|-----------|
| 1 | basics | fibonacci, sorting, structs |
| 2 | performance | SIMD, parallelize, UnsafePointer |
| 3 | advanced | generics, traits, async |
| 4 | systems | allocators, HTTP parser, C bindings |

Level rośnie automatycznie gdy success rate > 70%.

## Cel: maj/czerwiec 2026

Fine-tuned Qwen 9B Q4 (~5GB RAM) uruchamiany lokalnie na EliteBook HP.
