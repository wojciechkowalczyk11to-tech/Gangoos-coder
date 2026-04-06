#!/bin/bash
# Quick-start script for Gangoos-Coder finetuning on RunPod

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "================================================================================"
echo "🚀 GANGOOS-CODER FINETUNING QUICK START"
echo "================================================================================"
echo ""

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.8+"
    exit 1
fi

echo "✓ Python found: $(python3 --version)"
echo ""

# Parse arguments
DRY_RUN=false
SKIP_INSTALL=false
MODEL="Qwen/Qwen2.5-7B-Instruct"
NO_MERGE=true

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --full)
            DRY_RUN=false
            NO_MERGE=false
            shift
            ;;
        --model)
            MODEL="$2"
            shift 2
            ;;
        --skip-install)
            SKIP_INSTALL=true
            shift
            ;;
        --help)
            echo "Usage: ./quick_start.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dry-run         Run with 5 examples only (default)"
            echo "  --full            Run full training with GGUF export"
            echo "  --model MODEL     Choose model:"
            echo "                      - Qwen/Qwen2.5-7B-Instruct (default)"
            echo "                      - Qwen/Qwen2.5-3B"
            echo "                      - deepseek-ai/deepseek-r1"
            echo "  --skip-install    Skip dependency installation"
            echo "  --help            Show this help message"
            echo ""
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check dataset files
echo "📂 Checking dataset files..."
if [ ! -f "$SCRIPT_DIR/execution_traces.jsonl" ]; then
    echo "⚠️  Warning: execution_traces.jsonl not found"
fi
if [ ! -f "$SCRIPT_DIR/execution_traces_v2.jsonl" ]; then
    echo "⚠️  Warning: execution_traces_v2.jsonl not found"
fi
echo ""

# Prepare command
CMD="python3 $SCRIPT_DIR/finetune_pipeline.py"
CMD="$CMD --model '$MODEL'"
CMD="$CMD --dataset-dir '$SCRIPT_DIR'"
CMD="$CMD --output-dir '$PROJECT_DIR/models/finetuned'"

if [ "$DRY_RUN" = true ]; then
    CMD="$CMD --dry-run --no-merge --no-gguf"
    echo "🧪 Running DRY RUN (5 examples, ~10 minutes)"
else
    echo "🎯 Running FULL TRAINING (3 epochs, ~1 hour)"
fi

if [ "$SKIP_INSTALL" = true ]; then
    CMD="$CMD --skip-install"
    echo "⏭️  Skipping dependency installation"
fi

echo "📊 Model: $MODEL"
echo "📍 Output: $PROJECT_DIR/models/finetuned"
echo ""
echo "Starting in 3 seconds (Ctrl+C to cancel)..."
sleep 3
echo ""

# Run the pipeline
eval $CMD

echo ""
echo "================================================================================"
echo "✅ COMPLETE!"
echo "================================================================================"
echo ""
if [ "$DRY_RUN" = true ]; then
    echo "Dry run successful! To run full training:"
    echo "  ./quick_start.sh --full"
else
    echo "Training complete! To deploy to Ollama:"
    echo "  1. See FINETUNING_GUIDE.md for GGUF conversion"
    echo "  2. Create a Modelfile"
    echo "  3. Run: ollama create gangoos-coder -f Modelfile"
fi
echo ""
