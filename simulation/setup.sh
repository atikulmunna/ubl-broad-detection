#!/bin/bash
# UBL Simulation Setup Script

set -e  # Exit on error

echo "================================================"
echo "UBL AI Server - Setup Script"
echo "================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running from simulation directory
if [[ ! -f "docker-compose.yml" ]]; then
    echo -e "${RED}Error: Please run this script from the simulation directory${NC}"
    exit 1
fi

echo "Step 1: Checking prerequisites..."
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker not found${NC}"
    echo "Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
else
    echo -e "${GREEN}✓ Docker installed${NC}"
fi

# Check Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}✗ Docker Compose not found${NC}"
    echo "Please install Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
else
    echo -e "${GREEN}✓ Docker Compose installed${NC}"
fi

# Check for GPU (optional)
if command -v nvidia-smi &> /dev/null; then
    echo -e "${GREEN}✓ NVIDIA GPU detected${NC}"
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
    
    # Check for NVIDIA Docker runtime
    if docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
        echo -e "${GREEN}✓ NVIDIA Container Toolkit configured${NC}"
        echo -e "${YELLOW}  You can enable GPU support in docker-compose.yml${NC}"
    else
        echo -e "${YELLOW}⚠ NVIDIA Container Toolkit not configured${NC}"
        echo "  Install with: sudo apt-get install nvidia-container-toolkit"
        echo "  Then restart Docker: sudo systemctl restart docker"
    fi
else
    echo -e "${YELLOW}⚠ No NVIDIA GPU detected (CPU mode will be used)${NC}"
fi

echo ""
echo "Step 2: Checking model files..."
echo ""

MODEL_DIR="../models"
REQUIRED_MODELS=(
    "DA_YOLO11X.pt"
    "EXCLUSIVITY.pt"
    "POSM_YOLO11X.pt"
    "QPDS.pt"
    "SACHET_YOLO11X.pt"
    "Shelftalker.pt"
)

MISSING_MODELS=()
for model in "${REQUIRED_MODELS[@]}"; do
    if [[ -f "$MODEL_DIR/$model" ]]; then
        echo -e "${GREEN}✓ $model${NC}"
    else
        echo -e "${RED}✗ $model${NC}"
        MISSING_MODELS+=("$model")
    fi
done

if [[ ${#MISSING_MODELS[@]} -gt 0 ]]; then
    echo ""
    echo -e "${RED}Error: Missing model files:${NC}"
    for model in "${MISSING_MODELS[@]}"; do
        echo "  - $model"
    done
    echo ""
    echo "Please place all model files in: $MODEL_DIR/"
    exit 1
fi

echo ""
echo "Step 3: Checking config files..."
echo ""

CONFIG_DIR="../config"
STANDARDS_DIR="../config/standards"

if [[ ! -d "$CONFIG_DIR" ]]; then
    echo -e "${RED}✗ config directory not found${NC}"
    echo "Please ensure config/ directory exists in the parent directory"
    exit 1
fi

if [[ -f "$CONFIG_DIR/config.yaml" ]]; then
    echo -e "${GREEN}✓ config.yaml${NC}"
else
    echo -e "${RED}✗ config.yaml${NC}"
    exit 1
fi

if [[ ! -d "$STANDARDS_DIR" ]]; then
    echo -e "${RED}✗ config/standards directory not found${NC}"
    exit 1
fi

REQUIRED_STANDARDS=(
    "qpds_standards.yaml"
    "sos_shelving_norm.yaml"
    "sachet_standards.yaml"
    "posm_standards.yaml"
)

MISSING_CONFIGS=()
for config in "${REQUIRED_STANDARDS[@]}"; do
    if [[ -f "$STANDARDS_DIR/$config" ]]; then
        echo -e "${GREEN}✓ standards/$config${NC}"
    else
        echo -e "${RED}✗ standards/$config${NC}"
        MISSING_CONFIGS+=("$config")
    fi
done

if [[ ${#MISSING_CONFIGS[@]} -gt 0 ]]; then
    echo ""
    echo -e "${RED}Error: Missing config files:${NC}"
    for config in "${MISSING_CONFIGS[@]}"; do
        echo "  - $config"
    done
    echo ""
    echo "Please ensure all config files are in: $STANDARDS_DIR/"
    exit 1
fi

echo ""
echo "Step 4: Checking utils directory..."
echo ""

if [[ -d "../utils" ]]; then
    echo -e "${GREEN}✓ utils directory exists${NC}"
    
    REQUIRED_UTILS=(
        "qpds_compliance.py"
        "sos_compliance.py"
        "sachet_compliance.py"
        "posm_compliance.py"
        "category_analysis.py"
    )
    
    MISSING_UTILS=()
    for util in "${REQUIRED_UTILS[@]}"; do
        if [[ -f "../utils/$util" ]]; then
            echo -e "${GREEN}  ✓ $util${NC}"
        else
            echo -e "${RED}  ✗ $util${NC}"
            MISSING_UTILS+=("$util")
        fi
    done
    
    if [[ ${#MISSING_UTILS[@]} -gt 0 ]]; then
        echo ""
        echo -e "${YELLOW}Warning: Missing utility files (some features may not work):${NC}"
        for util in "${MISSING_UTILS[@]}"; do
            echo "  - $util"
        done
    fi
else
    echo -e "${RED}✗ utils directory not found${NC}"
    echo "Please ensure utils/ directory exists in the parent directory"
    exit 1
fi

echo ""
echo "Step 5: Setting up environment..."
echo ""

if [[ ! -f ".env" ]]; then
    if [[ -f ".env.example" ]]; then
        cp .env.example .env
        echo -e "${GREEN}✓ Created .env from .env.example${NC}"
        echo -e "${YELLOW}  Please review and customize .env if needed${NC}"
    else
        echo -e "${YELLOW}⚠ No .env or .env.example found${NC}"
        echo "  Using default environment variables"
    fi
else
    echo -e "${GREEN}✓ .env file exists${NC}"
fi

echo ""
echo "================================================"
echo -e "${GREEN}Setup Complete!${NC}"
echo "================================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Start the services:"
echo "   docker-compose up --build"
echo ""
echo "2. In another terminal, test with the client:"
echo "   cd client"
echo "   python main.py"
echo ""
echo "3. View logs:"
echo "   docker logs -f ai-server"
echo "   docker logs -f backend-api"
echo ""
echo "4. Access the API:"
echo "   http://localhost:8000"
echo ""
echo "For GPU support:"
echo "   - Uncomment the GPU section in docker-compose.yml"
echo "   - Restart services"
echo ""
echo "================================================"
