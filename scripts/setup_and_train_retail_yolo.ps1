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

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

function Get-TrainingArtifactPaths {
    param([string]$SummaryPath)

    if (-not $SummaryPath -or -not (Test-Path -LiteralPath $SummaryPath)) {
        return $null
    }

    $summary = Get-Content -LiteralPath $SummaryPath -Raw | ConvertFrom-Json
    $saveDir = $summary.training.save_dir
    if (-not $saveDir) {
        return $null
    }

    return [PSCustomObject]@{
        SaveDir = $saveDir
        BestPt  = Join-Path $saveDir "weights\best.pt"
        LastPt  = Join-Path $saveDir "weights\last.pt"
    }
}

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    throw "Conda is not available in this PowerShell session. Open an Anaconda-enabled shell and retry."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Step "Creating or refreshing conda environment: $EnvName"
Invoke-Checked -FailureMessage "Failed to create or refresh conda environment '$EnvName'." -Command {
    conda create -n $EnvName python=3.10 -y
}

Write-Step "Installing repo dependencies"
Invoke-Checked -FailureMessage "Failed to upgrade pip in conda environment '$EnvName'." -Command {
    conda run -n $EnvName python -m pip install --upgrade pip
}
Invoke-Checked -FailureMessage "Failed to install repo dependencies from requirements.txt." -Command {
    conda run -n $EnvName python -m pip install -r requirements.txt
}
Invoke-Checked -FailureMessage "Failed to install optional Hugging Face dependencies." -Command {
    conda run -n $EnvName python -m pip install transformers accelerate
}

Write-Step "Installing CUDA-enabled PyTorch"
Invoke-Checked -FailureMessage "Failed to install CUDA-enabled PyTorch wheels." -Command {
    conda run -n $EnvName python -m pip install --upgrade --index-url https://download.pytorch.org/whl/cu124 torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1
}

Write-Step "Checking CUDA visibility"
Invoke-Checked -FailureMessage "CUDA is not available in the '$EnvName' environment after installing GPU PyTorch. Stopping before training." -Command {
    conda run -n $EnvName python -c "import sys, torch; print('torch:', torch.__version__); print('torch cuda build:', torch.version.cuda); print('cuda available:', torch.cuda.is_available()); print('gpu count:', torch.cuda.device_count()); print('gpu:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none'); sys.exit(0 if torch.cuda.is_available() else 1)"
}

Write-Step "Preparing YOLO labels and dataset yaml"
Invoke-Checked -FailureMessage "Failed to prepare YOLO labels and dataset yaml." -Command {
    conda run -n $EnvName python scripts\prepare_retail_yolo_dataset.py --dataset-root $DatasetRoot
}

Write-Step "Starting one-class retail detector training"
Invoke-Checked -FailureMessage "YOLO training failed." -Command {
    conda run -n $EnvName python scripts\train_retail_yolo.py --dataset-root $DatasetRoot --model $Model --device $Device --epochs $Epochs --imgsz $ImageSize --batch $Batch --summary-file $SummaryFile
}

Write-Step "Training command finished"
Write-Host "Summary file: $SummaryFile" -ForegroundColor Green
$artifacts = Get-TrainingArtifactPaths -SummaryPath $SummaryFile
if ($artifacts) {
    Write-Host "Run directory: $($artifacts.SaveDir)" -ForegroundColor Green
    Write-Host "Best checkpoint: $($artifacts.BestPt)" -ForegroundColor Green
    Write-Host "Last checkpoint: $($artifacts.LastPt)" -ForegroundColor Green
}
