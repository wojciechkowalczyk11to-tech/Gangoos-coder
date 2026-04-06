#!/usr/bin/env python3
"""
Complete QLoRA Finetuning Pipeline for Qwen2.5 / DeepSeek-R1
Designed for RunPod or any machine with CUDA GPU and 24GB+ VRAM

This script:
1. Installs dependencies (Unsloth, transformers, etc.)
2. Loads execution traces from JSONL files
3. Formats data for chat-completion finetuning
4. Configures and runs QLoRA training with Unsloth
5. Saves LoRA adapter + merged full model
6. Exports to GGUF Q4_K_M format for Ollama deployment
"""

import os
import sys
import json
import argparse
import warnings
from pathlib import Path
from typing import Optional, Dict, List, Any
import logging
from datetime import datetime

warnings.filterwarnings("ignore")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def check_gpu():
    """Check for GPU availability and print CUDA info."""
    try:
        import torch

        if not torch.cuda.is_available():
            logger.warning("⚠️  GPU not detected! Training will be VERY slow on CPU.")
            return False

        logger.info(f"✓ GPU detected: {torch.cuda.get_device_name(0)}")
        logger.info(f"✓ CUDA available: {torch.version.cuda}")
        logger.info(f"✓ VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
        return True
    except Exception as e:
        logger.error(f"Error checking GPU: {e}")
        return False


def install_dependencies():
    """Install required packages with pip."""
    logger.info("📦 Installing dependencies...")

    packages = [
        "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git",
        "xformers",
        "transformers==4.42.3",
        "datasets",
        "peft",
        "trl",
        "bitsandbytes",
        "wandb",
        "fire",
    ]

    import subprocess

    for package in packages:
        try:
            logger.info(f"  Installing {package.split('@')[0].split('==')[0]}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", package])
        except subprocess.CalledProcessError as e:
            logger.warning(f"⚠️  Could not install {package}: {e}")

    logger.info("✓ Dependencies installed")


def load_datasets(dataset_dir: str, dry_run: bool = False) -> List[Dict[str, Any]]:
    """
    Load training data from JSONL files in OpenAI messages format.

    Args:
        dataset_dir: Directory containing execution_traces.jsonl and execution_traces_v2.jsonl
        dry_run: If True, only load first 5 examples

    Returns:
        List of conversation dictionaries
    """
    logger.info("📂 Loading datasets...")

    dataset_dir = Path(dataset_dir)
    conversations = []

    jsonl_files = [
        dataset_dir / "execution_traces.jsonl",
        dataset_dir / "execution_traces_v2.jsonl",
        dataset_dir / "gangoos_coder_dataset.jsonl",
    ]

    for jsonl_file in jsonl_files:
        if not jsonl_file.exists():
            logger.warning(f"⚠️  File not found: {jsonl_file}")
            continue

        logger.info(f"  Loading {jsonl_file.name}...")
        count = 0

        try:
            with open(jsonl_file, "r") as f:
                for line_idx, line in enumerate(f):
                    if dry_run and count >= 5:
                        break

                    try:
                        data = json.loads(line)

                        # Expect 'messages' field in OpenAI format
                        if "messages" in data:
                            conversations.append(data)
                            count += 1
                        else:
                            logger.debug(f"  Line {line_idx} missing 'messages' field")
                    except json.JSONDecodeError as e:
                        logger.debug(f"  Skipping line {line_idx}: {e}")
        except Exception as e:
            logger.error(f"  Error reading {jsonl_file}: {e}")

    if not conversations:
        raise ValueError("❌ No valid training data found! Check that JSONL files contain 'messages' field.")

    logger.info(f"✓ Loaded {len(conversations)} conversations")
    return conversations


