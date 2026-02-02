"""Configuration loader for debate bot agents and settings."""

import os
from pathlib import Path
from typing import Optional

import yaml


class Config:
    """Load and manage configuration from YAML file."""

    _instance: Optional["Config"] = None
    _config: dict = {}

    def __new__(cls) -> "Config":
        """Singleton pattern for config loading."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self) -> None:
        """Load configuration from config.yaml file."""
        config_path = Path(__file__).parent.parent / "config.yaml"

        if not config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found at {config_path}. "
                "Please ensure config.yaml exists in the project root."
            )

        with open(config_path, "r") as f:
            self._config = yaml.safe_load(f) or {}

    def get_agent_model(self, agent_name: str) -> str:
        """Get the model for a specific agent.

        Args:
            agent_name: Name of the agent (e.g., 'case_generator', 'research')

        Returns:
            Model identifier string (e.g., 'claude-opus-4-5-20251101')
        """
        model = (
            self._config.get("agents", {}).get(agent_name, {}).get("model")
        )
        if not model:
            raise ValueError(
                f"Model not configured for agent '{agent_name}'. "
                "Please check config.yaml agents section."
            )
        return model

    def get_max_tokens(self) -> int:
        """Get the maximum tokens setting.

        Returns:
            Maximum tokens per response (default: 4096)
        """
        return self._config.get("api", {}).get("max_tokens", 4096)

    def get_case_word_limits(self) -> tuple[int, int]:
        """Get min and max word limits for case contentions.

        Returns:
            Tuple of (min_words, max_words) (default: (100, 500))
        """
        case_config = self._config.get("case", {}).get("contentions", {})
        min_words = case_config.get("min_words", 100)
        max_words = case_config.get("max_words", 500)
        return (min_words, max_words)

    def get_case_total_time(self) -> int:
        """Get total time limit for case in seconds.

        Returns:
            Total time in seconds (default: 240 for 4 minutes)
        """
        return self._config.get("case", {}).get("total_time_seconds", 240)

    def get_speech_word_limits(self) -> tuple[int, int]:
        """Get min and max word limits for generated speeches.

        Returns:
            Tuple of (min_words, max_words) (default: (50, 300))
        """
        speech_config = self._config.get("speech", {}).get("generation", {})
        min_words = speech_config.get("min_words", 50)
        max_words = speech_config.get("max_words", 300)
        return (min_words, max_words)
