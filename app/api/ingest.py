"""
Document Ingestion API endpoints.
Provides secure endpoints for ingesting documents into the ADR Tool.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from pydantic import BaseModel

from app.core.security import User, require_scopes
from app.services import ingest as ingest_service

router = APIRouter(prefix="/ingest", tags=["Document Ingestion"])


# =============================================================================
# Request/Response Models
# =============================================================================

class MetadataField(BaseModel):
    """Key-value metadata field"""
    key: str
    value: str


class IngestApiRequest(BaseModel):
    """Request model for API-based document ingestion"""
    filename: str
    content: str  # Base64-encoded or plain text content
    content_type: Optional[str] = None
    metadata: Optional[dict] = None


class IngestFilRequest(BaseModel):
    """Request model for file-path based document ingestion"""
    file_path: str
    metadata: Optional[dict] = None


class IngestResponse(BaseModel):
    """Response model for successful document ingestion"""
    id: str
    filename: str
    original_filename: str
    path: str
    size: int
    hash: str
    source: str
    ingested_at: str
    metadata: dict


class DocumentListResponse(BaseModel):
    """Response model for document listing"""
    items: List[IngestResponse]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    """Error response model"""
    detail: str
    error_type: Optional[str] = None


# =============================================================================
# API Endpoints
# =============================================================================


@router.post(
    "/api",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest document via API",
    description="""
    Ingest a document by providing file content directly in the request body.
    
    **Security Features:**
    - Path traversal protection via filename sanitization
    - File type validation (allowed: txt, md, pdf, doc, docx, json, yaml, xml, csv)
    - File size limit: 10MB
    - Files stored in date-based subdirectories with unique IDs
    
    **Requires:** adr:write scope
    """
)
async def ingest_api(
    filename: str = Form(..., description="Original filename"),
    content: str = Form(..., description="File content (text or base64)"),
    content_type: Optional[str] = Form(None, description="Content MIME type"),
    metadata_json: Optional[str] = Form(None, description="Optional metadata as JSON"),
    user: User = Depends(require_scopes(["adr:write"]))
):
    """
    Ingest a document via API (ingestApi).
    
    The content can be plain text or base64-encoded. The filename is sanitized
    to prevent path traversal attacks.
    """
    import json
    import base64
    
    try:
        # Parse metadata if provided
        metadata = None
        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid metadata JSON: {e}"
                )
        
        # Try to decode as base64, fall back to plain text
        try:
            file_content = base64.b64decode(content)
        except Exception:
            # Treat as plain text if not valid base64
            file_content = content.encode("utf-8")
        
        # Ingest the document
        document = await ingest_service.ingest_file_api(
            file_content=file_content,
            filename=filename,
            content_type=content_type,
            metadata=metadata
        )
        
        return IngestResponse(**document)
        
    except ingest_service.PathTraversalError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ingest_service.FileValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest document: {str(e)}"
        )


@router.post(
    "/file",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest document from file path",
    description="""
    Ingest a document by providing a server-side file path.
    
    **Security Features:**
    - Strict path traversal protection (blocks .. and absolute paths)
    - Files must be within allowed directories
    - Path validation ensures files stay within allowed bases
    - File type validation and size limits enforced
    
    **Requires:** adr:write scope
    """
)
async def ingest_file(
    file_path: str = Form(..., description="Server-side file path to ingest"),
    metadata_json: Optional[str] = Form(None, description="Optional metadata as JSON"),
    user: User = Depends(require_scopes(["adr:write"]))
):
    """
    Ingest a document from a file path (ingestFil).
    
    ⚠️ **SECURITY NOTE:** This endpoint allows server-side file access.
    The file_path is strictly validated to prevent path traversal attacks.
    Only files within configured allowed directories can be ingested.
    """
    import json
    
    try:
        # Parse metadata if provided
        metadata = None
        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid metadata JSON: {e}"
                )
        
        # Ingest the document
        document = await ingest_service.ingest_file_path(
            file_path=file_path,
            metadata=metadata
        )
        
        return IngestResponse(**document)
        
    except ingest_service.PathTraversalError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path traversal blocked: {str(e)}"
        )
    except ingest_service.FileValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest document: {str(e)}"
        )


@router.post(
    "/upload",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload document via multipart form",
    description="""
    Upload a document using multipart/form-data.
    
    **Security Features:**
    - Path traversal protection
    - File type validation
    - File size limit: 10MB
    
    **Requires:** adr:write scope
    """
)
async def upload_file(
    file: UploadFile = File(..., description="File to upload"),
    metadata_json: Optional[str] = Form(None, description="Optional metadata as JSON"),
    user: User = Depends(require_scopes(["adr:write"]))
):
    """Upload a document via multipart form data"""
    import json
    
    try:
        # Read file content
        file_content = await file.read()
        
        # Parse metadata if provided
        metadata = None
        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid metadata JSON: {e}"
                )
        
        # Get content type
        content_type = file.content_type
        
        # Ingest the document
        document = await ingest_service.ingest_file_api(
            file_content=file_content,
            filename=file.filename or "unknown",
            content_type=content_type,
            metadata=metadata
        )
        
        return IngestResponse(**document)
        
    except ingest_service.PathTraversalError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ingest_service.FileValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload document: {str(e)}"
        )


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List ingested documents",
    description="List all ingested documents with pagination"
)
async def list_documents(
    limit: int = Query(50, ge=1, le=100, description="Maximum documents to return"),
    offset: int = Query(0, ge=0, description="Number of documents to skip"),
    user: User = Depends(require_scopes(["adr:read"]))
):
    """List all ingested documents"""
    documents = await ingest_service.list_documents(limit=limit, offset=offset)
    total = len(documents)  # Note: This is approximate with offset
    
    return DocumentListResponse(
        items=[IngestResponse(**doc) for doc in documents],
        total=total,
        limit=limit,
        offset=offset
    )


@router.get(
    "/{doc_id}",
    response_model=IngestResponse,
    summary="Get document by ID",
    description="Get metadata for a specific ingested document"
)
async def get_document(
    doc_id: str,
    user: User = Depends(require_scopes(["adr:read"]))
):
    """Get document metadata by ID"""
    document = await ingest_service.get_document(doc_id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id '{doc_id}' not found"
        )
    
    return IngestResponse(**document)


@router.delete(
    "/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
    description="Delete an ingested document and its file"
)
async def delete_document(
    doc_id: str,
    user: User = Depends(require_scopes(["adr:delete"]))
):
    """Delete an ingested document"""
    deleted = await ingest_service.delete_document(doc_id)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id '{doc_id}' not found"
        )
    
    return None
