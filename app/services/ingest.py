"""
Document ingestion service with secure file handling.
Protects against path traversal attacks.
"""
import os
import uuid
import aiofiles
from pathlib import Path
from typing import Optional, List
from datetime import datetime
import hashlib

# Allowed file extensions for document uploads
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".doc", ".docx", ".json", ".yaml", ".yml", ".xml", ".csv"}

# Maximum file size (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024

# Base upload directory (configurable)
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/tmp/adr-uploads"))

# In-memory storage for ingested documents (replace with DB in production)
_documents_db: dict = {}


class DocumentIngestionError(Exception):
    """Custom exception for document ingestion errors"""
    pass


class PathTraversalError(DocumentIngestionError):
    """Exception raised when path traversal is detected"""
    pass


class FileValidationError(DocumentIngestionError):
    """Exception raised when file validation fails"""
    pass


def _validate_path(base_dir: Path, target_path: Path) -> Path:
    """
    Securely resolve a path and ensure it stays within the base directory.
    This prevents path traversal attacks (e.g., ../../etc/passwd).
    
    Args:
        base_dir: The allowed base directory
        target_path: The path to validate
        
    Returns:
        The resolved absolute path
        
    Raises:
        PathTraversalError: If the path attempts to escape base_dir
    """
    # Resolve both paths to absolute paths
    base_dir = base_dir.resolve()
    target_path = target_path.resolve()
    
    # Check if the resolved target path is within the base directory
    try:
        target_path.relative_to(base_dir)
    except ValueError:
        raise PathTraversalError(
            f"Path traversal detected: '{target_path}' is outside allowed directory '{base_dir}'"
        )
    
    return target_path


