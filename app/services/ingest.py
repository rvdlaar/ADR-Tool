"""
Document ingestion service with secure file handling.
Persists metadata to SQLite, embeds documents in ChromaDB.
"""
import os
import uuid
import aiofiles
from pathlib import Path
from typing import Optional, List
from datetime import datetime
import hashlib

from app.db.document_store import (
    create_document as db_create,
    get_document as db_get,
    list_documents as db_list,
    delete_document as db_delete,
)

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".doc", ".docx", ".json", ".yaml", ".yml", ".xml", ".csv"}
MAX_FILE_SIZE = 10 * 1024 * 1024
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/tmp/adr-uploads"))

# Text-extractable extensions (for RAG embedding)
TEXT_EXTENSIONS = {".txt", ".md", ".json", ".yaml", ".yml", ".xml", ".csv"}


class DocumentIngestionError(Exception):
    pass

class PathTraversalError(DocumentIngestionError):
    pass

class FileValidationError(DocumentIngestionError):
    pass


def _validate_path(base_dir: Path, target_path: Path) -> Path:
    base_dir = base_dir.resolve()
    target_path = target_path.resolve()
    try:
        target_path.relative_to(base_dir)
    except ValueError:
        raise PathTraversalError(
            f"Path traversal detected: '{target_path}' is outside '{base_dir}'"
        )
    return target_path


def _sanitize_filename(filename: str) -> str:
    filename = filename.replace("\x00", "")
    filename = os.path.basename(filename)
    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_")
    filename = "".join(c if c in allowed_chars else "_" for c in filename)
    if not filename or filename.startswith("."):
        filename = f"document_{uuid.uuid4().hex[:8]}"
    return filename


def _validate_file_extension(filename: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError(
            f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )


async def _ensure_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def _embed_document(doc_id: str, content: str, filename: str):
    """Best-effort embed document content into ChromaDB."""
    try:
        from app.services.embeddings import get_embedding_service
        from app.services.vector_store import get_vector_store, COLLECTION_CONTEXT
        vs = get_vector_store()
        if not vs:
            return
        text = f"{filename}\n{content[:5000]}"
        embedding = get_embedding_service().embed(text)
        vs.upsert(COLLECTION_CONTEXT, doc_id, embedding, text, {"filename": filename})
    except Exception:
        pass  # Non-blocking


async def ingest_file_api(
    file_content: bytes, filename: str,
    content_type: Optional[str] = None, metadata: Optional[dict] = None
) -> dict:
    if len(file_content) > MAX_FILE_SIZE:
        raise FileValidationError(f"File too large. Max: {MAX_FILE_SIZE / (1024*1024)}MB")

    filename = _sanitize_filename(filename)
    _validate_file_extension(filename)

    doc_id = str(uuid.uuid4())[:12]
    date_dir = datetime.utcnow().strftime("%Y-%m-%d")
    upload_dir = await _ensure_upload_dir()

    target_dir = upload_dir / "api" / date_dir
    target_dir = _validate_path(upload_dir, target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / filename
    target_path = _validate_path(target_dir, target_path)
    if target_path.exists():
        stem = target_path.stem
        suffix = target_path.suffix
        target_path = target_dir / f"{stem}_{doc_id[:6]}{suffix}"

    async with aiofiles.open(target_path, "wb") as f:
        await f.write(file_content)

    file_hash = hashlib.sha256(file_content).hexdigest()

    document = db_create(
        doc_id=doc_id, filename=target_path.name,
        original_filename=filename, file_path=str(target_path),
        file_size=len(file_content), content_type=content_type,
        file_hash=file_hash, metadata=metadata, source="api"
    )

    # Embed text-extractable files
    ext = Path(filename).suffix.lower()
    if ext in TEXT_EXTENSIONS:
        try:
            text_content = file_content.decode("utf-8", errors="replace")
            _embed_document(doc_id, text_content, filename)
        except Exception:
            pass

    return document


async def ingest_file_path(
    file_path: str, metadata: Optional[dict] = None
) -> dict:
    input_path = Path(file_path)
    if ".." in input_path.parts or input_path.is_absolute():
        raise PathTraversalError("Absolute paths and .. sequences not allowed")

    filename = _sanitize_filename(input_path.name)
    _validate_file_extension(filename)

    allowed_bases = [
        Path("/home/node/.openclaw/workspace-henry/adr-tool-api/uploads"),
        Path("/tmp/adr-uploads/import"),
    ]

    resolved_path = None
    for base in allowed_bases:
        try:
            if str(input_path).startswith(str(base)):
                resolved_path = base / input_path.relative_to(base)
                break
        except ValueError:
            continue

    if resolved_path is None:
        base = allowed_bases[0]
        resolved_path = (base / filename).resolve()
        resolved_path = _validate_path(base, resolved_path)

    if not resolved_path.exists():
        raise FileValidationError(f"File not found: {resolved_path}")

    file_size = resolved_path.stat().st_size
    if file_size > MAX_FILE_SIZE:
        raise FileValidationError(f"File too large. Max: {MAX_FILE_SIZE / (1024*1024)}MB")

    async with aiofiles.open(resolved_path, "rb") as f:
        file_content = await f.read()

    doc_id = str(uuid.uuid4())[:12]
    date_dir = datetime.utcnow().strftime("%Y-%m-%d")
    upload_dir = await _ensure_upload_dir()

    target_dir = upload_dir / "fil" / date_dir
    target_dir = _validate_path(upload_dir, target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / filename
    target_path = _validate_path(target_dir, target_path)
    if target_path.exists():
        stem = target_path.stem
        suffix = target_path.suffix
        target_path = target_dir / f"{stem}_{doc_id[:6]}{suffix}"

    async with aiofiles.open(target_path, "wb") as f:
        await f.write(file_content)

    file_hash = hashlib.sha256(file_content).hexdigest()

    document = db_create(
        doc_id=doc_id, filename=target_path.name,
        original_filename=filename, file_path=str(target_path),
        file_size=file_size, content_type=None,
        file_hash=file_hash, metadata=metadata, source="file_path"
    )

    ext = Path(filename).suffix.lower()
    if ext in TEXT_EXTENSIONS:
        try:
            text_content = file_content.decode("utf-8", errors="replace")
            _embed_document(doc_id, text_content, filename)
        except Exception:
            pass

    return document


async def get_document(doc_id: str) -> Optional[dict]:
    return db_get(doc_id)


async def list_documents(limit: int = 50, offset: int = 0) -> List[dict]:
    docs, _ = db_list(limit=limit, offset=offset)
    return docs


async def delete_document(doc_id: str) -> bool:
    doc = db_get(doc_id)
    if not doc:
        return False
    try:
        Path(doc["file_path"]).unlink(missing_ok=True)
    except Exception:
        pass
    try:
        from app.services.vector_store import get_vector_store, COLLECTION_CONTEXT
        vs = get_vector_store()
        if vs:
            vs.delete(COLLECTION_CONTEXT, doc_id)
    except Exception:
        pass
    return db_delete(doc_id)
