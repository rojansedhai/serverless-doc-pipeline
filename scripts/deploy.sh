#!/usr/bin/env bash
set -e

echo "=================================================="
echo "  Deploying Multi-Tenant Serverless Doc Pipeline   "
echo "=================================================="

# 1. Build Lambda packages
echo -e "\n[*] Building Lambda archives..."
python3 scripts/build.py

# 2. Terraform Deploy
cd terraform
echo -e "\n[*] Initializing Terraform..."
terraform init

echo -e "\n[*] Running Terraform Apply..."
terraform apply -auto-approve

echo -e "\n[+] Deployment Complete!"
cd ..
