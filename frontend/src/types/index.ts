export interface Lead {
    id: string
    first_name: string
    last_name: string
    email: string
    phone: string
    company: string
    industry: string
    lead_source: 'Google' | 'Meta' | 'Referral' | 'Other'
    form_message: string
    temperature: 'Cold' | 'Warm' | 'Hot'
    outcome: 'In Progress' | 'Not Interested' | 'Disqualified' | 'Meeting Booked'
    signal_score: number
    created_at: string
    updated_at: string
}

export interface Message {
    id: string
    lead_id: string
    direction: 'inbound' | 'outbound'
    content: string
    created_at: string
    leads?: Partial<Lead>
}

export interface ConversationState {
    id: string
    lead_id: string
    current_state: 'Opening' | 'Discovery' | 'Qualification' | 'Intent Building' | 'Booking Push' | 'Awaiting' | 'Confirmed' | 'Escalation'
    bant_budget: string | null
    bant_authority: string | null
    bant_need: string | null
    bant_timeline: string | null
    message_count: number
    is_typing?: boolean
    last_active_at: string
    updated_at: string
}

export interface Booking {
    id: string
    lead_id: string
    calendly_event_id: string
    scheduled_at: string
    status: 'confirmed' | 'cancelled' | 'pending'
    created_at: string
    leads?: Partial<Lead>
}

export interface LLMSession {
    id: string
    lead_id: string | null
    helicone_id: string
    model: string
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    cost_usd: number
    latency_ms: number
    conversation_state: string
    created_at: string
}

export type ConversationStateName = ConversationState['current_state']

export interface Client {
    id: string
    business_name: string
    whatsapp_number: string
    api_key: string
    is_active: boolean
    sales_contact: string | null
    created_at: string
}

export interface BaileysSession {
    sessionId: string
    status: 'connected' | 'pairing' | 'offline' | 'connecting'
    qr?: string
    error?: string
}

/* ===================== CodeVerity domain ===================== */

export interface InspectionLineItem {
    code: string
    description: string
    qty: number
    unit: string
    photo_urls?: string[]
}

export interface PhotoEvidence {
    url: string
    caption?: string | null
    damage_types?: string[]
    supports_codes?: string[]
    quality?: string | null
    claim_relevance?: number | null
    voice_note_url?: string | null
    transcript?: string | null
}

export interface Inspection {
    session_id: string
    company_id: string | null
    crew_name: string | null
    company_name: string | null
    address: string | null
    city: string | null
    claim_number: string | null
    building_code: string | null
    photos: string[]
    photo_evidence?: PhotoEvidence[]
    transcription: string | null
    voice_note_url: string | null
    line_items: InspectionLineItem[]
    pdf_url: string | null
    bounty_status: string
    crm_status: string | null
    supplement_value: number | null
    current_state: string
    created_at: string | null
}

export interface CrewRow {
    crew_id: string
    full_name: string
    phone_number: string
    role: string
    company_name: string | null
    company_code: string | null
    total_bounties_earned: number
}

export interface Jobsite {
    job_id: string
    company_id: string
    property_address: string
    claim_number: string | null
    city: string | null
    state: string | null
    zip_code: string | null
    county: string | null
    municipal_code_summary: string | null
}

export interface Company {
    company_id: string
    company_name: string
    invite_code: string
    crm_type: string | null
    crm_webhook_url: string | null
}
