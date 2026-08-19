# Deployment script for Windows PowerShell
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Deploying Multi-Tenant Serverless Doc Pipeline   " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 1. Build Lambda packages
Write-Host "`n[*] Building Lambda archives..." -ForegroundColor Yellow
python .\scripts\build.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] Build failed!" -ForegroundColor Red
    exit 1
}

# 2. Terraform Deploy
Set-Location terraform
Write-Host "`n[*] Initializing Terraform..." -ForegroundColor Yellow
terraform init

Write-Host "`n[*] Running Terraform Apply..." -ForegroundColor Yellow
terraform apply -auto-approve

Write-Host "`n[+] Deployment Complete!" -ForegroundColor Green
Set-Location ..