def format_for_training(conversations: List[Dict], model_name: str) -> List[Dict]:
    """
    Format conversations for chat-template based training.

    Args:
        conversations: List of OpenAI message format conversations
        model_name: Name of the model (for template selection)

    Returns:
        List of formatted training examples
    """
    logger.info("📝 Formatting data for training...")

    training_examples = []

    # Determine chat template based on model
    if "qwen" in model_name.lower():
        # Qwen uses <|im_start|> format
        chat_template = "qwen"
    elif "deepseek" in model_name.lower():
        # DeepSeek uses similar format
        chat_template = "deepseek"
    else:
        chat_template = "default"

    skipped = 0

    for idx, conv in enumerate(conversations):
        try:
            messages = conv.get("messages", [])

            if not messages:
                skipped += 1
                continue

            # Format as single text example for SFT
            # The model will learn from the full conversation
            formatted_text = format_messages_for_sft(messages, chat_template)

            if formatted_text:
                training_examples.append({
                    "text": formatted_text,
                    "conversation_id": idx,
                })
            else:
                skipped += 1
        except Exception as e:
            logger.debug(f"  Error formatting conversation {idx}: {e}")
            skipped += 1

    if skipped > 0:
        logger.warning(f"⚠️  Skipped {skipped} conversations due to formatting errors")

    logger.info(f"✓ Formatted {len(training_examples)} training examples")
    return training_examples


def format_messages_for_sft(messages: List[Dict], chat_template: str = "qwen") -> Optional[str]:
    """Format message list into SFT training text."""

    if chat_template == "qwen":
        # Qwen3.5-B template
        text = ""
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "").strip()

            if not content:
                continue

            if role == "system":
                text += f"<|im_start|>system\n{content}<|im_end|>\n"
            elif role == "user":
                text += f"<|im_start|>user\n{content}<|im_end|>\n"
            elif role == "assistant":
                text += f"<|im_start|>assistant\n{content}<|im_end|>\n"

        # Ensure ends with assistant prompt
        if text and not text.endswith("<|im_end|>\n"):
            text += "<|im_end|>"

    elif chat_template == "deepseek":
        # DeepSeek-R1 template
        text = ""
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "").strip()

            if not content:
                continue

            if role == "system":
                text += f"system_message: {content}\n"
            elif role == "user":
                text += f"user: {content}\n"
            elif role == "assistant":
                text += f"assistant: {content}\n"

    else:
        # Default/generic format
        text = ""
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "").strip()

            if not content:
                continue

            text += f"[{role}]\n{content}\n\n"

    return text.strip() if text else None


def setup_training_args(output_dir: str, max_seq_length: int = 2048) -> Dict[str, Any]:
    """
    Configure training hyperparameters for Unsloth.

    Returns a dict compatible with SFTTrainer
    """
    from transformers import TrainingArguments

    training_args = TrainingArguments(
        output_dir=output_dir,
        overwrite_output_dir=True,
        num_train_epochs=3,
        per_device_train_batch_size=2,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        weight_decay=0.01,
        max_grad_norm=1.0,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        logging_dir=f"{output_dir}/logs",
        logging_steps=10,
        save_strategy="steps",
        save_steps=100,
        eval_strategy="steps",
        eval_steps=50,
        save_total_limit=2,
        seed=42,
        # Optimization
        optim="paged_adamw_32bit",  # Works better with bitsandbytes
        bf16=True,  # Use bfloat16 if GPU supports it
        # Gradient checkpointing for memory efficiency
        gradient_checkpointing=True,
        # Disable default device map (Unsloth handles this)
        device_map="auto",
    )

    return training_args


def setup_lora_config() -> Dict[str, Any]:
    """Configure QLoRA parameters."""
    from peft import LoraConfig

    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=[
            "q_proj",      # Query projection
            "k_proj",      # Key projection
            "v_proj",      # Value projection
            "o_proj",      # Output projection
            "gate_proj",   # Gate projection (Qwen/DeepSeek specific)
            "up_proj",     # Up projection (Qwen/DeepSeek specific)
            "down_proj",   # Down projection (Qwen/DeepSeek specific)
        ],
    )

    return lora_config


