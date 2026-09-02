# CodeVerity PDF Microservice (Modal.com)

Serverless PDF compiler (PRD §7). Renders the supplement request package with `fpdf2`,
uploads it to Cloudflare R2, and returns `{"pdf_url": ...}`.

## Layout
| File | Role |
|------|------|
| `renderer.py` | Pure `build_supplement_pdf(payload) -> bytes` (no Modal, unit-tested) |
| `pdf_service.py` | Modal app + R2 upload + `POST` web endpoint |

## Payload shape
```json
{
  "claim_number": "A-1029",
  "address": "1420 Elmwood Dr, Dallas, TX 75201",
  "building_code_citation": "Dallas §51A roofing ordinance",
  "line_items": [
    {"code": "RFG DRIP", "description": "Drip edge", "qty": 180, "unit": "LF"}
  ],
  "photos": ["https://cdn.codeverity.ai/photos/abc.jpg"]
}
```

## Setup & deploy
```bash
pip install modal
modal token new                      # one-time auth

# Create the R2 secret the service reads at runtime:
modal secret create codeverity-r2 \
  R2_ENDPOINT_URL=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... \
  R2_BUCKET_NAME=codeverity-media R2_PUBLIC_CUSTOM_DOMAIN=cdn.codeverity.ai

modal deploy modal_worker/pdf_service.py
```
The deploy prints the endpoint URL — set it as `MODAL_API_URL` in the backend `.env`.
The backend's `RealServices.compile_pdf` POSTs the payload there and reads `pdf_url`.
