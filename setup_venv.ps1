if (!(Test-Path ".\.venv")) {
    Write-Host "Creating uv virtual environment..."
    uv venv --python=3.12
}

& .\.venv\Scripts\Activate.ps1

python -m ensurepip --upgrade
python -m pip install --upgrade pip

if (Test-Path ".\requirements.txt") {
    pip install -r requirements.txt
}

Write-Host "✅ uv 가상환경이 준비되었습니다!"
