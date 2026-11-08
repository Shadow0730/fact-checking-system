"""Settings read from the repository-root .env (see .env.example)."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(REPO_DIR / ".env"), extra="ignore")

    sarvam_api_key: str = ""
    sarvam_base_url: str = "https://api.sarvam.ai"
    sarvam_llm_model: str = "sarvam-105b"
    sarvam_llm_path: str = "/v2/chat/completions"
    sarvam_llm_reasoning_effort: str = "none"
    sarvam_llm_max_tokens: int = 6000
    sarvam_llm_temperature: float = 0.1
    sarvam_prism_model: str = "sarvam-prism"
    sarvam_prism_path: str = "/v2/systemone"
    sarvam_timeout_s: float = 60
    sarvam_max_concurrency: int = 4
    offline_mode: bool = False

    # Indian Kanoon: look up citations that are not in the local corpus (empty token = off).
    indiankanoon_api_token: str = ""
    indiankanoon_base_url: str = "https://api.indiankanoon.org"
    indiankanoon_timeout_s: float = 30
    indiankanoon_max_lookups: int = 8          # per check, to cap cost

    # Empty = no database: the corpus is loaded into memory and checks are saved as JSON under data/.
    database_url: str = ""
    data_dir: str = "../data"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    embedding_device: str = "cpu"
    embedding_batch_size: int = 16
    hf_token: str = ""

    corpus_dir: str = "../corpus"
    chunk_target_chars: int = 1800
    chunk_max_chars: int = 3000

    retrieval_top_k: int = 5
    retrieval_candidates: int = 20
    rrf_k: int = 60

    thresh_supported: float = 0.90
    thresh_weak: float = 0.60
    thresh_contradicted: float = 0.50
    quote_exact: float = 97
    quote_near: float = 85

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    log_level: str = "INFO"
    max_draft_chars: int = 60000
    max_upload_mb: int = 20

    def model_post_init(self, _):
        if not self.offline_mode and not self.sarvam_api_key:
            raise ValueError("SARVAM_API_KEY is required unless OFFLINE_MODE=true (see .env.example)")

    @property
    def corpus_path(self) -> Path:
        p = Path(self.corpus_dir)
        return p if p.is_absolute() else (BACKEND_DIR / p).resolve()

    @property
    def use_db(self) -> bool:
        return bool(self.database_url.strip())

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        return p if p.is_absolute() else (BACKEND_DIR / p).resolve()

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
