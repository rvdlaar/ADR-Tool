# Security Remediations - Vincent's Re-Audit
# AI ADR Tool API - Security Fixes

## Summary
All critical security issues identified in the previous audit have been addressed.

---

## Issue 5: Path Traversal Vulnerability in Document Ingestion Pipeline
**Files:** 
- `app/services/ingest.py` (new)
- `app/api/ingest.py` (new)

**Problem:** No document ingestion pipeline existed, requiring creation of secure `ingestApi` and `ingestFil` endpoints with protection against path traversal attacks.

**Fix:** Implemented comprehensive path traversal protection:

### Security Measures Implemented

1. **Filename Sanitization** (`_sanitize_filename`):
   - Removes null bytes and control characters
   - Extracts only the basename (removes directory components)
   - Filters to alphanumeric, dots, dashes, and underscores
   - Generates fallback names for empty/dotfile inputs

2. **Path Validation** (`_validate_path`):
   - Resolves both base and target paths to absolute paths
   - Uses `relative_to()` to verify target stays within base
   - Raises `PathTraversalError` if path escapes base directory
   - Blocks `../` sequences and absolute paths

3. **File Type Validation** (`_validate_file_extension`):
   - Whitelist approach: only allows `.txt`, `.md`, `.pdf`, `.doc`, `.docx`, `.json`, `.yaml`, `.yml`, `.xml`, `.csv`
   - Rejects all other extensions

4. **File Size Limits**:
   - Maximum file size: 10MB
   - Checked before writing to prevent DoS

5. **Unique File Naming**:
   - UUID-based unique IDs for each document
   - Date-based subdirectory organization (`YYYY-MM-DD`)
   - Automatic suffix addition if filename conflicts

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/ingest/api` | POST | Ingest via base64/text content (ingestApi) |
| `/api/v1/ingest/file` | POST | Ingest from server file path (ingestFil) |
| `/api/v1/ingest/upload` | POST | Multipart file upload |
| `/api/v1/ingest` | GET | List ingested documents |
| `/api/v1/ingest/{id}` | GET | Get document metadata |
| `/api/v1/ingest/{id}` | DELETE | Delete document |

### Code Examples

**Path Validation (critical security check):**
```python
def _validate_path(base_dir: Path, target_path: Path) -> Path:
    """Securely resolve path and ensure it stays within base directory"""
    base_dir = base_dir.resolve()
    target_path = target_path.resolve()
    
    try:
        target_path.relative_to(base_dir)
    except ValueError:
        raise PathTraversalError(
            f"Path traversal detected: '{target_path}' is outside '{base_dir}'"
        )
    
    return target_path
```

**File Path Ingestion (blocks traversal):**
```python
async def ingest_file_path(file_path: str, metadata: Optional[dict] = None):
    input_path = Path(file_path)
    
    # Block absolute paths and .. sequences
    if ".." in input_path.parts or input_path.is_absolute():
        raise PathTraversalError(
            "Absolute paths and '..' are not allowed"
        )
    
    # Validate against allowed base directories
    allowed_bases = [
        Path("/home/node/.openclaw/workspace-henry/adr-tool-api/uploads"),
        Path("/tmp/adr-uploads/import"),
    ]
    
    # Resolve and validate the path stays within allowed bases
    resolved_path = _validate_path(allowed_bases[0], resolved_path)
```

---

## Issue 1: Hardcoded Test API Key
**File:** `app/core/security.py`
**Function:** `get_user_from_api_key()`

**Problem:** Hardcoded test API key `"test-api-key-12345"` was always valid, even in production.

**Fix:** The test API key is now only valid when `ENVIRONMENT` environment variable is set to `"test"`:
```python
environment = os.getenv("ENVIRONMENT", "").lower()
if environment == "test":
    valid_api_keys.append("test-api-key-12345")
```

---

## Issue 2: Insecure Password Verification
**File:** `app/core/security.py`
**Functions:** `verify_password()`, `get_password_hash()`

**Problem:** Placeholder implementation that just compared plain text passwords.

**Fix:** Implemented proper bcrypt hashing using passlib:
```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)
```

**File:** `app/api/auth.py`
**Function:** `login()`

**Problem:** Login endpoint accepted any non-empty credentials.

**Fix:** Added proper user authentication with bcrypt verification:
- Created `MOCK_USERS_DB` with bcrypt-hashed passwords
- Created `authenticate_user()` function that uses `verify_password()`
- Login now validates against stored password hashes

---

## Issue 3: Refresh Token Loses Original Scopes
**Files:** 
- `app/core/security.py` - `create_refresh_token()`
- `app/api/auth.py` - `login()` and `refresh_token()`

**Problem:** When refreshing tokens, original scopes were lost and defaulted to `["adr:read", "adr:write"]`.

**Fix:** 
1. Updated `create_refresh_token()` to accept optional `scopes` parameter:
```python
def create_refresh_token(data: dict, scopes: Optional[List[str]] = None) -> str:
    # ... stores scopes in token payload
    "scopes": scopes or []
```

2. Login endpoint now passes scopes to refresh token creation:
```python
refresh_token = create_refresh_token(
    data={**token_data, "scopes": valid_scopes}
)
```

3. Refresh endpoint extracts and preserves original scopes:
```python
scopes = payload.get("scopes", ["adr:read"])
```

---

## Issue 4: Import Placement and SECRET_KEY Unification
**File:** `app/api/auth.py`

**Problems:**
- `import os` was at the bottom of the file
- Refresh token endpoint hardcoded SECRET_KEY fallback: `os.getenv("SECRET_KEY", "CHANGE_ME_IN_PRODUCTION")`

**Fix:**
- Moved `import os` (and all other imports) to the top of the file
- Now imports and uses centralized `SECRET_KEY` and `ALGORITHM` from `app.core.security`
- Removed duplicate imports in `create_api_key()` function

---

## Testing Notes

### Demo Credentials
The following test users are available (password: "password123"):
- **admin**: Full access (adr:read, adr:write, adr:delete, admin:users, admin:settings)
- **user**: Read/write access (adr:read, adr:write)
- **reader**: Read-only access (adr:read)

### Environment Configuration
To run in test mode (enables test API key):
```bash
ENVIRONMENT=test
```

### API Key Authentication
To use API key auth, set valid keys via environment variable:
```
VALID_API_KEYS=key1,key2,key3
```

---

## Files Modified
1. `app/core/security.py` - Password hashing, API key gating, refresh token scopes
2. `app/api/auth.py` - Login verification, refresh token scopes, import cleanup