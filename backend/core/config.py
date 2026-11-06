"""
Central configuration for the CheckoutPilot backend.

All settings are read from environment variables (loaded from the .env file
in the project root). Other code should import `settings` from here instead
of calling os.getenv() everywhere.

Example:
    from backend.core.config import settings
    print(settings.paypal_api_base)
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load variables from the .env file (if it exists) into the environment.
load_dotenv()


def _split_csv(value: str) -> list[str]:
    """Turn 'a, b, c' into ['a', 'b', 'c'], ignoring empty items."""
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class Settings:
    """Application settings. Defaults are safe placeholders for local development."""

    app_name: str = "CheckoutPilot API"
    app_version: str = "0.1.0"
    app_env: str = os.getenv("APP_ENV", "development")

    cors_origins: list[str] = field(
        default_factory=lambda: _split_csv(os.getenv("CORS_ORIGINS", "http://localhost:8501"))
    )

    # AI provider
    ai_provider: str = os.getenv("AI_PROVIDER", "anthropic")

    # PayPal Sandbox
    paypal_environment: str = os.getenv("PAYPAL_ENVIRONMENT", "sandbox")
    paypal_client_id: str = os.getenv("PAYPAL_CLIENT_ID", "")
    paypal_client_secret: str = os.getenv("PAYPAL_CLIENT_SECRET", "")
    paypal_api_base: str = os.getenv("PAYPAL_API_BASE", "https://api-m.sandbox.paypal.com")


# A single shared settings object used across the backend.
settings = Settings()
