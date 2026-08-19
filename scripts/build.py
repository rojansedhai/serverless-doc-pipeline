#!/usr/bin/env python3
"""
Build Script for Serverless Document Pipeline
Packages Lambda functions with shared modules into zip archives in terraform/.builds/
"""
import os
import shutil
import zipfile
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
TERRAFORM_DIR = ROOT_DIR / "terraform"
BUILDS_DIR = TERRAFORM_DIR / ".builds"


def create_zip(lambda_name: str, src_path: Path):
    zip_filename = BUILDS_DIR / f"{lambda_name}.zip"
    print(f"[*] Packaging {lambda_name} -> {zip_filename.relative_to(ROOT_DIR)}")

    with zipfile.ZipFile(zip_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
        # 1. Add Lambda handler
        handler_file = src_path / "handler.py"
        if handler_file.exists():
            zipf.write(handler_file, arcname="handler.py")
        else:
            print(f"[!] Warning: {handler_file} not found")

        # 2. Add shared modules
        shared_dir = SRC_DIR / "shared"
        if shared_dir.exists():
            for item in shared_dir.glob("*.py"):
                zipf.write(item, arcname=f"shared/{item.name}")

    print(f"[+] Successfully built {zip_filename.name} ({zip_filename.stat().st_size} bytes)")


def main():
    print("==================================================")
    print("  Building Lambda Packages for Terraform")
    print("==================================================")

    BUILDS_DIR.mkdir(parents=True, exist_ok=True)

    lambdas = [
        ("get_presigned_url", SRC_DIR / "get_presigned_url"),
        ("doc_processor", SRC_DIR / "doc_processor"),
        ("get_doc_status", SRC_DIR / "get_doc_status"),
    ]

    for name, path in lambdas:
        create_zip(name, path)

    print("\n[OK] All Lambda artifacts generated in terraform/.builds/")


if __name__ == "__main__":
    main()
