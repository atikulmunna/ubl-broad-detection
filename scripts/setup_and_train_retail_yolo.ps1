param(
    [string]$EnvName = "yolo_inference",
    [string]$DatasetRoot = "dataset\SOS Merged -OneClass-COCO Format",
    [string]$Model = "yolo11n.pt",
    [int]$Epochs = 50,
    [int]$ImageSize = 960,
    [int]$Batch = 4,
    [string]$Device = "cuda",
    [string]$SummaryFile = "outputs\yolo_train\summary.json"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    throw "Conda is not available in this PowerShell session. Open an Anaconda-enabled shell and retry."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Step "Creating or refreshing conda environment: $EnvName"
conda create -n $EnvName python=3.10 -y

Write-Step "Installing CUDA-enabled PyTorch"
conda run -n $EnvName python -m pip install --upgrade pip
conda run -n $EnvName python -m pip install --upgrade --index-url https://download.pytorch.org/whl/cu128 torch torchvision torchaudio

Write-Step "Installing repo dependencies"
conda run -n $EnvName python -m pip install -r requirements.txt
conda run -n $EnvName python -m pip install transformers accelerate

Write-Step "Checking CUDA visibility"
conda run -n $EnvName python -c "import torch; print('torch:', torch.__version__); print('cuda:', torch.cuda.is_available()); print('gpu:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"

Write-Step "Preparing YOLO labels and dataset yaml"
conda run -n $EnvName python scripts\prepare_retail_yolo_dataset.py --dataset-root $DatasetRoot

Write-Step "Starting one-class retail detector training"
conda run -n $EnvName python scripts\train_retail_yolo.py --dataset-root $DatasetRoot --model $Model --device $Device --epochs $Epochs --imgsz $ImageSize --batch $Batch --summary-file $SummaryFile

Write-Step "Training command finished"
Write-Host "Summary file: $SummaryFile" -ForegroundColor Green
