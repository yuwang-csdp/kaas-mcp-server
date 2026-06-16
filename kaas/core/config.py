from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Auth — comma-separated list of valid API keys
    API_KEYS: list[str] = [
        k.strip()
        for k in os.getenv("KAAS_API_KEYS", "dev-key-1,dev-key-2").split(",")
        if k.strip()
    ]

    # Feature flags
    GRAPH_ENABLED: bool = os.getenv("KAAS_GRAPH_ENABLED", "false").lower() == "true"

    # Retriever defaults
    DEFAULT_TOP_K: int = int(os.getenv("KAAS_DEFAULT_TOP_K", "5"))
    DEFAULT_MAX_PRODUCTS: int = int(os.getenv("KAAS_DEFAULT_MAX_PRODUCTS", "3"))

    # Service identity
    TAXONOMY_VERSION: str = "0.1.0"
    CLASSIFIER_VERSION: str = "rules-v0"
    C360_CONNECTIVITY: str = "dummy"  # "ok" | "degraded" | "down" | "dummy"


settings = Settings()