def _sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to remove potentially dangerous characters.
    
    Args:
        filename: The original filename
        
    Returns:
        Sanitized filename
    """
    # Remove null bytes and control characters
    filename = filename.replace("\x00", "")
    
    # Get just the basename (remove any directory components)
    filename = os.path.basename(filename)
    
    # Replace spaces and common special chars with underscores
    # Keep alphanumeric, dots, dashes, and underscores
    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_")
    filename = "".join(c if c in allowed_chars else "_" for c in filename)
    
    # Ensure we don't have an empty filename
    if not filename or filename.startswith("."):
        filename = f"document_{uuid.uuid4().hex[:8]}"
    
    return filename


def _validate_file_extension(filename: str) -> None:
    """
    Validate that the file has an allowed extension.
    
    Args:
        filename: The filename to validate
        
    Raises:
        FileValidationError: If the extension is not allowed
    """
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError(
            f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )


async def _ensure_upload_dir() -> Path:
    """Ensure the upload directory exists with proper permissions"""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


async def ingest_file_api(
    file_content: bytes,
    filename: str,
    content_type: Optional[str] = None,
    metadata: Optional[dict] = None
) -> dict:
    """
    Ingest a document via API (file content passed directly).
    
    Args:
        file_content: The raw file content
        filename: The original filename
        content_type: Optional content type
        metadata: Optional metadata dict
        
    Returns:
        Document metadata including ID and path
        
    Raises:
        PathTraversalError: If path traversal is detected
        FileValidationError: If file validation fails
    """
    # Validate file size
    if len(file_content) > MAX_FILE_SIZE:
        raise FileValidationError(
            f"File too large. Maximum size: {MAX_FILE_SIZE / (1024*1024)}MB"
        )
    
    # Validate and sanitize filename
    filename = _sanitize_filename(filename)
    _validate_file_extension(filename)
    
    # Generate unique document ID
    doc_id = str(uuid.uuid4())[:12]
    
    # Create date-based subdirectory for organization
    date_dir = datetime.utcnow().strftime("%Y-%m-%d")
    
    # Ensure upload directory exists
    upload_dir = await _ensure_upload_dir()
    
    # Create the target directory path (securely)
    target_dir = upload_dir / "api" / date_dir
    target_dir = _validate_path(upload_dir, target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Create the target file path (securely)
    target_path = target_dir / filename
    target_path = _validate_path(target_dir, target_path)
    
    # If file exists, add UUID suffix to make unique
    if target_path.exists():
        stem = target_path.stem
        suffix = target_path.suffix
        target_path = target_dir / f"{stem}_{doc_id[:6]}{suffix}"
    
    # Write the file
    async with aiofiles.open(target_path, "wb") as f:
        await f.write(file_content)
    
    # Calculate file hash
    file_hash = hashlib.sha256(file_content).hexdigest()
    
    # Store document metadata
    document = {
        "id": doc_id,
        "filename": target_path.name,
        "original_filename": filename,
        "path": str(target_path),
        "size": len(file_content),
        "hash": file_hash,
        "content_type": content_type,
        "metadata": metadata or {},
        "ingested_at": datetime.utcnow().isoformat(),
        "source": "api"
    }
    
    _documents_db[doc_id] = document
    
    return document


async def ingest_file_path(
    file_path: str,
    metadata: Optional[dict] = None
) -> dict:
    """
    Ingest a document from a file path (server-side file access).
    Used for batch processing or server-side file ingestion.
    
    Args:
        file_path: Path to the file to ingest
        metadata: Optional metadata dict
        
    Returns:
        Document metadata including ID and path
        
    Raises:
        PathTraversalError: If path traversal is detected
        FileValidationError: If file validation fails
    """
    # Validate and sanitize the input path
    # This is the CRITICAL check for path traversal
    input_path = Path(file_path)
    
    # Check for suspicious patterns in the path
    if ".." in input_path.parts or input_path.is_absolute():
        # Convert to absolute relative path for validation
        # Don't allow absolute paths from user input
        raise PathTraversalError(
            "Absolute paths and path traversal sequences (..) are not allowed"
        )
    
    # Sanitize the filename portion
    filename = _sanitize_filename(input_path.name)
    _validate_file_extension(filename)
    
    # For file path ingestion, we require the file to be within an allowed directory
    # Define allowed base directories for file ingestion
    allowed_bases = [
        Path("/home/node/.openclaw/workspace-henry/adr-tool-api/uploads"),
        Path("/tmp/adr-uploads/import"),
    ]
    
    # Resolve the file path
    try:
        # Get absolute path and validate it stays within allowed bases
        resolved_path = None
        for base in allowed_bases:
            try:
                # Try to make it relative to this base
                if str(input_path).startswith(str(base)):
                    resolved_path = base / input_path.relative_to(base)
                    break
            except ValueError:
                continue
        
        if resolved_path is None:
            # Default: assume it's relative to the first allowed base
            base = allowed_bases[0]
            resolved_path = (base / filename).resolve()
            resolved_path = _validate_path(base, resolved_path)
        
    except Exception as e:
        raise PathTraversalError(f"Invalid file path: {e}")
    
    # Check file exists
    if not resolved_path.exists():
        raise FileValidationError(f"File not found: {resolved_path}")
    
    # Check file size
    file_size = resolved_path.stat().st_size
    if file_size > MAX_FILE_SIZE:
        raise FileValidationError(
            f"File too large. Maximum size: {MAX_FILE_SIZE / (1024*1024)}MB"
        )
    
    # Read file content
    async with aiofiles.open(resolved_path, "rb") as f:
        file_content = await f.read()
    
    # Generate unique document ID
    doc_id = str(uuid.uuid4())[:12]
    
    # Create date-based subdirectory
    date_dir = datetime.utcnow().strftime("%Y-%m-%d")
    
    # Ensure upload directory exists
    upload_dir = await _ensure_upload_dir()
    
    # Create target directory
    target_dir = upload_dir / "fil" / date_dir
    target_dir = _validate_path(upload_dir, target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Create target file path
    target_path = target_dir / filename
    target_path = _validate_path(target_dir, target_path)
    
    # If file exists, add UUID suffix
    if target_path.exists():
        stem = target_path.stem
        suffix = target_path.suffix
        target_path = target_dir / f"{stem}_{doc_id[:6]}{suffix}"
    
    # Write the file
    async with aiofiles.open(target_path, "wb") as f:
        await f.write(file_content)
    
    # Calculate file hash
    file_hash = hashlib.sha256(file_content).hexdigest()
    
    # Store document metadata
    document = {
        "id": doc_id,
        "filename": target_path.name,
        "original_filename": filename,
        "source_path": str(resolved_path),
        "path": str(target_path),
        "size": file_size,
        "hash": file_hash,
        "metadata": metadata or {},
        "ingested_at": datetime.utcnow().isoformat(),
        "source": "file_path"
    }
    
    _documents_db[doc_id] = document
    
    return document


async def get_document(doc_id: str) -> Optional[dict]:
    """Get document metadata by ID"""
    return _documents_db.get(doc_id)


async def list_documents(limit: int = 50, offset: int = 0) -> List[dict]:
    """List ingested documents"""
    docs = list(_documents_db.values())
    docs.sort(key=lambda x: x["ingested_at"], reverse=True)
    return docs[offset:offset + limit]


async def delete_document(doc_id: str) -> bool:
    """Delete a document"""
    doc = _documents_db.get(doc_id)
    if not doc:
        return False
    
    # Delete the file
    try:
        Path(doc["path"]).unlink(missing_ok=True)
    except Exception:
        pass
    
    del _documents_db[doc_id]
    return True
