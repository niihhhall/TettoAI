# CodeVerity Field & Operator System — Production-Grade Master PRD (v2.0)

**Document Version:** 3.0 (Hardened Production & Kiro IDE Build Blueprint with GitHub Integration)  
**Target Platform:** Kiro IDE Full-Stack Code Generation  
**Production Stack:** React + Vite (Frontend) | FastAPI + Python 3.12 (Backend) | Neon Postgres (Database) | Cloudflare R2 (Media Storage) | Deepgram Nova-2 (STT) | Fireworks.ai Llama-3.3-70B (LLM) | Modal.com (PDF Microservice) | Twilio (WhatsApp API)  
**Hosting Architecture:** Vercel (Frontend) | Heroku / Railway (FastAPI Backend)  

---

## 1. Executive Summary & Core Identity

CodeVerity is an autonomous **Field Intake & Supplement Orchestration Infrastructure** built for US residential storm restoration roofing contractors. It bridge the high-friction gap between 1099 roof foremen in the field and office estimators at their desks.

### Core Operating Principles
1. **Zero-Friction Field Intake:** Foremen on steep roofs interact exclusively through **WhatsApp Quick Reply Buttons**, **Interactive Lists**, **Native GPS Pins**, and **Voice Notes**. Zero manual text typing is required.
2. **Database-First Identity:** Incoming WhatsApp Caller IDs (`+E.164`) are queried against Neon Postgres before LLM prompt execution. Identity is injected deterministically into system prompts to eliminate AI context memory loss.
3. **Decoupled Async Processing:** The backend acknowledges Twilio webhooks in under 50ms with a `200 OK` response while executing media ingestion, speech-to-text, and LLM extraction asynchronously in background workers, eliminating 15-second webhook timeouts.
4. **Three-Point Code Triangulation:** Every supplement line item is justified using a triple-proof model: **Geo-tagged Photo Proof + City Municipal Building Ordinance Citation + Manufacturer Warranty Specs**.
5. **Subcontractor Crew Alignment:** 1099 foremen receive a **$25 cash bounty** for every approved supplement package generated from their field submissions.

---

## 2. Hardened System Architecture & Tech Stack

```
                                  [FIELD CREW (WhatsApp)]
                                             │
                                             ▼
                                  [Twilio WhatsApp Gateway]
                                             │
                        (POST Webhook - <50ms TwiML Response)
                                             │
                                             ▼
                                  [FastAPI Backend Server]
                                    (Heroku / Railway)
                                             │
      ┌───────────────────┬──────────────────┴───────────────────┬───────────────────┐
      ▼                   ▼                                      ▼                   ▼
[Neon Postgres]   [Cloudflare R2]                          [Deepgram STT]     [Fireworks.ai]
(Identity & DB)   (Public CDN Bucket)                      (Nova-2 Engine)    (Llama-3.3-70B)
      │                   │                                      │                   │
      └───────────────────┼──────────────────────────────────────┴───────────────────┘
                          │
                          ▼
               [Modal.com PDF Worker]
             (Serverless PDF Compiler)
                          │
                          ▼
            [Operator Console Dashboard]
              (Vercel / Next.js/Vite)
```

