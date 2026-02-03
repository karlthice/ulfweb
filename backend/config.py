"""Configuration management for ulfweb."""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000


class LlamaConfig(BaseModel):
    url: str = "http://localhost:8080"


class TildeConfig(BaseModel):
    url: str = "http://localhost:8081"


class DatabaseConfig(BaseModel):
    path: str = "data/ulfweb.db"


class DefaultsConfig(BaseModel):
    temperature: float = 0.7
    top_k: int = 40
    top_p: float = 0.9
    repeat_penalty: float = 1.1
    max_tokens: int = 2048
    system_prompt: str = "You are a helpful assistant."
    model: str = ""


class ModelsConfig(BaseModel):
    path: str = ""
    llama_server: str = "llama-server"


class Settings(BaseSettings):
    server: ServerConfig = ServerConfig()
    llama: LlamaConfig = LlamaConfig()
    tilde: TildeConfig = TildeConfig()
    database: DatabaseConfig = DatabaseConfig()
    defaults: DefaultsConfig = DefaultsConfig()
    models: ModelsConfig = ModelsConfig()

    class Config:
        env_prefix = "ULFWEB_"


def load_config(config_path: str | None = None) -> Settings:
    """Load configuration from YAML file and environment variables."""
    if config_path is None:
        config_path = os.getenv("ULFWEB_CONFIG", "config.yaml")

    config_data: dict[str, Any] = {}

    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file) as f:
            config_data = yaml.safe_load(f) or {}

    # Override with environment variables
    if os.getenv("ULFWEB_LLAMA_URL"):
        config_data.setdefault("llama", {})["url"] = os.getenv("ULFWEB_LLAMA_URL")
    if os.getenv("ULFWEB_TILDE_URL"):
        config_data.setdefault("tilde", {})["url"] = os.getenv("ULFWEB_TILDE_URL")
    if os.getenv("ULFWEB_DATABASE_PATH"):
        config_data.setdefault("database", {})["path"] = os.getenv("ULFWEB_DATABASE_PATH")
    if os.getenv("ULFWEB_SERVER_HOST"):
        config_data.setdefault("server", {})["host"] = os.getenv("ULFWEB_SERVER_HOST")
    if os.getenv("ULFWEB_SERVER_PORT"):
        config_data.setdefault("server", {})["port"] = int(os.getenv("ULFWEB_SERVER_PORT"))
    if os.getenv("ULFWEB_MODELS_PATH"):
        config_data.setdefault("models", {})["path"] = os.getenv("ULFWEB_MODELS_PATH")
    if os.getenv("ULFWEB_LLAMA_SERVER"):
        config_data.setdefault("models", {})["llama_server"] = os.getenv("ULFWEB_LLAMA_SERVER")

    return Settings(**config_data)


# Global settings instance
settings = load_config()
