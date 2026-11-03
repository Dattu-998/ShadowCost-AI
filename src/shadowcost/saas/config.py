"""Server settings for the hosted product, all from environment variables.

Every integration is optional: a server without Stripe keys simply reports billing as not
configured, so the open-source code runs locally with nothing but the demo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from shadowcost.llm import load_dotenv


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_secret_key: str
    site_url: str  # the web app, for redirects and links in emails
    api_url: str  # this API's public URL, for OAuth redirects
    stripe_secret_key: str
    stripe_webhook_secret: str
    resend_api_key: str
    email_from: str
    google_client_id: str
    google_client_secret: str
    token_key: str  # encrypts OAuth refresh tokens and signs OAuth state
    groq_api_key: str
    cron_secret: str

    @property
    def auth_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_secret_key)

    @property
    def billing_enabled(self) -> bool:
        return bool(self.stripe_secret_key and self.stripe_webhook_secret)

    @property
    def email_enabled(self) -> bool:
        return bool(self.resend_api_key)

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret and self.token_key)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    def features(self) -> dict[str, bool]:
        return {
            "billing": self.billing_enabled,
            "email": self.email_enabled,
            "google": self.google_enabled,
            "llm_drafting": self.llm_enabled,
        }


@lru_cache(maxsize=1)
def settings() -> Settings:
    load_dotenv()
    env = os.environ.get
    return Settings(
        supabase_url=env("SUPABASE_URL", ""),
        supabase_secret_key=env("SUPABASE_SECRET_KEY", ""),
        site_url=env("SITE_URL", "http://localhost:3000").rstrip("/"),
        api_url=env("API_URL", "http://localhost:8000").rstrip("/"),
        stripe_secret_key=env("STRIPE_SECRET_KEY", ""),
        stripe_webhook_secret=env("STRIPE_WEBHOOK_SECRET", ""),
        resend_api_key=env("RESEND_API_KEY", ""),
        email_from=env("EMAIL_FROM", "ShadowCost <onboarding@resend.dev>"),
        google_client_id=env("GOOGLE_CLIENT_ID", ""),
        google_client_secret=env("GOOGLE_CLIENT_SECRET", ""),
        token_key=env("TOKEN_ENCRYPTION_KEY", ""),
        groq_api_key=env("GROQ_API_KEY", "") or env("LLM_API_KEY", ""),
        cron_secret=env("CRON_SECRET", ""),
    )