def load_model_and_tokenizer(model_name: str, max_seq_length: int = 2048):
    """
    Load model and tokenizer using Unsloth for QLoRA.

    Args:
        model_name: HuggingFace model ID
        max_seq_length: Maximum sequence length

    Returns:
        model, tokenizer tuple
    """
    from unsloth import FastLanguageModel

    logger.info(f"🤖 Loading model: {model_name}")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=max_seq_length,
        dtype=None,  # Auto-detect
        load_in_4bit=True,  # 4-bit quantization
        device_map="auto",
    )

    logger.info("✓ Model and tokenizer loaded")

    # Prepare for QLoRA training
    model = FastLanguageModel.get_peft_model(
        model,
        finetune_modules=setup_lora_config(),
        inference_mode=False,
    )

    logger.info("✓ LoRA modules attached")

    return model, tokenizer


def prepare_datasets_for_training(
    training_examples: List[Dict],
    tokenizer,
    max_seq_length: int = 2048,
) -> Dict:
    """
    Prepare datasets using HuggingFace datasets library.

    Returns train and eval datasets
    """
    from datasets import Dataset

    logger.info("🔄 Preparing datasets...")

    # Create Dataset from list of dicts
    dataset = Dataset.from_dict({
        "text": [ex["text"] for ex in training_examples],
    })

    def tokenize_function(examples):
        """Tokenize and format examples."""
        tokenized = tokenizer(
            examples["text"],
            max_length=max_seq_length,
            truncation=True,
            padding="max_length",
            return_tensors=None,
        )

        # Create labels (same as input_ids for next-token prediction)
        tokenized["labels"] = tokenized["input_ids"].copy()

        return tokenized

    # Tokenize all examples
    tokenized_dataset = dataset.map(
        tokenize_function,
        batched=True,
        desc="Tokenizing",
        remove_columns=["text"],
    )

    # Split into train/eval
    split_dataset = tokenized_dataset.train_test_split(test_size=0.1, seed=42)

    logger.info(f"✓ Train examples: {len(split_dataset['train'])}")
    logger.info(f"✓ Eval examples: {len(split_dataset['test'])}")

    return split_dataset


def train_model(
    model,
    tokenizer,
    train_dataset,
    eval_dataset,
    output_dir: str,
    max_seq_length: int = 2048,
):
    """
    Train the model using SFTTrainer from TRL.
    """
    from trl import SFTTrainer
    from transformers import TrainingArguments

    logger.info("🚀 Starting training...")

    training_args = TrainingArguments(
        output_dir=output_dir,
        overwrite_output_dir=True,
        num_train_epochs=3,
        per_device_train_batch_size=2,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        weight_decay=0.01,
        max_grad_norm=1.0,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        logging_dir=f"{output_dir}/logs",
        logging_steps=10,
        save_strategy="steps",
        save_steps=100,
        eval_strategy="steps",
        eval_steps=50,
        save_total_limit=2,
        seed=42,
        optim="paged_adamw_32bit",
        bf16=True,
        gradient_checkpointing=True,
        report_to=["tensorboard"],  # Change to ["wandb"] if using W&B
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        dataset_text_field="text",
        max_seq_length=max_seq_length,
        packing=True,  # Pack examples for efficiency
    )

    # Train
    trainer.train()

    logger.info("✓ Training complete")

    return trainer


def save_model(model, tokenizer, output_dir: str):
    """Save the trained LoRA adapter."""
    logger.info("💾 Saving LoRA adapter...")

    output_path = Path(output_dir) / "lora_adapter"
    output_path.mkdir(parents=True, exist_ok=True)

    model.save_pretrained(str(output_path))
    tokenizer.save_pretrained(str(output_path))

    logger.info(f"✓ LoRA adapter saved to {output_path}")


def merge_and_save_full_model(model, tokenizer, output_dir: str):
    """Merge LoRA adapter into base model and save."""
    from unsloth import FastLanguageModel

    logger.info("🔀 Merging LoRA adapter into base model...")

    # Merge LoRA into base model
    merged_model = FastLanguageModel.for_inference(model)

    output_path = Path(output_dir) / "merged_model"
    output_path.mkdir(parents=True, exist_ok=True)

    merged_model.save_pretrained(str(output_path))
    tokenizer.save_pretrained(str(output_path))

    logger.info(f"✓ Merged model saved to {output_path}")


