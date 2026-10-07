"""Validate upload names before parsing and bound bytes read per file."""
import re
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from starlette.responses import JSONResponse

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES = 5
EVIDENCE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
                       ".mp4", ".mov", ".avi", ".mkv", ".mp3", ".wav", ".m4a", ".ogg",
                       ".pdf", ".doc", ".docx", ".txt", ".md"}


class UploadLimitMiddleware:
    """Bound the multipart body before Starlette spools it to memory/disk."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") not in {
                "/api/rag/upload", "/api/rag/upload-multiple", "/api/disputes/resolve-with-files"}:
            return await self.app(scope, receive, send)
        limit = MAX_FILE_BYTES * MAX_FILES + 64 * 1024
        headers = dict(scope.get("headers", []))
        try:
            too_large = int(headers.get(b"content-length", b"0")) > limit
        except ValueError:
            return await JSONResponse({"detail":"Invalid content length."}, status_code=400)(scope, receive, send)
        if too_large:
            return await JSONResponse({"detail":"Upload request is too large."}, status_code=413)(scope, receive, send)
        total = 0
        async def bounded_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > limit:
                raise HTTPException(413, "Upload request is too large.")
            return message
        return await self.app(scope, bounded_receive, send)


def validate_filename(filename: str | None, extensions: set[str]) -> str:
    if not filename or len(filename) > 200 or re.search(r'[\\/:%\x00-\x1f]', filename):
        raise HTTPException(400, "Invalid file name.")
    ext = Path(filename).suffix.lower()
    if ext not in extensions:
        raise HTTPException(400, "Unsupported file format.")
    return ext


def evidence_directory(root: Path, order_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", order_id):
        raise HTTPException(400, "Invalid order ID.")
    directory = root / order_id
    if not directory.resolve().is_relative_to(root.resolve()):
        raise HTTPException(400, "Invalid evidence directory.")
    return directory


def upload_path(root: Path, ext: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{uuid4().hex}{ext}"
    if not path.resolve().is_relative_to(root.resolve()):
        raise HTTPException(400, "Invalid upload path.")
    return path


async def read_upload(file: UploadFile) -> bytes:
    content = bytearray()
    while chunk := await file.read(64 * 1024):
        content.extend(chunk)
        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(413, "Each file must be at most 10 MB.")
    if not content:
        raise HTTPException(400, "Empty file.")
    return bytes(content)


def validate_count(files: list[UploadFile]) -> None:
    if len(files) > MAX_FILES:
        raise HTTPException(413, "Upload at most 5 files per request.")
