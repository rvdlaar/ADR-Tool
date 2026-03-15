"""Settings API — API key, output folder, preferences. Stored in data/settings.json."""
import os
import json
from pathlib import Path
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/settings", tags=["Settings"])

SETTINGS_PATH = Path("data/settings.json")


class Settings(BaseModel):
    ai_api_key: Optional[str] = None
    ai_model: Optional[str] = None
    ai_base_url: Optional[str] = None
    output_folder: Optional[str] = None  # Auto-save accepted ADRs here
    embedding_model: Optional[str] = None


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text())
        except Exception:
            pass
    return {}


def save_settings(data: dict):
    SETTINGS_PATH.parent.mkdir(exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, indent=2))


def apply_settings_to_env(data: dict):
    """Push settings into environment variables so services pick them up."""
    mappings = {
        "ai_api_key": "AI_API_KEY",
        "ai_model": "AI_MODEL",
        "ai_base_url": "AI_BASE_URL",
        "embedding_model": "EMBEDDING_MODEL",
    }
    for key, env_var in mappings.items():
        val = data.get(key)
        if val:
            os.environ[env_var] = val

    # Reset singletons so they pick up new env vars
    try:
        from app.services.ai_generator import get_generator
        import app.services.ai_generator as gen_mod
        gen_mod._generator = None
    except Exception:
        pass
    try:
        from app.services.embeddings import get_embedding_service
        import app.services.embeddings as emb_mod
        emb_mod._service = None
    except Exception:
        pass


@router.get("")
async def get_settings():
    """Get current settings (API key masked)."""
    data = load_settings()
    # Mask API key
    masked = dict(data)
    if masked.get("ai_api_key"):
        key = masked["ai_api_key"]
        masked["ai_api_key"] = key[:4] + "..." + key[-4:] if len(key) > 8 else "***"
    masked["ai_configured"] = bool(data.get("ai_api_key") or os.getenv("AI_API_KEY"))
    masked["output_folder"] = data.get("output_folder", "")
    return masked


@router.put("")
async def update_settings(settings: Settings):
    """Update settings. Only non-null fields are applied."""
    data = load_settings()
    update = settings.model_dump(exclude_none=True)
    data.update(update)
    save_settings(data)
    apply_settings_to_env(data)
    return {"ok": True, "updated": list(update.keys())}


@router.post("/save-adr-to-folder")
async def save_adr_to_folder(body: dict):
    """Save a markdown file to the configured output folder."""
    data = load_settings()
    folder = data.get("output_folder")
    if not folder:
        return {"error": "No output folder configured", "saved": False}

    folder_path = Path(os.path.expanduser(folder))
    if not folder_path.exists():
        try:
            folder_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return {"error": f"Cannot create folder: {e}", "saved": False}

    filename = body.get("filename", "untitled.md")
    content = body.get("content", "")

    # Security: no path traversal
    filename = Path(filename).name

    file_path = folder_path / filename
    try:
        file_path.write_text(content, encoding="utf-8")
        return {"saved": True, "path": str(file_path)}
    except Exception as e:
        return {"error": str(e), "saved": False}


# Apply saved settings on import
_initial = load_settings()
if _initial:
    apply_settings_to_env(_initial)
