"""CodeVerity PDF microservice on Modal.com (PRD §7).

Exposes an HTTP POST endpoint that renders a supplement PDF, uploads it to Cloudflare R2,
and returns {"pdf_url": ...} — which the FastAPI backend's RealServices.compile_pdf calls.

Deploy:
    modal deploy modal_worker/pdf_service.py
The printed URL goes into the backend's MODAL_API_URL env var.

R2 credentials are injected via a Modal Secret named "codeverity-r2" containing:
    R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
    R2_BUCKET_NAME, R2_PUBLIC_CUSTOM_DOMAIN
"""

from __future__ import annotations

import os

import modal

from renderer import build_supplement_pdf  # bundled via add_local_python_source below

app = modal.App("codeverity-pdf-service")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fpdf2==2.8.2", "boto3==1.35.90")
    .add_local_python_source("renderer")
)

r2_secret = modal.Secret.from_name("codeverity-r2")


def _upload_pdf_to_r2(pdf_bytes: bytes, key: str) -> str:
    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    s3.put_object(
        Bucket=os.environ["R2_BUCKET_NAME"],
        Key=key,
        Body=pdf_bytes,
        ContentType="application/pdf",
    )
    domain = os.environ.get("R2_PUBLIC_CUSTOM_DOMAIN")
    if domain:
        return f"https://{domain}/{key}"
    return f"{os.environ['R2_ENDPOINT_URL']}/{os.environ['R2_BUCKET_NAME']}/{key}"


@app.function(image=image, secrets=[r2_secret], timeout=60)
@modal.fastapi_endpoint(method="POST")
def generate_supplement_pdf(payload: dict) -> dict:
    """Render + upload. Returns {"pdf_url": "<public R2 url>"}."""
    claim = str(payload.get("claim_number", "UNKNOWN")).replace("/", "-").replace(" ", "_")
    pdf_bytes = build_supplement_pdf(payload)
    key = f"pdf/{claim}.pdf"
    url = _upload_pdf_to_r2(pdf_bytes, key)
    return {"pdf_url": url}
