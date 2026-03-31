#!/bin/bash
# Usage: ./upload_models.sh MODEL1.pt MODEL2.pt ...

set -e

# Default values
MODELS_DIR="models"
AWS_REGION="${AWS_DEFAULT_REGION:-ap-southeast-1}"

echo "=========================================="
echo "  UBL AI Models Selective Upload Script"
echo "=========================================="
echo ""

# Interactive Selection
echo "Select target environment:"
echo "  1) Development (default)"
echo "  2) Production"
echo ""
read -p "Enter selection [1]: " env_choice

case $env_choice in
    2)
        ENVIRONMENT="production"
        S3_BUCKET="u-lens-production-ai-models"
        ENV_DISPLAY="PRODUCTION"
        ;;
    *)
        ENVIRONMENT="development"
        S3_BUCKET="u-lens-development-ai-models"
        ENV_DISPLAY="DEVELOPMENT"
        ;;
esac

echo ""
echo "Target Environment: $ENV_DISPLAY"
echo "S3 Bucket: s3://$S3_BUCKET/models/"
echo ""

# Check if arguments are provided
if [ $# -eq 0 ]; then
    echo "ERROR: No model files specified."
    echo ""
    echo "Usage: $0 MODEL1.pt MODEL2.pt [MODEL3.pt ...]"
    echo ""
    echo "Example:"
    echo "  $0 DA_YOLO11X.pt QPDS.pt"
    echo ""
    echo "Available models in $MODELS_DIR:"
    if [ -d "$MODELS_DIR" ]; then
        for model in "$MODELS_DIR"/*.pt; do
            if [ -f "$model" ]; then
                filename=$(basename "$model")
                size=$(du -h "$model" | cut -f1)
                echo "  - $filename ($size)"
            fi
        done
    fi
    exit 1
fi

if [ ! -d "$MODELS_DIR" ]; then
    echo "ERROR: Models directory not found: $MODELS_DIR"
    exit 1
fi

MODELS_TO_UPLOAD=()

echo "Validating specified models..."
for model_name in "$@"; do
    model_path="$MODELS_DIR/$model_name"
    
    if [ ! -f "$model_path" ]; then
        echo "ERROR: Model file not found: $model_name"
        echo "Path checked: $model_path"
        exit 1
    fi
    
    MODELS_TO_UPLOAD+=("$model_path")
done

echo ""
echo "Models to upload to $ENV_DISPLAY:"
for model_path in "${MODELS_TO_UPLOAD[@]}"; do
    filename=$(basename "$model_path")
    size=$(du -h "$model_path" | cut -f1)
    echo "  - $filename ($size)"
done

echo ""
read -p "Proceed with upload? (y/n): " confirm
if [ "$confirm" != "y" ]; then
    echo "Upload cancelled."
    exit 0
fi

echo ""
echo "Uploading models..."

for model_path in "${MODELS_TO_UPLOAD[@]}"; do
    filename=$(basename "$model_path")
    echo "Uploading $filename..."
    aws s3 cp "$model_path" "s3://$S3_BUCKET/models/$filename" \
        --region "$AWS_REGION" \
        --metadata "uploaded=$(date -u +%Y-%m-%dT%H:%M:%SZ),source=local,environment=$ENVIRONMENT"
    echo "$filename uploaded successfully"
done

echo ""
echo "=========================================="
echo "  Upload Complete!"
echo "=========================================="
echo ""
echo "Uploaded ${#MODELS_TO_UPLOAD[@]} model(s) to: s3://$S3_BUCKET/models/"
echo ""
echo "To verify, run:"
echo "  aws s3 ls s3://$S3_BUCKET/models/"
