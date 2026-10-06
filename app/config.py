import os
from pathlib import Path

ROOT = Path(os.getenv("HERAMA_ROOT", Path(__file__).resolve().parent.parent))
MODELS_DIR = Path(os.getenv("HERAMA_MODELS", ROOT / "models"))
MEMORY_DIR = ROOT / ".memory"
SKILLS_DIR = ROOT / "skills"
HOST = os.getenv("HERAMA_HOST", "127.0.0.1")
PORT = int(os.getenv("HERAMA_PORT", "11434"))  # Ollama default
SKILL_EXEC = os.getenv("HERAMA_SKILL_EXEC") == "1"
SKILL_TIMEOUT = int(os.getenv("HERAMA_SKILL_TIMEOUT", "10"))  # seconds
RAM_HEADROOM = 0.8  # fraction of free memory usable
