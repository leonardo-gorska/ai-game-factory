"""
GORVAX GAME FACTORY — Configuration
Loads settings from .env and provides typed config objects.
"""

from __future__ import annotations

from typing import Any

import json
import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
GAME_DIR = ROOT_DIR / "game"
DASHBOARD_DIR = ROOT_DIR / "dashboard"
STORAGE_DIR = BACKEND_DIR / "storage"
ITERATIONS_DIR = STORAGE_DIR / "iterations"
PROMPTS_DIR = BACKEND_DIR / "llm" / "prompts"

# Ensure directories exist
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
ITERATIONS_DIR.mkdir(parents=True, exist_ok=True)

# ── Load .env ──────────────────────────────────────────
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for LLM providers."""
    gemini_api_key: str = ""
    sambanova_api_key: str = ""
    cerebras_api_key: str = ""
    groq_api_key: str = ""
    mistral_api_key: str = ""
    openrouter_api_key: str = ""

    # Model mappings — ordered by ranking (best first)
    sambanova_model: str = "sambanova/DeepSeek-V3.1"            # 🥇 Best free: fast, great JSON
    cerebras_model: str = "cerebras/llama3.1-8b"                # 🥉 Ultra-fast, small prompts
    gemini_model: str = "gemini/gemini-2.0-flash"
    groq_model: str = "groq/llama-3.1-8b-instant"
    mistral_model: str = "mistral/mistral-small-latest"
    openrouter_model: str = "openrouter/qwen/qwen3-coder:free"
    openrouter_fallback_model: str = "openrouter/meta-llama/llama-3.3-70b-instruct:free"

    @classmethod
    def from_env(cls) -> LLMConfig:
        return cls(
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            sambanova_api_key=os.getenv("SAMBANOVA_API_KEY", ""),
            cerebras_api_key=os.getenv("CEREBRAS_API_KEY", ""),
            groq_api_key=os.getenv("GROQ_API_KEY", ""),
            mistral_api_key=os.getenv("MISTRAL_API_KEY", ""),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        )

    def available_providers(self) -> list[str]:
        """Return list of providers with configured API keys."""
        providers: list[str] = []
        if self.sambanova_api_key:
            providers.append("sambanova")
        if self.cerebras_api_key:
            providers.append("cerebras")
        if self.gemini_api_key:
            providers.append("gemini")
        if self.groq_api_key:
            providers.append("groq")
        if self.mistral_api_key:
            providers.append("mistral")
        if self.openrouter_api_key:
            providers.append("openrouter")
        return providers

    def get_agent_override(self, agent_name: str) -> str | None:
        """Get forced provider for critical agents (bypasses smart routing).
        
        Checks env vars LLM_DEVELOPER_MODEL / LLM_DESIGNER_MODEL first.
        If not set, auto-selects the most capable available provider.
        """
        # Check env var override
        env_key = f"LLM_{agent_name.upper()}_MODEL"
        env_override = os.getenv(env_key, "")
        if env_override and env_override in self.available_providers():
            return env_override
        # Auto-select best available for critical agents
        # Priority: sambanova (DeepSeek V3.1), openrouter, mistral, cerebras, groq
        if agent_name in ("developer", "designer"):
            prefs = ["sambanova", "openrouter", "mistral", "cerebras", "groq"]
            for p in prefs:
                if p in self.available_providers():
                    return p
        return None

    def get_model(self, provider: str) -> str:
        """Get the model identifier for a provider."""
        mapping = {
            "sambanova": self.sambanova_model,
            "cerebras": self.cerebras_model,
            "gemini": self.gemini_model,
            "groq": self.groq_model,
            "mistral": self.mistral_model,
            "openrouter": self.openrouter_model,
        }
        return mapping.get(provider, self.sambanova_model)

    def get_fallback_models(self, provider: str) -> list[str]:
        """Get fallback model(s) for a provider. Returns empty list if none."""
        fallbacks: dict[str, list[str]] = {
            "sambanova": ["sambanova/Meta-Llama-3.3-70B-Instruct", "sambanova/Qwen3-235B"],
            "cerebras": ["cerebras/gpt-oss-120b"],
            "openrouter": [self.openrouter_fallback_model],
        }
        return fallbacks.get(provider, [])

    def get_api_key(self, provider: str) -> str:
        """Get the API key for a provider."""
        mapping = {
            "sambanova": self.sambanova_api_key,
            "cerebras": self.cerebras_api_key,
            "gemini": self.gemini_api_key,
            "groq": self.groq_api_key,
            "mistral": self.mistral_api_key,
            "openrouter": self.openrouter_api_key,
        }
        return mapping.get(provider, "")


# ── Valid options for ProjectConfig (single source of truth) ──
VALID_PLATFORMS = ("browser", "desktop", "mobile", "console")
VALID_ENGINES = ("phaser3", "pixijs", "threejs", "canvas", "unity", "godot", "unreal")
VALID_GENRES = (
    "idle_rpg", "action", "puzzle", "tower_defense", "platformer",
    "racing", "roguelike", "survival", "strategy", "simulation",
)
VALID_MONETIZATIONS = ("free_with_ads", "freemium", "hybrid", "premium", "none")

PLATFORM_LABELS = {
    "browser": "navegador (browser)",
    "desktop": "desktop (Electron)",
    "mobile": "mobile (PWA)",
    "console": "console (exportado)",
}

ENGINE_LABELS = {
    "phaser3": "Phaser 3",
    "pixijs": "Pixi.js",
    "threejs": "Three.js",
    "canvas": "Canvas puro",
    "unity": "Unity (WebGL)",
    "godot": "Godot (HTML5)",
    "unreal": "Unreal (Pixel Streaming)",
}

GENRE_LABELS = {
    "idle_rpg": "idle RPG",
    "action": "ação",
    "puzzle": "puzzle",
    "tower_defense": "tower defense",
    "platformer": "plataforma",
    "racing": "corrida",
    "roguelike": "roguelike",
    "survival": "sobrevivência",
    "strategy": "estratégia",
    "simulation": "simulação",
}

MONETIZATION_LABELS = {
    "free_with_ads": "Grátis + Anúncios",
    "freemium": "Freemium (IAP)",
    "hybrid": "Híbrido (Ads + IAP)",
    "premium": "Premium (Pago)",
    "none": "Sem Monetização",
}


@dataclass(frozen=True)
class ProjectConfig:
    """Configuration for the game project being developed."""
    game_name: str = "Realm Forge"
    platform: str = "browser"
    engine: str = "phaser3"
    genre: str = "idle_rpg"
    monetization: str = "hybrid"
    max_iterations: int = 10000

    def to_prompt_vars(self) -> dict[str, str]:
        """Return variables for prompt template rendering."""
        from backend.llm.prompt_engine import MONETIZATION_STRATEGIES
        return {
            "game_name": self.game_name,
            "engine_label": ENGINE_LABELS.get(self.engine, self.engine),
            "genre_label": GENRE_LABELS.get(self.genre, self.genre),
            "platform_label": PLATFORM_LABELS.get(self.platform, self.platform),
            "monetization_label": MONETIZATION_LABELS.get(self.monetization, self.monetization),
            "monetization_strategy": MONETIZATION_STRATEGIES.get(self.monetization, ""),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_name": self.game_name,
            "platform": self.platform,
            "engine": self.engine,
            "genre": self.genre,
            "monetization": self.monetization,
            "max_iterations": self.max_iterations,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectConfig:
        return cls(
            game_name=data.get("game_name", "Realm Forge"),
            platform=data.get("platform", "browser"),
            engine=data.get("engine", "phaser3"),
            genre=data.get("genre", "idle_rpg"),
            monetization=data.get("monetization", "hybrid"),
            max_iterations=int(data.get("max_iterations", 10000)),
        )


def load_project_config() -> ProjectConfig:
    """Load project config from project.json, or return defaults."""
    path = ROOT_DIR / "project.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return ProjectConfig.from_dict(json.load(f))
        except Exception:
            pass
    return ProjectConfig()


def save_project_config(config: ProjectConfig) -> None:
    """Save project config to project.json."""
    path = ROOT_DIR / "project.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)


@dataclass(frozen=True)
class PipelineConfig:
    """Configuration for the AI pipeline."""
    max_iterations: int = 10000
    iteration_delay_seconds: int = 30
    quality_threshold: int = 80
    max_build_retries: int = 2

    @classmethod
    def from_env(cls) -> PipelineConfig:
        return cls(
            max_iterations=int(os.getenv("MAX_ITERATIONS", "10000")),
            iteration_delay_seconds=int(os.getenv("ITERATION_DELAY_SECONDS", "30")),
            quality_threshold=int(os.getenv("QUALITY_THRESHOLD", "80")),
            max_build_retries=int(os.getenv("MAX_BUILD_RETRIES", "2")),
        )


@dataclass(frozen=True)
class ServerConfig:
    """Configuration for the API server."""
    backend_port: int = 8000
    dashboard_port: int = 3000
    game_port: int = 5173
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> ServerConfig:
        return cls(
            backend_port=int(os.getenv("BACKEND_PORT", "8000")),
            dashboard_port=int(os.getenv("DASHBOARD_PORT", "3000")),
            game_port=int(os.getenv("GAME_PORT", "5173")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


@dataclass(frozen=True)
class AppConfig:
    """Root configuration object."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    project: ProjectConfig = field(default_factory=ProjectConfig)

    @classmethod
    def from_env(cls) -> AppConfig:
        return cls(
            llm=LLMConfig.from_env(),
            pipeline=PipelineConfig.from_env(),
            server=ServerConfig.from_env(),
            project=load_project_config(),
        )


# ── Singleton ──────────────────────────────────────────
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Get or create the application config singleton."""
    global _config
    if _config is None:
        _config = AppConfig.from_env()
    return _config
