# Gangoos-Coder Finetuning Guide

Complete guide for finetuning Qwen 2.5 or DeepSeek-R1 models using QLoRA on RunPod or local GPU machines.

## Table of Contents

1. [RunPod Setup](#runpod-setup)
2. [Running the Pipeline](#running-the-pipeline)
3. [Monitoring Training](#monitoring-training)
4. [Evaluating the Model](#evaluating-the-model)
5. [Deploying to Ollama](#deploying-to-ollama)
6. [Cost Estimates](#cost-estimates)
7. [Troubleshooting](#troubleshooting)

---

## RunPod Setup

### Step 1: Choose a Template

Log in to [RunPod.io](https://runpod.io/) and select a GPU pod with one of these configurations:

**Recommended GPU Options:**
- **RTX 4090** (24GB VRAM) - Best price/performance for this workload
  - Est. cost: $0.44-0.60/hour
  - Training time: ~30-45 min for 3 epochs

- **RTX 6000 Ada** (48GB VRAM) - Faster training, can use larger batches
  - Est. cost: $1.22-1.89/hour
  - Training time: ~15-20 min for 3 epochs

- **A100 (40GB)** - Very fast but more expensive
  - Est. cost: $1.20-1.50/hour
  - Training time: ~10-15 min for 3 epochs

**Minimum GPU:** RTX 3090 (24GB) or RTX 4000 (24GB)

### Step 2: Start a Pod

1. Click **Deploy** on your chosen template
2. Select **Pytorch** or **CUDA 12.0** base image
3. Choose the GPU from the dropdown
4. Click **Deploy** and wait for the pod to start (2-3 minutes)

### Step 3: Open Jupyter/Terminal

Once running:
- Click **Connect** to open Jupyter or terminal
- Choose **Jupyter Lab** or **SSH** connection method

### Step 4: Clone/Download the Code

If using terminal:

```bash
# Install git if needed
apt-get update && apt-get install -y git

# Clone your repo (or download the files)
cd /root
git clone <your-repo-url> Gangoos-coder
cd Gangoos-coder/dataset
```

If you don't have a git repo, copy the files directly:
- Upload `finetune_pipeline.py` to `/root/Gangoos-coder/dataset/`
- Upload your JSONL dataset files

---

## Running the Pipeline

### Option A: Minimal Setup (Recommended First Run)

```bash
cd /root/Gangoos-coder/dataset

# Dry run to test the setup (loads 5 examples only)
python finetune_pipeline.py --dry-run --no-merge --no-gguf
```

This will:
- Install dependencies
- Load and format 5 example conversations
- Verify everything works without spending compute time

### Option B: Full Training Run

```bash
cd /root/Gangoos-coder/dataset

# Full training with Qwen 2.5 (default)
python finetune_pipeline.py \
    --model "Qwen/Qwen2.5-7B-Instruct" \
    --dataset-dir /root/Gangoos-coder/dataset \
    --output-dir /root/Gangoos-coder/models/finetuned
```

### Option C: Using DeepSeek-R1 (8B)

```bash
python finetune_pipeline.py \
    --model "deepseek-ai/deepseek-r1" \
    --output-dir /root/Gangoos-coder/models/deepseek-finetuned
```

### Script Arguments Explained

```bash
python finetune_pipeline.py \
    --model MODEL_NAME              # Base model to finetune
    --dataset-dir PATH              # Where JSONL files are located
    --output-dir PATH               # Where to save checkpoints/final model
    --max-seq-length 2048           # Max token length (2048 is good for code)
    --dry-run                       # Test with 5 examples only
    --skip-install                  # Skip dependency install (if already done)
    --no-train                      # Load data but don't train
    --no-merge                      # Keep LoRA separate from base model
    --no-gguf                       # Skip GGUF export
```

### Expected Output During Training

```
🧠 GANGOOS-CODER FINETUNING PIPELINE
================================================================================
Model: Qwen/Qwen2.5-7B-Instruct
Dataset: /root/Gangoos-coder/dataset
Output: /root/Gangoos-coder/models/finetuned
Max seq length: 2048
================================================================================

✓ GPU detected: NVIDIA RTX 4090
✓ CUDA available: 12.0
✓ VRAM: 24.0 GB

📦 Installing dependencies...
  Installing unsloth...
  Installing transformers...
  [... more packages ...]
✓ Dependencies installed

📂 Loading datasets...
  Loading execution_traces.jsonl...
✓ Loaded 2,547 conversations

📝 Formatting data for training...
✓ Formatted 2,547 training examples

🤖 Loading model: Qwen/Qwen2.5-7B-Instruct...
✓ Model and tokenizer loaded
✓ LoRA modules attached

🔄 Preparing datasets...
✓ Train examples: 2,292
✓ Eval examples: 255

🚀 Starting training...
[Training progress...]
```

---

## Monitoring Training

### Real-Time Monitoring with TensorBoard

While training is running, open a **new terminal** in RunPod and run:

```bash
# Start tensorboard
tensorboard --logdir /root/Gangoos-coder/models/finetuned/logs --port 6006

# Then open browser to: http://<runpod-ip>:6006
```

**Key metrics to watch:**

- **Training Loss** - Should decrease smoothly
- **Eval Loss** - Should decrease initially, then plateau
- **Learning Rate** - Cosine scheduler, starts at 2e-4, decays to ~0
- **Throughput** - Tokens/sec (should stay consistent)

### When to Stop Training Early

The script trains for 3 epochs by default. You can interrupt earlier if:

1. **Eval loss plateaus** - Stops decreasing for 3+ eval steps
   ```
   Step 50: eval_loss = 2.34
   Step 60: eval_loss = 2.33
   Step 70: eval_loss = 2.32  <- Very small improvement
   Step 80: eval_loss = 2.31  <- Diminishing returns
   ```

2. **Overfitting starts** - Train loss << eval loss
   ```
   Step 100: train_loss=0.8, eval_loss=2.5  <- Gap widening = overfitting
   ```

3. **Training loss spikes** - Possible NaN or learning rate issue
   ```
   -> Handle by reducing learning rate to 1e-4 and restarting
   ```

**To interrupt training gracefully:**
```bash
# Press Ctrl+C in the terminal
# The script saves checkpoints automatically
```

---

## Evaluating the Model

### Option 1: Quick Eval on Test Set (Automatic)

The script evaluates on 10% of data during training. Check tensorboard for eval loss.

### Option 2: Manual Evaluation Script

Create `evaluate.py`:

```python
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# Load the finetuned model
model_path = "/root/Gangoos-coder/models/finetuned/merged_model"
tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    torch_dtype=torch.bfloat16,
    device_map="auto"
)

# Test prompt
prompt = """
def fibonacci(n):
    \"\"\"Calculate fibonacci number at position n\"\"\"
"""

# Generate
inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
outputs = model.generate(
    **inputs,
    max_new_tokens=200,
    temperature=0.7,
    top_p=0.9,
    do_sample=True
)

result = tokenizer.decode(outputs[0])
print(result)
```

Run with:
```bash
cd /root/Gangoos-coder/models/finetuned
python evaluate.py
```

### Option 3: A/B Test with Base Model

Compare finetuned vs. base model outputs:

```python
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# Load base model
base_model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-7B-Instruct",
    torch_dtype=torch.bfloat16,
    device_map="auto"
)
base_tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-7B-Instruct")

# Load finetuned model
ft_model = AutoModelForCausalLM.from_pretrained(
    "/root/Gangoos-coder/models/finetuned/merged_model",
    torch_dtype=torch.bfloat16,
    device_map="auto"
)
ft_tokenizer = AutoTokenizer.from_pretrained(
    "/root/Gangoos-coder/models/finetuned/merged_model"
)

test_prompts = [
    "Write a function to check if a number is prime",
    "def merge_sorted_arrays",
    "How do I load a CSV file in pandas?",
]

for prompt in test_prompts:
    print(f"\nPrompt: {prompt}")
    print("-" * 50)

    # Base model
    inputs = base_tokenizer(prompt, return_tensors="pt").to(base_model.device)
    base_out = base_model.generate(**inputs, max_new_tokens=100)
    print(f"Base: {base_tokenizer.decode(base_out[0])}")

    # Finetuned
    inputs = ft_tokenizer(prompt, return_tensors="pt").to(ft_model.device)
    ft_out = ft_model.generate(**inputs, max_new_tokens=100)
    print(f"FT:   {ft_tokenizer.decode(ft_out[0])}")
```

---

## Deploying to Ollama

### Prerequisites

You need Ollama installed on the target machine:

**On Mac:**
```bash
# Download from https://ollama.ai
# Or: brew install ollama
```

**On Linux:**
```bash
curl https://ollama.ai/install.sh | sh
```

**On Windows:**
Download from https://ollama.ai/download

### Step 1: Export to GGUF Format

The `finetune_pipeline.py` attempts this automatically, but if it fails:

**Manual GGUF Conversion:**

```bash
cd /root/Gangoos-coder/models/finetuned

# Install llama.cpp
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp

# Build quantization tool
make quantize

# Convert model
python3 convert.py --outfile merged.gguf ../merged_model

# Quantize to Q4_K_M (4-bit, 80% original size)
./quantize merged.gguf gangoos-coder-q4km.gguf Q4_K_M

# Move to accessible location
cp gangoos-coder-q4km.gguf /root/Gangoos-coder/models/
```

### Step 2: Create Modelfile

Create `/home/user/Modelfile`:

```dockerfile
FROM ./gangoos-coder-q4km.gguf

TEMPLATE "[INST] {{ .Prompt }} [/INST]"

PARAMETER stop "[INST]"
PARAMETER stop "[/INST]"
PARAMETER temperature 0.7
PARAMETER top_k 40
PARAMETER top_p 0.9
PARAMETER num_predict 512

SYSTEM "You are Gangoos-Coder, an AI assistant specialized in writing and analyzing code."
```

### Step 3: Create the Ollama Model

```bash
cd /home/user

# Create model (registers it with Ollama)
ollama create gangoos-coder -f Modelfile

# Verify it was created
ollama list | grep gangoos
```

### Step 4: Run the Model

**Interactive:**
```bash
ollama run gangoos-coder
```

Then you can chat:
```
>>> def fibonacci(n):
This function will calculate the nth Fibonacci number...
```

**Programmatic (Python):**

```python
import requests
import json

def query_gangoos(prompt: str) -> str:
    """Query the finetuned Gangoos-Coder model."""
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "gangoos-coder",
            "prompt": prompt,
            "stream": False,
            "temperature": 0.7,
        }
    )

    if response.status_code == 200:
        return response.json()["response"]
    else:
        raise Exception(f"Ollama error: {response.text}")

# Test it
result = query_gangoos("def is_palindrome(s):")
print(result)
```

**Using Ollama API server:**

Start Ollama in server mode:
```bash
# On Linux/Mac
OLLAMA_HOST=0.0.0.0:11434 ollama serve

# Then access from any machine via:
# http://<your-ip>:11434/api/generate
```

### Step 5: Deploy on Multiple Machines

**On EliteBook:**
1. Install Ollama
2. Copy `gangoos-coder-q4km.gguf` to `~/.ollama/models/`
3. Create Modelfile and run `ollama create gangoos-coder -f Modelfile`

**On VM1:**
Same steps as EliteBook

**Sync models between machines:**
```bash
# Backup the model
tar czf gangoos-coder.tar.gz \
    ~/.ollama/models/blobs/ \
    ~/.ollama/models/manifests/

# Transfer to another machine and extract
tar xzf gangoos-coder.tar.gz -C ~/
```

---

## Cost Estimates

### RunPod GPU Pricing (as of 2026-04)

| GPU | Cost/Hour | Training Time (3 epochs) | Total Cost |
|-----|-----------|--------------------------|-----------|
| RTX 4090 | $0.50 | 45 min | ~$0.38 |
| RTX 6000 Ada | $1.50 | 20 min | ~$0.50 |
| A100 40GB | $1.40 | 15 min | ~$0.35 |
| H100 | $3.00 | 10 min | ~$0.50 |

**Cost optimization tips:**

1. **Use spot instances** - 30-50% cheaper but can be interrupted
2. **Train during off-peak hours** - Usually cheaper
3. **Use smaller models** - Qwen 7B vs Qwen 32B saves cost
4. **Reduce epochs** - Go from 3 to 2 epochs to save ~33%
5. **Increase batch size** - More efficient (if VRAM allows)

### Data Transfer Costs

- **Model download** (first run): ~4-5 GB from Hugging Face = minimal cost
- **No egress charges** if staying within RunPod ecosystem

### Storage Costs

- **Temporary storage** (pod runtime): Included in hourly cost
- **Persistent storage**: ~$0.25/GB/month (optional)

**Example: Full training lifecycle**

```
Dry run test:        5 min  × $0.50 = $0.04
Full training:      50 min  × $0.50 = $0.42
GGUF export:        10 min  × $0.50 = $0.08
Evaluation:          5 min  × $0.50 = $0.04
─────────────────────────────────────
TOTAL:              ~$0.58
```

---

## Troubleshooting

### Problem: CUDA Out of Memory (OOM)

**Error message:**
```
RuntimeError: CUDA out of memory. Tried to allocate X.XX GiB
```

**Solutions (in order):**

1. **Reduce batch size:**
   ```bash
   # Edit finetune_pipeline.py, line ~300:
   per_device_train_batch_size=1  # Reduced from 2
   ```

2. **Increase gradient accumulation:**
   ```python
   gradient_accumulation_steps=8  # Increased from 4
   ```

3. **Reduce max sequence length:**
   ```bash
   python finetune_pipeline.py --max-seq-length 1024
   ```

4. **Enable activation checkpointing** (already enabled in script)

5. **Use smaller model:**
   ```bash
   python finetune_pipeline.py --model "Qwen/Qwen2.5-3B"
   ```

6. **Use different GPU** (RunPod) with more VRAM

### Problem: Training Loss Not Decreasing

**Possible causes:**

1. **Learning rate too high/low:**
   - Edit `setup_training_args()` in script, try `1e-5` or `5e-4`

2. **Data quality issues:**
   - Check JSONL format with: `python -m json.tool < execution_traces.jsonl | head -50`

3. **Insufficient data:**
   - Need at least 500-1000 training examples
   - Check: `echo $(wc -l execution_traces.jsonl)`

4. **Model mismatch:**
   - Ensure tokenizer matches model
   - Check chat template for your model

**Debug with:**
```bash
python finetune_pipeline.py --no-train  # Just load and format data
# Inspect output in logs/
```

### Problem: Model Not Found

**Error:**
```
OSError: Can't find 'model.safetensors' in HuggingFace
```

**Solution:**
```bash
# Check internet connection
ping huggingface.co

# Clear cache and retry
rm -rf ~/.cache/huggingface/
python finetune_pipeline.py  # Will re-download
```

### Problem: Ollama Model Creation Fails

**Error:**
```
Error: failed to load model: invalid GGUF file
```

**Solution:**
1. Verify GGUF file isn't corrupted:
   ```bash
   ls -lh gangoos-coder-q4km.gguf  # Should be 4-8GB
   file gangoos-coder-q4km.gguf    # Should show GGUF format
   ```

2. Re-export GGUF:
   ```bash
   cd llama.cpp
   ./quantize ../merged_model/model.safetensors gangoos.gguf Q4_K_M
   ```

3. Use simpler Modelfile:
   ```dockerfile
   FROM ./gangoos-coder-q4km.gguf
   ```

### Problem: Slow Training Speed

**Expected speeds (tokens/sec):**
- RTX 4090: 600-800 tokens/sec
- A100: 1200-1500 tokens/sec
- RTX 3090: 400-500 tokens/sec

**If too slow:**

1. Check GPU usage:
   ```bash
   nvidia-smi -l 1  # Monitor GPU %
   ```

2. Enable packing in script (already done):
   - Groups multiple examples together

3. Increase batch size (if VRAM allows):
   ```python
   per_device_train_batch_size=4
   ```

4. Use smaller model:
   ```bash
   --model "Qwen/Qwen2.5-3B"
   ```

### Problem: Finetuned Model Performs Worse Than Base

**Possible causes:**

1. **Overfitting** - Training for too many epochs
   - Check tensorboard: if train_loss << eval_loss, reduce epochs

2. **Catastrophic forgetting** - Model losing general knowledge
   - Reduce learning rate to `1e-5`
   - Use more diverse dataset

3. **Bad data** - Poor quality training examples
   - Filter/clean JSONL files
   - Ensure proper chat template format

**Verify data quality:**
```bash
python -c "
import json
with open('execution_traces.jsonl') as f:
    for i, line in enumerate(f):
        data = json.loads(line)
        msgs = data.get('messages', [])
        print(f'Example {i}: {len(msgs)} messages, {sum(len(m.get(\"content\",\"\")) for m in msgs)} chars')
        if i >= 10: break
"
```

---

## Next Steps

1. **First run:** Use `--dry-run` to test setup (takes ~5 minutes)
2. **Full training:** Run without flags for complete pipeline (takes ~1 hour)
3. **Evaluate:** Check tensorboard during training
4. **Deploy:** Export to GGUF and create Ollama model
5. **Integrate:** Use in your applications via Ollama API

## Additional Resources

- **Unsloth GitHub:** https://github.com/unslothai/unsloth
- **Ollama Docs:** https://ollama.ai/docs
- **TRL Docs:** https://huggingface.co/docs/trl
- **QLoRA Paper:** https://arxiv.org/abs/2305.14314
- **Qwen Models:** https://huggingface.co/Qwen

---

**Questions or issues?** Check the Troubleshooting section or review logs in:
```
/root/Gangoos-coder/models/finetuned/logs/
```