### Complete Component Stack
* **Development Environment:** Kiro IDE
* **Frontend Web App:** React 19 + TypeScript + Vite + Tailwind CSS (`markeye-agenticui` codebase (https://github.com/niihhhall/markeye-agenticui) deployed on Vercel)
* **Backend API Gateway:** Python 3.12 + FastAPI + Uvicorn + Pydantic v2 (Deployed on Heroku / Railway)
* **Primary Database:** Neon Serverless Postgres (`asyncpg` connection pooling)
* **Media & File Storage:** Cloudflare R2 (S3-compatible bucket for public image/audio hosting)
* **Speech-to-Text Engine:** Deepgram Nova-2 API (`en` trade vocabulary prompts)
* **LLM Extraction Engine:** Fireworks.ai (`accounts/fireworks/models/llama-v3p3-70b-instruct` via `instructor`)
* **Async PDF Microservice:** Modal.com Python Container (`fpdf2` rendering)
* **WhatsApp Channel API:** Twilio Programmable Messaging API

---

## 3. Production Steel-Man Engineering Specifications

### 3.1 Decoupled Async Ingestion (Fixing Twilio 15s Timeout)
All incoming Twilio webhooks MUST return an immediate HTTP `200 OK` with empty TwiML `<Response/>` within 50ms. Heavy media downloads, Deepgram STT calls, and Fireworks.ai inference run strictly inside `FastAPI.BackgroundTasks`.

### 3.2 Twilio-to-R2 Media Streaming (Fixing 403 Forbidden Errors)
Twilio media URLs require HTTP Basic Authentication. The background worker streams image/audio bytes directly from Twilio into a Cloudflare R2 public bucket before passing URLs to Neon DB or Modal.com.

### 3.3 WebSocket Keep-Alive & Auto-Reconnect (Fixing Heroku Router Drops)
Heroku routers terminate idle WebSockets after 55 seconds. FastAPI emits `{"type": "ping"}` frames every 30 seconds. The React dashboard implements an exponential backoff auto-reconnect hook.

### 3.4 Strict Pydantic Schema Enforcement (Fixing Unstructured LLM Crashes)
Fireworks.ai responses are wrapped with `instructor` and Pydantic schemas. Any parse failure triggers a single-retry fallback, ensuring malformed JSON never causes `500 Internal Server Errors`.

### 3.5 Dual-Layer Geofence Matching (Fixing Invalid City Ordinance Claims)
Reverse geocoding resolves both `locality` (incorporated city) and `administrative_area_level_2` (county) to prevent citing city ordinances on properties located in unincorporated county jurisdictions.

---

## 4. Neon Postgres Database DDL Schemas

```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Contractor Company Accounts
CREATE TABLE companies (
    company_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name VARCHAR(255) NOT NULL,
    invite_code VARCHAR(50) UNIQUE NOT NULL, -- e.g., '4821' or 'APEX'
    crm_type VARCHAR(50) DEFAULT 'JobNimbus',
    crm_webhook_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Crew Members (Foremen / Subcontractors)
CREATE TABLE crew_members (
    crew_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(company_id) ON DELETE CASCADE,
    phone_number VARCHAR(20) UNIQUE NOT NULL, -- E.164 format (+12145550199)
    full_name VARCHAR(255) NOT NULL,
    preferred_language VARCHAR(5) DEFAULT 'en',
    role VARCHAR(50) DEFAULT 'Foreman',
    total_bounties_earned DECIMAL(10,2) DEFAULT 0.00,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for instant phone number authentication lookup (<5ms)
CREATE INDEX idx_crew_members_phone ON crew_members(phone_number);

-- 3. Jobsites
CREATE TABLE jobsites (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(company_id) ON DELETE CASCADE,
    claim_number VARCHAR(100),
    property_address TEXT NOT NULL,
    zip_code VARCHAR(10) NOT NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(2) NOT NULL,
    municipal_code_summary TEXT, -- Pre-fetched city building codes
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Inspection Sessions (State Machine)
CREATE TABLE inspection_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crew_id UUID REFERENCES crew_members(crew_id) ON DELETE CASCADE,
    job_id UUID REFERENCES jobsites(job_id) ON DELETE SET NULL,
    current_state VARCHAR(50) DEFAULT 'STATE_0_AUTH',
    approved_photos JSONB DEFAULT '[]'::jsonb, -- Array of Cloudflare R2 public URLs
    voice_note_url TEXT,
    transcription_text TEXT,
    structured_line_items JSONB DEFAULT '[]'::jsonb, -- Xactimate line items
    pdf_url TEXT,
    bounty_status VARCHAR(20) DEFAULT 'PENDING', -- PENDING, APPROVED, PAID
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

## 5. End-to-End User Flow & UI Buttons Catalog

```
[ENTRY POINT: QR Code / Truck Sticker / Outbound Link]
                           │
                           ▼
[STATE 0: IDENTITY & DATABASE AUTHENTICATION]
 Query Caller ID against Database
 ├── User Exists ──────► Load Crew Profile & Company Account ID
 └── Unrecognized ────► Trigger State 0.5: Conversational Onboarding / Enter Company Code
                           │
                           ▼
[STATE 1: JOBSITE SELECTION & LOCK]
 Interactive List: Nearby Assigned Jobs or [➕ New Jobsite]
                           │
                           ▼
[STATE 2: LOCATION & MUNICIPAL ORDINANCE LOCK]
 Native Location Pin or Photo ──► Reverse Geocode Address ──► Fetch City Building Code
                           │
                           ▼
[STATE 3: BULK PHOTO DUMP & VISION AI QA]
 Upload 3-8 Photos ──► Vision AI Checks Exposure/Blur/Duplicates & Stream to R2
 ├── Photo Fails QA ──► Quick Reply: "Photo #3 blurry due to glare. Tap to retake."
 └── Photos Approved ─► Evidence Shots Locked & Geo-stamped
                           │
                           ▼
[STATE 4: ENGLISH VOICE NOTE & SCOPE STRUCTURING]
 Record English Voice Note ──► Deepgram STT ──► Fireworks.ai Pydantic Extraction
                           │
                           ▼
[STATE 5: PACKAGE CONFIRMATION & CREW BOUNTY LOCK]
 Review Scope Summary ──► Tap [✅ Submit Package] ──► Lock $25 Crew Bounty
                           │
                           ▼
[STATE 6: PDF COMPILATION & DESK-SIDE CRM DISPATCH]
 Modal.com Compiles PDF ──► Webhook Push to JobNimbus / AccuLynx / Slack
```

### Conversational UI Script (English)

#### State 0.5: Unregistered Worker Onboarding
* **System Message:**  
  > 🛠️ **CodeVerity Field Intake System**  
  > Welcome! I am the automated Field Intake System. I don't recognize this phone number yet.  
  > Please reply with your **Full Name**:
* **Worker Input:** `"Marcus Johnson"`
* **System Interactive List Message:**  
  * **Header:** `Select Your Company`  
  * **Body:** `Choose your contractor or tap below to enter your company code:`  
  * **Button:** `[ View Options ]`  
  * **List Options:**  
    1. `Apex Roofing (Code: 4821)`  
    2. `Titan Storm Restoration`  
    3. `🔑 Enter Company Code`  
* **Worker Action:** Taps `🔑 Enter Company Code` and replies `"4821"` (or `"APEX"`).  
* **System Confirmation:**  
  > *"Code verified! You are linked to **Apex Roofing**. Let's get started."*

#### State 2: Location Lock
* **System Message:**  
  > 📍 **Location Confirmation**  
  > Please tap the attachment icon (📎) and send your **Current Location (GPS Pin)**, or snap a photo of the front of the house.
* **Worker Action:** Taps `📎 Location -> Send Current Location`.
* **Quick Reply Buttons:**  
  `[ ✅ Confirm Address ]` | `[ ✏️ Edit Address ]` | `[ 📍 Resend GPS ]`

#### State 3: Photo Quality Control
* **Quick Reply Buttons:**  
  `[ 📷 Retake Photo #3 ]` | `[ ➕ Add More Photos ]` | `[ ➡️ Skip to Voice ]`

#### State 4: Voice Note Confirmation
* **Quick Reply Buttons:**  
  `[ ✅ Submit Package ]` | `[ 🎙️ Re-record Voice ]` | `[ ✏️ Add Note ]`

---

## 6. Frontend Operator Console Specifications (`markeye-agenticui`)

**GitHub Repository Link:** https://github.com/niihhhall/markeye-agenticui

The frontend React 19 application is structured around four primary core views:

### 1. Live Feed View (`src/pages/Conversations.tsx`)
* **Realtime Socket:** Connects to `ws://backend-domain/api/v1/ws/inspections`.
* **Feed Card Items:** Shows worker name, job address, timestamp, photo gallery grid, Deepgram audio player, and transcribed scope.
* **Action:** Tapping any card opens the slide-over `InspectionDrawer.tsx`.

### 2. PDF Preview & 1-Click Code Drawer (`src/components/InspectionDrawer.tsx`)
* **PDF Viewer:** `<iframe>` displaying the Modal.com generated Supplement PDF.
* **1-Click Xactimate Copy Buttons:**
  * `[ Copy RFG DRIP ]` \(\rightarrow\) Copies `"RFG DRIP - Drip edge - 180 LF"` to clipboard.
  * `[ Copy RFG SHTHN ]` \(\rightarrow\) Copies `"RFG SHTHN - OSB Sheathing 1/2" - 64 SF"` to clipboard.
  * `[ Copy RFG IWS ]` \(\rightarrow\) Copies `"RFG IWS - Ice & Water Shield - 2 SQ"` to clipboard.
* **CRM Dispatch Action:** `[ ✅ Approve & Push to CRM ]` triggers outbound webhook to JobNimbus.

### 3. Claims Master Table (`src/pages/Leads.tsx`)
* **Table Columns:** `Property Address`, `Claim #`, `Assigned Foreman`, `City Building Code`, `Supplement Value ($)`, `Status`.

### 4. Crew Manager (`src/pages/Instances.tsx`)
* **Features:** Displays active **Company Code** (`4821`), pre-registration phone entry form, and foreman bounty ledger ($25 per approved claim).
### 5. Export Actions & Data Portability
The UI provides three dedicated export functions:
* **PDF Export:** `[ 📥 Download PDF Report ]` button in `InspectionDrawer.tsx` to download the compiled 1-page Supplement Request PDF.
* **Claims Data Export:** `[ 📊 Export Claims CSV / Excel ]` button on `Leads.tsx` to export all property addresses, claim numbers, code citations, and supplement dollar values for accounting and CRM backup.
* **Crew Bounty Export:** `[ 💳 Export Bounty Payout CSV ]` button on `Instances.tsx` to export foreman $25 bounty balances for direct payroll processing.

* **Features:** Displays active **Company Code** (`4821`), pre-registration phone entry form, and foreman bounty ledger ($25 per approved claim).

---

## 7. Modal.com PDF Microservice Architecture

```python
# modal_worker/pdf_service.py
import modal
from fpdf import FPDF

app = modal.App("codeverity-pdf-service")
image = modal.Image.debian_slim().pip_install("fpdf2", "httpx", "boto3")

@app.function(image=image, timeout=60)
def generate_supplement_pdf(payload: dict) -> str:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    
    # Title Header
    pdf.cell(0, 10, "SUPPLEMENT REQUEST PACKAGE", ln=True, align="C")
    pdf.ln(5)
    
    # Property & Code Justification Section
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, f"Property Address: {payload['address']}", ln=True)
    pdf.cell(0, 8, f"Claim Number: {payload['claim_number']}", ln=True)
    pdf.cell(0, 8, f"Municipal Ordinance: {payload['building_code_citation']}", ln=True)
    pdf.ln(5)
    
    # Line Items Table
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Xactimate Line Items Required:", ln=True)
    pdf.set_font("Arial", "", 10)
    for item in payload['line_items']:
        pdf.cell(0, 6, f"• [{item['code']}] {item['description']} - Qty: {item['qty']} {item['unit']}", ln=True)
        
    # Render PDF to bytes
    pdf_bytes = pdf.output(dest='S')
    
    # Upload to Cloudflare R2 and return URL
    pdf_url = upload_pdf_bytes_to_r2(pdf_bytes, f"pdf/{payload['claim_number']}.pdf")
    return pdf_url
```

---

## 8. Heroku / Railway Deployment Configuration

### 1. `Procfile`
```text
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2
```

### 2. `runtime.txt`
```text
python-3.12.2
```

### 3. Environment Variables Configuration Matrix
```env
DATABASE_URL="postgresql://user:pass@ep-cool-site-123.us-east-2.aws.neon.tech/main?sslmode=require"
FIREWORKS_API_KEY="fw_3Z..."
DEEPGRAM_API_KEY="dg_7A..."
TWILIO_ACCOUNT_SID="AC..."
TWILIO_AUTH_TOKEN="a1..."
MAPBOX_ACCESS_TOKEN="pk..."
R2_ENDPOINT_URL="https://<account_id>.r2.cloudflarestorage.com"
R2_ACCESS_KEY_ID="r2_key_..."
R2_SECRET_ACCESS_KEY="r2_secret_..."
R2_BUCKET_NAME="codeverity-media"
R2_PUBLIC_CUSTOM_DOMAIN="cdn.codeverity.ai"
MODAL_API_URL="https://your-app.modal.run"
```

---

## 9. Kiro IDE Engineering Prompt Roadmap

### Step 0: Repository Setup
> *"Kiro, clone or reference our frontend repository at https://github.com/niihhhall/markeye-agenticui into the `/frontend` directory as the base React 19 + Vite + Tailwind dashboard."*

Follow this exact prompt sequence inside Kiro IDE to build the codebase from scratch:

### Step 1: Database DDL Execution
> *"Kiro, read Section 4 of `kiro-master-prd-v2.md` and generate a Python script using `asyncpg` that connects to `DATABASE_URL` and executes the DDL schema to create `companies`, `crew_members`, `jobsites`, and `inspection_sessions` tables in Neon Postgres."*

### Step 2: FastAPI Webhook & State Machine Construction
> *"Kiro, build a Python FastAPI application in `/backend` implementing the Twilio webhook handler (`POST /api/v1/whatsapp/webhook`) using `BackgroundTasks` as specified in Section 3.1 and Section 5. Create state handlers for States 0 through 6."*

### Step 3: Audio, R2 & AI Integrations
> *"Kiro, build backend services for: 1) Streaming Twilio media to Cloudflare R2 (`app/services/media_storage.py`), 2) Transcribing audio notes with Deepgram Nova-2 (`app/services/speech.py`), and 3) Extracting Xactimate line items using Fireworks.ai and `instructor` Pydantic models (`app/services/code_extractor.py`)."*

### Step 4: Frontend Dashboard Integration
> *"Kiro, connect `Conversations.tsx` in `/frontend` to the FastAPI WebSocket endpoint with auto-reconnect logic. Create `InspectionDrawer.tsx` with a PDF iframe preview and 1-click Xactimate copy buttons. Update `Leads.tsx` as our Claims Table and `Instances.tsx` as our Crew Manager."*

---
