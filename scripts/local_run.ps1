$ErrorActionPreference = 'Stop'

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Criei .env a partir de .env.example. Edite DOOM_API_KEY e confirme LLM_PROVIDER=ollama." -ForegroundColor Yellow
}

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
