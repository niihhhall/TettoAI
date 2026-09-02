"""Central configuration (PRD §8 env matrix).

All secrets come from environment variables / .env — never hard-coded. Values used only
in later phases are Optional so Phase 1 can boot with just DATABASE_URL.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Core (required from Phase 1) ---
    DATABASE_URL: str

    # --- Twilio WhatsApp (Phase 2) ---
    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: str | None = None
    TWILIO_WHATSAPP_FROM: str | None = None

    # --- Content template SIDs (Phase 2) ---
    CONTENT_SID_COMPANY_LIST: str | None = None
    CONTENT_SID_JOBSITE_LIST: str | None = None
    CONTENT_SID_LOCATION_CONFIRM: str | None = None
    CONTENT_SID_PHOTO_QA: str | None = None
    CONTENT_SID_VOICE_CONFIRM: str | None = None

    # --- Cloudflare R2 (Phase 3) ---
    R2_ENDPOINT_URL: str | None = None
    R2_ACCESS_KEY_ID: str | None = None
    R2_SECRET_ACCESS_KEY: str | None = None
    R2_BUCKET_NAME: str | None = None
    R2_PUBLIC_CUSTOM_DOMAIN: str | None = None

    # --- AI / geocoding (Phase 3) ---
    DEEPGRAM_API_KEY: str | None = None
    FIREWORKS_API_KEY: str | None = None
    # Fireworks model ID for line-item extraction. Swappable without code changes.
    FIREWORKS_MODEL: str = "accounts/fireworks/models/gpt-oss-120b"
    # Vision model for photo assessment / best-claim-photo selection (must be vision-capable).
    VISION_MODEL: str = "accounts/fireworks/models/glm-5p3-flash"
    MAPBOX_ACCESS_TOKEN: str | None = None

    # --- Messaging provider ---
    # "twilio" (default) or "meta" (WhatsApp Cloud API — free test number, up to 5 recipients).
    MESSAGING_PROVIDER: str = "twilio"

    # --- Meta WhatsApp Cloud API (used when MESSAGING_PROVIDER=meta) ---
    META_ACCESS_TOKEN: str | None = None      # Graph API token (24h temp, or a permanent system-user token)
    META_PHONE_NUMBER_ID: str | None = None   # the sender/test phone number ID
    META_WABA_ID: str | None = None           # WhatsApp Business Account ID (optional)
    META_VERIFY_TOKEN: str | None = None      # your chosen string for the webhook GET handshake
    META_APP_SECRET: str | None = None        # app secret for X-Hub-Signature-256 (optional but recommended)
    META_GRAPH_VERSION: str = "v22.0"
    # Allowed hosts for Meta media fetches (SSRF guard): Graph API + the media CDN.
    META_MEDIA_HOSTS: str = "graph.facebook.com,lookaside.fbsbx.com"

    # --- Photo QA thresholds (State 3). Tunable without code changes; WhatsApp recompresses
    # photos, so these are deliberately lenient — a real photo should never be rejected just
    # for being a phone/WhatsApp capture. Raise them if too many bad photos slip through. ---
    PHOTO_BLUR_MIN: float = 12.0     # variance-of-Laplacian floor (clamped Pillow scale)
    PHOTO_DARK_MAX: float = 20.0     # mean luminance below this = too dark
    PHOTO_BRIGHT_MIN: float = 245.0  # mean luminance above this = blown out
    PHOTO_DUP_HAMMING: int = 5       # dHash distance <= this = duplicate

    # Lean messaging: don't send a WhatsApp reply for every good photo, and skip the
    # mid-photo "still sending?" nudge. Per-photo evidence (caption/damage/voice) is STILL
    # captured and shown in the console/PDF/CRM — we just stop chatting to the foreman on
    # each photo. Cuts a 4-photo run from ~12 outbound messages to ~7, which matters on the
    # Twilio trial cap (50 messages / rolling 24h). Set to false for the chatty per-photo UX.
    WHATSAPP_LEAN_MODE: bool = True

    # --- Modal PDF microservice (Phase 4) ---
    MODAL_API_URL: str | None = None

    # --- Security ---
    # Secret for signing operator session JWTs. Required in production.
    JWT_SECRET: str | None = None
    JWT_TTL_MINUTES: int = 720  # 12h operator sessions
    # Verify X-Twilio-Signature on the webhook whenever an auth token is present.
    TWILIO_WEBHOOK_VALIDATE: bool = True
    # Public URL Twilio signs against (e.g. https://api.codeverity.ai). Set this behind a
    # proxy (Heroku/Railway) where the internal scheme/host differ from the public one;
    # otherwise the raw request URL is used.
    PUBLIC_BASE_URL: str | None = None
    # Allowed hosts for server-side media fetches (SSRF guard). Comma-separated suffixes.
    TWILIO_MEDIA_HOSTS: str = "api.twilio.com,media.twiliocdn.com,mcs.us1.twilio.com"

    # --- Runtime ---
    ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    DB_POOL_MIN_SIZE: int = 1
    DB_POOL_MAX_SIZE: int = 10
    # Comma-separated allowed origins for CORS. Default "*" for dev; set the Vercel
    # domain(s) in production.
    CORS_ORIGINS: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def twilio_media_hosts(self) -> list[str]:
        return [h.strip().lower() for h in self.TWILIO_MEDIA_HOSTS.split(",") if h.strip()]

    @property
    def meta_media_hosts(self) -> list[str]:
        return [h.strip().lower() for h in self.META_MEDIA_HOSTS.split(",") if h.strip()]

    @property
    def use_meta(self) -> bool:
        return self.MESSAGING_PROVIDER.strip().lower() == "meta"

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
