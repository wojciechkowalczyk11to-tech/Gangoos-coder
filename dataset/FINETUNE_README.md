# Finetuning Pipeline - Quick Reference

Complete implementation of QLoRA finetuning for Qwen 2.5 and DeepSeek-R1 models.

## Files

- **`finetune_pipeline.py`** (23 KB) - Main training script with all features
- **`FINETUNING_GUIDE.md`** (17 KB) - Complete step-by-step guide
- **`quick_start.sh`** - Bash wrapper for easy launching
- **`FINETUNE_README.md`** - This file

## Quick Start

### 1. Dry Run (Test Setup - 5 minutes)

```bash
cd /sessions/loving-beautiful-mccarthy/Gangoos-coder/dataset
python3 finetune_pipeline.py --dry-run --no-merge --no-gguf
```

Or using the helper script:

```bash
./quick_start.sh --dry-run
```

### 2. Full Training (1-2 hours depending on GPU)

```bash
python3 finetune_pipeline.py
```

Or with custom model:

```bash
python3 finetune_pipeline.py --model "Qwen/Qwen2.5-3B"
```

### 3. Monitor Training

In a new terminal:

```bash
tensorboard --logdir /sessions/loving-beautiful-mccarthy/Gangoos-coder/models/finetuned/logs
# Open browser to http://localhost:6006
```

## Features

### Script Capabilities

✓ **Automatic dependency installation**
- Unsloth, transformers, datasets, peft, trl, bitsandbytes
- Uses pip, works anywhere

✓ **GPU detection & VRAM reporting**
- Auto-detects CUDA availability
- Prints VRAM capacity
- Graceful fallback if GPU unavailable

✓ **Data loading from multiple JSONL sources**
- Supports OpenAI messages format
- Handles execution_traces.jsonl, execution_traces_v2.jsonl, gangoos_coder_dataset.jsonl
- Automatic deduplication of message formats
- Clear error messages for malformed data

✓ **Chat template formatting**
- Auto-detects model type (Qwen, DeepSeek, etc.)
- Applies correct prompt formatting per model
- Handles system/user/assistant roles

✓ **Production-grade QLoRA configuration**
- 4-bit quantization (BNB)
- Rank: 16, Alpha: 32, Dropout: 0.05
- Target modules: q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj
- Gradient checkpointing for memory efficiency

✓ **Optimized training config**
- 3 epochs, batch_size=2, grad_accum=4
- Cosine learning rate scheduler
- 2e-4 initial LR with warmup
- Max sequence length: 2048 (configurable)
- Automatic train/eval split (90/10)

✓ **Model merge & export**
- Saves LoRA adapter separately
- Merges LoRA into base model
- Exports to GGUF Q4_K_M for Ollama
- Prints deployment instructions

✓ **Robust error handling**
- Graceful handling of missing files
- Clear error messages for debugging
- Keyboard interrupt support (Ctrl+C saves state)
- Dry-run mode for testing

✓ **Training monitoring**
- TensorBoard integration
- Eval loss tracking
- Automatic checkpoint saving
- Instructions for early stopping

## Configuration

### Model Selection

**Qwen 2.5 (Recommended)**
```bash
--model "Qwen/Qwen2.5-7B-Instruct"  # Best balance (default)
--model "Qwen/Qwen2.5-3B"            # Faster, lower VRAM
--model "Qwen/Qwen2.5-14B-Instruct"  # Larger, slower
```

**DeepSeek-R1**
```bash
--model "deepseek-ai/deepseek-r1"    # 8B version with reasoning
```

### Training Hyperparameters

Edit `setup_training_args()` in `finetune_pipeline.py`:

```python
num_train_epochs=3,              # Increase for more training
per_device_train_batch_size=2,   # Reduce if OOM
gradient_accumulation_steps=4,   # Increase for larger effective batch
learning_rate=2e-4,              # Adjust if loss doesn't decrease
warmup_ratio=0.03,               # % of training for warmup
max_grad_norm=1.0,               # Gradient clipping
```

### QLoRA Configuration

Edit `setup_lora_config()`:

```python
r=16,                  # LoRA rank (16-64 common)
lora_alpha=32,        # Scaling factor
lora_dropout=0.05,    # Dropout in LoRA layers
```

Higher rank = more capacity but slower training.

## Output Structure

```
/sessions/loving-beautiful-mccarthy/Gangoos-coder/models/finetuned/
├── logs/                          # TensorBoard logs
│   ├── events.out.tfevents.*
│   └── runs/
├── checkpoint-100/                # Intermediate checkpoints
├── checkpoint-200/
└── (training in progress)
├── lora_adapter/                  # Final LoRA adapter
│   ├── adapter_config.json
│   ├── adapter_model.bin
│   └── tokenizer.json
├── merged_model/                  # Merged full model
│   ├── config.json
│   ├── model.safetensors
│   └── tokenizer.json
└── model_Q4_K_M.gguf             # GGUF for Ollama (4-bit)
```

## Command Reference

### Basic Usage

```bash
# Dry run (tests setup with 5 examples)
python3 finetune_pipeline.py --dry-run --no-merge --no-gguf

# Full training (all data, all steps)
python3 finetune_pipeline.py

# Custom model
python3 finetune_pipeline.py --model "Qwen/Qwen2.5-3B"

# Skip dependencies if already installed
python3 finetune_pipeline.py --skip-install

# Load data without training (for debugging)
python3 finetune_pipeline.py --no-train

# Save only adapter, skip merge
python3 finetune_pipeline.py --no-merge

# Skip GGUF export
python3 finetune_pipeline.py --no-gguf

# Custom sequence length
python3 finetune_pipeline.py --max-seq-length 4096

# Combine multiple options
python3 finetune_pipeline.py \
    --model "deepseek-ai/deepseek-r1" \
    --max-seq-length 2048 \
    --output-dir ./custom_output \
    --no-gguf
```

