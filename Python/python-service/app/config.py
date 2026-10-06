"""File locations and configurable service settings."""

from dataclasses import dataclass
from pathlib import Path
import os

CURRENT_FILE = Path(__file__).resolve()
ROOT = CURRENT_FILE.parent.parent
# Support both the original sibling folders and your separate Python/SpringBoot folders.
if (ROOT.parent / "spring-api").is_dir():
    DEFAULT_DATA_ROOT = ROOT.parent
    DEFAULT_POLICY_ROOT = ROOT.parent
else:
    DEFAULT_DATA_ROOT = ROOT.parent.parent / "SpringBoot"
    DEFAULT_POLICY_ROOT = ROOT.parent.parent


@dataclass(frozen=True)
class Settings:
    ollama_url: str = "http://localhost:11434"
    model: str = "llama3.2:3b"
    embedding_model: str = "nomic-embed-text"
    timeout_seconds: float = 20.0
    chroma_path: Path = ROOT / ".chroma"
    policy_file: Path = DEFAULT_POLICY_ROOT / "marlabs_policydata.pdf"
    callers_file: Path = DEFAULT_DATA_ROOT / "spring-api/src/main/resources/callers.json"

    @classmethod
    def from_env(cls):
        """Use environment variables when present; otherwise use the defaults above."""
        defaults = cls()
        # Environment variables are strings, so convert numbers and file paths.
        ollama_url = os.getenv("OLLAMA_BASE_URL", defaults.ollama_url)
        model = os.getenv("OLLAMA_MODEL", defaults.model)
        embedding_model = os.getenv("OLLAMA_EMBED_MODEL", defaults.embedding_model)
        timeout_text = os.getenv("OLLAMA_TIMEOUT_SECONDS", str(defaults.timeout_seconds))
        chroma_path = os.getenv("CHROMA_PATH", str(defaults.chroma_path))
        policy_file = os.getenv("POLICY_FILE", str(defaults.policy_file))
        callers_file = os.getenv("CALLERS_FILE", str(defaults.callers_file))
        settings = cls(
            ollama_url=ollama_url,
            model=model,
            embedding_model=embedding_model,
            timeout_seconds=float(timeout_text),
            chroma_path=Path(chroma_path),
            policy_file=Path(policy_file),
            callers_file=Path(callers_file),
        )
        valid_timeout = 0 < settings.timeout_seconds <= 60
        if not valid_timeout:
            raise ValueError("OLLAMA_TIMEOUT_SECONDS must be greater than 0 and at most 60.")
        return settings
