"""
Fine-tuning Qwen2.5-Coder-7B / Qwen3-9B na Mojo battle dataset.
Używa Unsloth (4x szybszy niż HuggingFace) + LoRA.
Uruchom na RunPod z RTX 4090 (24GB VRAM).

Setup RunPod:
  Template: RunPod PyTorch 2.4 + CUDA 12.1
  GPU: RTX 4090 (24GB) lub A100 (40GB)
  Disk: 50GB

  pip install unsloth[colab-new] xformers trl peft
"""
import json
import os
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
MODEL_NAME   = "Qwen/Qwen2.5-Coder-7B-Instruct"   # lub "Qwen/Qwen3-9B"
DATASET_PATH = "mojo_dataset.jsonl"
OUTPUT_DIR   = "./qwen-mojo-lora"
MAX_SEQ_LEN  = 4096
BATCH_SIZE   = 2
GRAD_ACCUM   = 4     # effective batch = 8
EPOCHS       = 3
LR           = 2e-4
LORA_R       = 16
LORA_ALPHA   = 32


def load_dataset(path: str):
    data = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            ex = json.loads(line)
            # Filtruj: tylko udane lub z error->fix flow
            meta = ex.get("metadata", {})
            if meta.get("success") or meta.get("turns", 0) > 1:
                data.append(ex)
    print(f"[*] Loaded {len(data)} training examples")
    return data


def format_chatml(example: dict) -> str:
    """Konwertuje do ChatML formatu."""
    out = ""
    for msg in example["messages"]:
        role = msg["role"]
        content = msg["content"]
        if role == "user":
            out += f"<|im_start|>user\n{content}<|im_end|>\n"
        elif role == "assistant":
            out += f"<|im_start|>assistant\n{content}<|im_end|>\n"
        elif role == "system":
            out += f"<|im_start|>system\n{content}<|im_end|>\n"
    return out


def main():
    from unsloth import FastLanguageModel
    from trl import SFTTrainer
    from transformers import TrainingArguments
    from datasets import Dataset

    print(f"[*] Loading model: {MODEL_NAME}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LEN,
        dtype=None,         # auto-detect
        load_in_4bit=True,  # QLoRA
    )

    # LoRA config
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        use_gradient_checkpointing="unsloth",
    )

    # Dataset
    raw_data = load_dataset(DATASET_PATH)
    texts = [format_chatml(ex) for ex in raw_data]
    hf_dataset = Dataset.from_dict({"text": texts})

    # Trainer
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=hf_dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LEN,
        args=TrainingArguments(
            per_device_train_batch_size=BATCH_SIZE,
            gradient_accumulation_steps=GRAD_ACCUM,
            num_train_epochs=EPOCHS,
            learning_rate=LR,
            fp16=not _is_bf16_supported(),
            bf16=_is_bf16_supported(),
            logging_steps=10,
            save_steps=100,
            output_dir=OUTPUT_DIR,
            warmup_ratio=0.05,
            lr_scheduler_type="cosine",
            report_to="none",
        ),
    )

    print("[*] Starting training...")
    trainer.train()

    # Zapisz
    model.save_pretrained(f"{OUTPUT_DIR}/final")
    tokenizer.save_pretrained(f"{OUTPUT_DIR}/final")
    print(f"[DONE] Model saved to {OUTPUT_DIR}/final")

    # Opcjonalnie: push to HuggingFace Hub
    # model.push_to_hub("your-username/qwen-mojo")


def _is_bf16_supported():
    import torch
    return torch.cuda.is_available() and torch.cuda.get_device_capability()[0] >= 8


if __name__ == "__main__":
    main()
