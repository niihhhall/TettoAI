"""Twilio -> Cloudflare R2 media streaming (PRD §3.2).

Fixes the 403 Forbidden trap: Twilio media URLs require HTTP Basic Auth, but they 302 to a
short-lived S3 URL that must be fetched WITHOUT the auth header (sending it triggers 403).
We therefore intercept the redirect and drop credentials on the follow-up request.
"""

from __future__ import annotations

import asyncio
import mimetypes
from urllib.parse import urlparse
from uuid import uuid4

import boto3
import httpx

from app.config import Settings

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def _host_allowed(url: str, allowed_hosts: list[str]) -> bool:
    """SSRF guard: the inbound media URL must be https and on an allowlisted Twilio host.

    A forged webhook could otherwise point MediaUrlN at an internal address and coerce the
    server into fetching it (and leaking the Twilio Basic-Auth header). The redirect target
    that Twilio returns is trusted because it originates from an allowlisted response.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    return any(host == a or host.endswith("." + a) for a in allowed_hosts)


class R2MediaStorage:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self.s = settings
        self.http = http
        self._s3 = boto3.client(
            "s3",
            endpoint_url=settings.R2_ENDPOINT_URL,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name="auto",
        )

    async def download_twilio_media(self, twilio_url: str, content_type: str | None) -> tuple[bytes, str]:
        """Auth the Twilio URL, then follow its redirect to S3 with NO auth header."""
        if not _host_allowed(twilio_url, self.s.twilio_media_hosts):
            raise ValueError(f"blocked media host: {urlparse(twilio_url).hostname!r}")
        resp = await self.http.get(
            twilio_url,
            auth=(self.s.TWILIO_ACCOUNT_SID or "", self.s.TWILIO_AUTH_TOKEN or ""),
            follow_redirects=False,
        )
        if resp.status_code in _REDIRECT_STATUSES and "location" in resp.headers:
            # Fresh request without Authorization — this is the 403 fix.
            resp = await self.http.get(resp.headers["location"], follow_redirects=True)
        resp.raise_for_status()
        ct = content_type or resp.headers.get("content-type", "application/octet-stream")
        return resp.content, ct

    async def download_meta_media(self, media_id: str, content_type: str | None) -> tuple[bytes, str]:
        """Resolve a Meta WhatsApp media ID to its short-lived CDN URL (Graph API), then
        download the bytes. Both requests carry the Meta bearer token; hosts are SSRF-
        allowlisted (graph.facebook.com + the lookaside media CDN)."""
        token = self.s.META_ACCESS_TOKEN or ""
        auth = {"Authorization": f"Bearer {token}"}
        graph_url = f"https://graph.facebook.com/{self.s.META_GRAPH_VERSION}/{media_id}"
        if not _host_allowed(graph_url, self.s.meta_media_hosts):
            raise ValueError("blocked meta graph host")
        meta = await self.http.get(graph_url, headers=auth)
        meta.raise_for_status()
        info = meta.json()
        url = info.get("url")
        ct = content_type or info.get("mime_type") or "application/octet-stream"
        if not url or not _host_allowed(url, self.s.meta_media_hosts):
            raise ValueError(f"blocked meta media url host: {urlparse(url or '').hostname!r}")
        resp = await self.http.get(url, headers=auth)
        resp.raise_for_status()
        return resp.content, ct

    def _public_url(self, key: str) -> str:
        if self.s.R2_PUBLIC_CUSTOM_DOMAIN:
            return f"https://{self.s.R2_PUBLIC_CUSTOM_DOMAIN}/{key}"
        return f"{self.s.R2_ENDPOINT_URL}/{self.s.R2_BUCKET_NAME}/{key}"

    @staticmethod
    def _key_for(content_type: str) -> str:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ""
        prefix = "audio" if content_type.startswith("audio") else "photos"
        return f"{prefix}/{uuid4().hex}{ext}"

    async def store_twilio_media(self, twilio_url: str, content_type: str) -> str:
        data, ct = await self.download_twilio_media(twilio_url, content_type)
        key = self._key_for(ct)
        return await self.upload_bytes(data, key, ct)

    async def upload_bytes(self, data: bytes, key: str, content_type: str) -> str:
        """Upload arbitrary bytes (e.g. a generated PDF) to R2 and return its public URL."""
        # boto3 is synchronous; run off the event loop.
        await asyncio.to_thread(
            self._s3.put_object,
            Bucket=self.s.R2_BUCKET_NAME, Key=key, Body=data, ContentType=content_type,
        )
        return self._public_url(key)
