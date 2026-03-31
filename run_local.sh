#!/bin/bash
# Run AI Server locally (outside Docker)
# Usage: ./run_local.sh [--debug] [--cpu]

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Parse args
DEBUG_MODE=false
FORCE_CPU=false
for arg in "$@"; do
    case $arg in
        --debug)
            DEBUG_MODE=true
            shift
            ;;
        --cpu)
            FORCE_CPU=true
            shift
            ;;
    esac
done

echo "================================================"
echo "UBL AI Server - Local Run"
if [[ "$DEBUG_MODE" == "true" ]]; then
    echo -e "${YELLOW}DEBUG MODE ENABLED${NC}"
fi
if [[ "$FORCE_CPU" == "true" ]]; then
    echo -e "${YELLOW}CPU MODE (GPU disabled)${NC}"
fi
echo "================================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python3 not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python3 found${NC}"

# Check if LocalStack is running
echo ""
echo "Checking LocalStack..."
if curl -s http://localhost:4566/_localstack/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ LocalStack is running${NC}"
else
    echo -e "${YELLOW}⚠ LocalStack not detected at localhost:4566${NC}"
    echo ""
    echo "Start LocalStack first:"
    echo "  cd simulation && docker-compose up localstack -d"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check GPU
echo ""
if command -v nvidia-smi &> /dev/null; then
    echo -e "${GREEN}✓ NVIDIA GPU detected${NC}"
    nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader
else
    echo -e "${YELLOW}⚠ No GPU detected, using CPU${NC}"
fi

# Check models
echo ""
echo "Checking models..."
MODELS_OK=true
for model in DA_YOLO11X.pt EXCLUSIVITY.pt QPDS.pt Shelftalker.pt SACHET_YOLO11X.pt POSM_YOLO11X.pt; do
    if [[ -f "models/$model" ]]; then
        echo -e "${GREEN}✓ $model${NC}"
    else
        echo -e "${RED}✗ $model${NC}"
        MODELS_OK=false
    fi
done

if [[ "$MODELS_OK" == "false" ]]; then
    echo -e "${RED}Missing models! Place them in models/${NC}"
    exit 1
fi

# Export environment variables for LocalStack
echo ""
echo "Setting environment..."
export USE_LOCALSTACK=true
export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_DEFAULT_REGION=ap-southeast-1

# S3 Buckets
export S3_BUCKET=u-lens-production-audit-images
export S3_MODELS_BUCKET=u-lens-production-ai-models
export S3_RESULTS_BUCKET=u-lens-production-ai-results

# SQS Queue URLs (LocalStack format)
export SQS_IMAGE_QUEUE_URL=http://localhost:4566/000000000000/ubl-image-processing-queue
export SQS_RESULTS_QUEUE_URL=http://localhost:4566/000000000000/ubl-ai-results-queue

# Worker config (single worker for easier debugging)
export NUM_INFERENCE_WORKERS=${NUM_INFERENCE_WORKERS:-1}
export SQS_POLL_INTERVAL=0.5
export SQS_EMPTY_WAIT=2.0

# Debug mode settings
if [[ "$DEBUG_MODE" == "true" ]]; then
    export DEBUG_MODE=true
    export DEBUG_OUTPUT_DIR="${SCRIPT_DIR}/debug_output"
    mkdir -p "$DEBUG_OUTPUT_DIR"
    echo -e "${YELLOW}Debug output: $DEBUG_OUTPUT_DIR${NC}"
fi

# Force CPU mode (disable CUDA)
if [[ "$FORCE_CPU" == "true" ]]; then
    export CUDA_VISIBLE_DEVICES=""
fi

echo ""
echo "Environment:"
echo "  USE_LOCALSTACK=$USE_LOCALSTACK"
echo "  AWS_ENDPOINT_URL=$AWS_ENDPOINT_URL"
echo "  NUM_INFERENCE_WORKERS=$NUM_INFERENCE_WORKERS"
if [[ "$DEBUG_MODE" == "true" ]]; then
    echo "  DEBUG_MODE=$DEBUG_MODE"
    echo "  DEBUG_OUTPUT_DIR=$DEBUG_OUTPUT_DIR"
fi
echo ""

echo "================================================"
echo -e "${GREEN}Starting AI Server...${NC}"
echo "================================================"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Run the server
python3 main.py