## Expected Performance

### Training Time

| GPU | Model | Time (3 epochs) |
|-----|-------|-----------------|
| RTX 4090 | Qwen2.5-7B | 45-60 min |
| RTX 6000 Ada | Qwen2.5-7B | 20-30 min |
| A100 40GB | Qwen2.5-7B | 15-20 min |
| RTX 3090 | Qwen2.5-3B | 30-45 min |

### Loss Progression (Expected)

```
Epoch 1: loss ~3.0 → 2.5
Epoch 2: loss ~2.5 → 2.0
Epoch 3: loss ~2.0 → 1.8-1.7
Eval loss typically 0.3-0.5 higher than train loss
```

### VRAM Usage

- Base model (4-bit): 4-6 GB
- Training overhead (batch=2, grad_accum=4): +4-6 GB
- **Total: 8-12 GB VRAM required**
- Activation checkpointing reduces by 20-30%

## Monitoring

### During Training

**Option 1: TensorBoard**
```bash
tensorboard --logdir ./models/finetuned/logs --port 6006
# Open http://localhost:6006
```

**Option 2: Log file**
```bash
tail -f ./models/finetuned/logs/run.log
```

**Key metrics to watch:**
- `loss`: Training loss (should decrease)
- `eval_loss`: Validation loss (should decrease, then plateau)
- `learning_rate`: Should decay smoothly
- `throughput`: Tokens/second (should be stable)

### When to Stop

Stop training early if:
1. Eval loss stops decreasing for 5+ eval steps
2. Training loss << eval loss (overfitting)
3. Training loss spikes suddenly (NaN or learning rate too high)

## Troubleshooting

### CUDA Out of Memory

```bash
# Option 1: Reduce batch size
# Edit line 300: per_device_train_batch_size=1

# Option 2: Smaller model
python3 finetune_pipeline.py --model "Qwen/Qwen2.5-3B"

# Option 3: Shorter sequences
python3 finetune_pipeline.py --max-seq-length 1024
```

### Training Loss Not Decreasing

Check data quality:
```bash
python3 -c "
import json
count = 0
with open('execution_traces.jsonl') as f:
    for line in f:
        data = json.loads(line)
        if 'messages' in data:
            count += 1
print(f'Valid examples: {count}')
"
```

### Model Not Found

```bash
# Clear HuggingFace cache
rm -rf ~/.cache/huggingface/hub

# Re-run (will re-download)
python3 finetune_pipeline.py
```

See **FINETUNING_GUIDE.md** for comprehensive troubleshooting.

## Deployment

### Export to Ollama (GGUF)

The script attempts automatic export. If it fails:

```bash
# Manual conversion
cd ./models/finetuned
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp && make quantize

# Convert
python3 convert.py --outfile merged.gguf ../merged_model

# Quantize (4-bit)
./quantize merged.gguf gangoos-coder-q4km.gguf Q4_K_M
```

### Run with Ollama

```bash
# Create Modelfile
cat > Modelfile << 'EOF'
FROM ./gangoos-coder-q4km.gguf
TEMPLATE "[INST] {{ .Prompt }} [/INST]"
EOF

# Create model
ollama create gangoos-coder -f Modelfile

# Run
ollama run gangoos-coder
```

### API Usage

```python
import requests

response = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "gangoos-coder",
        "prompt": "def fibonacci(n):",
        "stream": False
    }
)

print(response.json()["response"])
```

## Advanced Usage

### Use Different Optimizer

Edit `setup_training_args()`:

```python
optim="adafactor"      # Default is paged_adamw_32bit
# Other options: adamw_torch, adamw_bnb_8bit, etc.
```

### Wandb Integration

```bash
# Install and authenticate
pip install wandb
wandb login

# In script, change:
report_to=["wandb"]  # Instead of ["tensorboard"]
```

### Fine-tune on Specific Layer

Edit `setup_lora_config()`:

```python
target_modules=[
    "q_proj",      # Query attention (important)
    "v_proj",      # Value attention (important)
]  # Skip k_proj, o_proj for lighter training
```

### Multi-GPU Training

The script auto-detects multi-GPU setup via `device_map="auto"`. For explicit control:

```bash
# Use only first GPU
CUDA_VISIBLE_DEVICES=0 python3 finetune_pipeline.py

# Use GPUs 0,1,2
CUDA_VISIBLE_DEVICES=0,1,2 python3 finetune_pipeline.py
```

## Data Format

JSONL files must contain `messages` field in OpenAI format:

```json
{
  "messages": [
    {"role": "system", "content": "You are a code assistant."},
    {"role": "user", "content": "Write a function to..."},
    {"role": "assistant", "content": "Here's the function:\n\n```python\ndef ..."}
  ]
}
```

One conversation per line.

## System Requirements

**Minimum:**
- Python 3.8+
- 24 GB GPU VRAM (RTX 4090, RTX 6000, A100)
- 100 GB disk space
- 8 GB CPU RAM

**Recommended:**
- Python 3.10+
- 40+ GB GPU VRAM (A100, H100)
- 200 GB SSD
- 16 GB CPU RAM
- NVIDIA GPU (CUDA 12.0+)

## Support

- **Documentation:** See FINETUNING_GUIDE.md
- **Issues:** Check script output and TensorBoard logs
- **Debugging:** Use `--no-train` to test data loading
- **Questions:** See Troubleshooting section

## License

This pipeline uses:
- Unsloth (MIT License)
- Transformers (Apache 2.0)
- PyTorch (BSD)

Model weights may have specific licenses - verify before commercial use.