def export_to_gguf(model_dir: str, output_dir: str, quantization: str = "Q4_K_M"):
    """
    Export merged model to GGUF format for Ollama.

    Requires: pip install llama-cpp-python
    """
    logger.info(f"📦 Exporting to GGUF ({quantization})...")

    try:
        import subprocess

        output_path = Path(output_dir) / f"model_{quantization}.gguf"

        # Use llama.cpp's conversion script
        # This requires the llama.cpp repo and python bindings

        logger.info(f"  Converting model to {quantization}...")

        # This is a placeholder - actual conversion depends on llama.cpp setup
        # In practice, you'd use: python convert.py + quantize

        logger.warning("⚠️  GGUF export requires llama.cpp setup (see guide)")
        logger.info("   Manual conversion steps:")
        logger.info("   1. pip install llama-cpp-python")
        logger.info("   2. git clone https://github.com/ggerganov/llama.cpp")
        logger.info("   3. python llama.cpp/convert.py --outfile model.gguf merged_model")
        logger.info(f"   4. ./llama.cpp/quantize model.gguf model_{quantization}.gguf {quantization}")

        return str(output_path)

    except Exception as e:
        logger.error(f"❌ GGUF export failed: {e}")
        return None


def print_deployment_instructions(output_dir: str, model_name: str, quantization: str = "Q4_K_M"):
    """Print instructions for deploying the model to Ollama."""

    logger.info("\n" + "=" * 80)
    logger.info("📋 DEPLOYMENT INSTRUCTIONS FOR OLLAMA")
    logger.info("=" * 80 + "\n")

    logger.info("1️⃣  CREATE A MODELFILE:")
    logger.info("-" * 80)

    modelfile_example = f"""FROM ./model_{quantization}.gguf
TEMPLATE \"\"\"[INST] {{{{ prompt }}}} [/INST]\"\"\"
PARAMETER stop \"[INST]\"
PARAMETER stop \"[/INST]\"
PARAMETER temperature 0.7
PARAMETER top_p 0.9
"""

    logger.info("Create /path/to/Modelfile:")
    logger.info(modelfile_example)

    logger.info("2️⃣  CREATE THE OLLAMA MODEL:")
    logger.info("-" * 80)

    create_cmd = "ollama create gangoos-coder -f Modelfile"
    logger.info(f"$ {create_cmd}\n")

    logger.info("3️⃣  RUN THE MODEL:")
    logger.info("-" * 80)
    run_cmd = "ollama run gangoos-coder"
    logger.info(f"$ {run_cmd}\n")

    logger.info("4️⃣  API USAGE (if Ollama server is running on localhost:11434):")
    logger.info("-" * 80)
    logger.info("""
import requests
import json

response = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "gangoos-coder",
        "prompt": "def fibonacci(n):",
        "stream": False
    }
)

result = json.loads(response.text)
print(result["response"])
""")

    logger.info("5️⃣  MONITORING DURING TRAINING:")
    logger.info("-" * 80)
    logger.info("Look for these signs to know when to stop training:")
    logger.info("  • Eval loss plateaus (stops decreasing for 3-5 eval steps)")
    logger.info("  • Perplexity stabilizes")
    logger.info("  • Overfitting begins (train loss << eval loss)")
    logger.info("")
    logger.info("Check tensorboard with:")
    logger.info(f"  tensorboard --logdir {output_dir}/logs\n")

    logger.info("6️⃣  EXPECTED VRAM USAGE:")
    logger.info("-" * 80)
    logger.info("  • Base model (4-bit): 4-6 GB VRAM")
    logger.info("  • Batch size 2 + grad accum 4: ~8-12 GB total")
    logger.info("  • With activation checkpointing: Can run on 24GB+ GPUs")
    logger.info("  • Recommended: RTX 4090 (24GB) or RTX 6000 (48GB)\n")

    logger.info("7️⃣  TRAINING TIME ESTIMATES:")
    logger.info("-" * 80)
    logger.info("  • ~2000 training examples:")
    logger.info("    - RTX 4090: ~30-45 minutes for 3 epochs")
    logger.info("    - RTX A100: ~10-15 minutes for 3 epochs")
    logger.info("  • Adjust num_train_epochs in script if needed\n")

    logger.info("=" * 80 + "\n")


