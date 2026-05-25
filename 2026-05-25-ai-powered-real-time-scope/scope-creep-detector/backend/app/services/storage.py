import os
import shutil
from pathlib import Path
from typing import Optional
from fastapi import UploadFile

from app.config import get_settings

settings = get_settings()


def get_upload_path(filename: str, subfolder: str = "") -> Path:
    """Get local upload path, creating directory if needed."""
    base = Path(settings.upload_dir)
    if subfolder:
        base = base / subfolder
    base.mkdir(parents=True, exist_ok=True)
    return base / filename


async def save_upload_file(upload_file: UploadFile, destination: Path) -> str:
    """Save an uploaded file to disk and return the path."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination, "wb") as f:
        content = await upload_file.read()
        f.write(content)
    return str(destination)


def read_file_bytes(file_path: str) -> bytes:
    """Read file bytes from local storage."""
    with open(file_path, "rb") as f:
        return f.read()


def save_pdf_bytes(content: bytes, filename: str) -> str:
    """Save PDF bytes to local storage."""
    path = get_upload_path(filename, subfolder="change_orders")
    with open(path, "wb") as f:
        f.write(content)
    return str(path)