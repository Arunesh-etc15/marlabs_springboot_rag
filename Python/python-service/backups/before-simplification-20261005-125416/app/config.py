from dataclasses import dataclass
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = ROOT.parent if (ROOT.parent / "spring-api").is_dir() else ROOT.parent.parent / "SpringBoot"


@dataclass(frozen=True)
class Settings:
    mode: str = "ollama"
    ollama_url: str = "http://localhost:11434"
    model: str = "llama3.2:3b"
    embedding_model: str = "nomic-embed-text"
    timeout_seconds: float = 20.0
    chroma_path: Path = ROOT / ".chroma"
    policy_file: Path = DEFAULT_DATA_ROOT / "policies.json"
    callers_file: Path = DEFAULT_DATA_ROOT / "spring-api/src/main/resources/callers.json"

    @classmethod
    def from_env(cls):
        settings = cls(
            mode=os.getenv("MODEL_MODE", "ollama"),
            ollama_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
            embedding_model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
            timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "20")),
            chroma_path=Path(os.getenv("CHROMA_PATH", str(ROOT / ".chroma"))),
            policy_file=Path(os.getenv("POLICY_FILE", str(DEFAULT_DATA_ROOT / "policies.json"))),
            callers_file=Path(os.getenv("CALLERS_FILE", str(DEFAULT_DATA_ROOT / "spring-api/src/main/resources/callers.json"))),
        )
        if settings.mode not in {"ollama", "offline"} or not 0 < settings.timeout_seconds <= 60:
            raise ValueError("MODEL_MODE must be ollama/offline; timeout must be between 0 and 60 seconds.")
        return settings