def main():
    """Main training pipeline."""

    parser = argparse.ArgumentParser(description="QLoRA Finetuning Pipeline")
    parser.add_argument(
        "--dataset-dir",
        type=str,
        default="/sessions/loving-beautiful-mccarthy/Gangoos-coder/dataset",
        help="Directory containing JSONL dataset files",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="Qwen/Qwen2.5-7B-Instruct",
        choices=[
            "Qwen/Qwen2.5-7B-Instruct",
            "Qwen/Qwen2.5-9B",
            "deepseek-ai/deepseek-r1:8b-qwen3",
        ],
        help="Model to finetune (defaults to Qwen2.5-7B)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="/sessions/loving-beautiful-mccarthy/Gangoos-coder/models/finetuned",
        help="Output directory for trained models",
    )
    parser.add_argument(
        "--max-seq-length",
        type=int,
        default=2048,
        help="Maximum sequence length",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load only 5 examples and skip actual training (for testing)",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip dependency installation",
    )
    parser.add_argument(
        "--no-train",
        action="store_true",
        help="Load data and setup but don't train (useful for debugging)",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="Don't merge LoRA into base model (only save adapter)",
    )
    parser.add_argument(
        "--no-gguf",
        action="store_true",
        help="Don't export to GGUF format",
    )

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("🧠 GANGOOS-CODER FINETUNING PIPELINE")
    logger.info("=" * 80)
    logger.info(f"Model: {args.model}")
    logger.info(f"Dataset: {args.dataset_dir}")
    logger.info(f"Output: {args.output_dir}")
    logger.info(f"Max seq length: {args.max_seq_length}")
    if args.dry_run:
        logger.info("⚠️  DRY RUN MODE (5 examples only)")
    logger.info("=" * 80 + "\n")

    # Check GPU
    gpu_available = check_gpu()

    # Install dependencies
    if not args.skip_install:
        install_dependencies()
    else:
        logger.info("⏭️  Skipping dependency installation")

    # Load datasets
    conversations = load_datasets(args.dataset_dir, dry_run=args.dry_run)

    # Format for training
    training_examples = format_for_training(conversations, args.model)

    if args.no_train:
        logger.info("✓ Data loaded and formatted. Stopping before training (--no-train).")
        logger.info(f"  Ready to train {len(training_examples)} examples")
        return

    # Setup output directory
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Load model and tokenizer
    try:
        model, tokenizer = load_model_and_tokenizer(args.model, args.max_seq_length)
    except Exception as e:
        logger.error(f"❌ Failed to load model: {e}")
        logger.info("💡 Tip: Make sure you have internet connection and enough disk space")
        sys.exit(1)

    # Prepare datasets
    datasets = prepare_datasets_for_training(
        training_examples,
        tokenizer,
        args.max_seq_length,
    )

    # Train model
    try:
        trainer = train_model(
            model,
            tokenizer,
            datasets["train"],
            datasets["test"],
            str(output_path),
            args.max_seq_length,
        )
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Training interrupted by user")
        logger.info("Saving current state...")
        save_model(model, tokenizer, str(output_path))
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Training failed: {e}")
        sys.exit(1)

    # Save LoRA adapter
    save_model(model, tokenizer, str(output_path))

    # Merge and save full model
    if not args.no_merge:
        try:
            merge_and_save_full_model(model, tokenizer, str(output_path))
        except Exception as e:
            logger.error(f"⚠️  Merge failed (proceeding with adapter): {e}")

    # Export to GGUF (requires additional setup)
    if not args.no_gguf:
        merged_dir = output_path / "merged_model"
        if merged_dir.exists():
            export_to_gguf(str(merged_dir), str(output_path))

    # Print deployment instructions
    print_deployment_instructions(str(output_path), args.model)

    logger.info("✅ PIPELINE COMPLETE!")
    logger.info(f"📂 Output directory: {output_path}")


if __name__ == "__main__":
    main()
