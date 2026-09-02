import type { Inspection, CrewRow, Jobsite, Company } from '../types'
import { authHeaders, getToken, logout, setSession, type OperatorProfile } from './auth'

// Established convention in this codebase: VITE_API_URL with a localhost:8000 dev fallback.
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// WebSocket base: explicit VITE_WS_URL, else derive from API_URL (http->ws, https->wss).
export const WS_URL =
    (import.meta.env.VITE_WS_URL as string | undefined) ||
    `${API_URL.replace(/^http/, 'ws')}/api/v1/ws/inspections`

/** The operator WS URL with the session token attached (browsers can't set WS headers). */
export function inspectionsWsUrl(): string {
    const token = getToken()
    if (!token) return WS_URL
    const sep = WS_URL.includes('?') ? '&' : '?'
    return `${WS_URL}${sep}token=${encodeURIComponent(token)}`
}

/** Expired/invalid session — clear it and bounce to login. */
function onUnauthorized(): void {
    logout()
    window.location.reload()
}

async function authedGet(path: string): Promise<Response> {
    const res = await fetch(`${API_URL}${path}`, { headers: { ...authHeaders() } })
    if (res.status === 401) onUnauthorized()
    return res
}

export interface LoginResult {
    ok: boolean
    error?: string
}

export async function login(email: string, password: string): Promise<LoginResult> {
    const res = await fetch(`${API_URL}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
    })
    if (!res.ok) {
        return { ok: false, error: res.status === 401 ? 'Invalid email or password' : 'Login failed' }
    }
    const data = await res.json()
    setSession(data.token as string, data.operator as OperatorProfile)
    return { ok: true }
}

export async function fetchInspections(limit = 50): Promise<Inspection[]> {
    const res = await authedGet(`/api/v1/inspections?limit=${limit}`)
    if (!res.ok) throw new Error('Failed to fetch inspections')
    const data = await res.json()
    return data.inspections ?? []
}

export async function fetchCrew(): Promise<CrewRow[]> {
    const res = await authedGet('/api/v1/crew')
    if (!res.ok) throw new Error('Failed to fetch crew')
    const data = await res.json()
    return data.crew ?? []
}

export interface ApproveResult {
    ok: boolean
    crm_status?: string
    credited?: boolean
    bounty_status?: string
    error?: string
}

export async function approveInspection(sessionId: string): Promise<ApproveResult> {
    const res = await fetch(`${API_URL}/api/v1/inspections/${sessionId}/approve`, {
        method: 'POST',
        headers: { ...authHeaders() },
    })
    if (res.status === 401) {
        onUnauthorized()
        return { ok: false }
    }
    if (!res.ok) return { ok: false }
    return res.json()
}

export async function deleteInspection(sessionId: string): Promise<{ ok: boolean }> {
    const res = await fetch(`${API_URL}/api/v1/inspections/${sessionId}`, {
        method: 'DELETE',
        headers: { ...authHeaders() },
    })
    if (res.status === 401) {
        onUnauthorized()
        return { ok: false }
    }
    if (!res.ok) return { ok: false }
    return res.json()
}

export async function registerCrew(
    fullName: string,
    phoneNumber: string,
    companyCode: string,
): Promise<{ ok: boolean; error?: string }> {
    const res = await fetch(`${API_URL}/api/v1/crew`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ full_name: fullName, phone_number: phoneNumber, company_code: companyCode }),
    })
    if (res.status === 401) {
        onUnauthorized()
        return { ok: false, error: 'Session expired' }
    }
    return res.json()
}

/** Shared POST/PATCH helper for authed JSON writes with 401 handling. */
async function authedWrite(path: string, method: 'POST' | 'PATCH', body: unknown): Promise<Response | null> {
    const res = await fetch(`${API_URL}${path}`, {
        method,
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(body),
    })
    if (res.status === 401) {
        onUnauthorized()
        return null
    }
    return res
}

// --- Jobsites ---

export interface JobsiteInput {
    property_address: string
    claim_number?: string
    city?: string
    state?: string
    zip_code?: string
    county?: string
    municipal_code_summary?: string
}

export async function fetchJobsites(): Promise<Jobsite[]> {
    const res = await authedGet('/api/v1/jobsites')
    if (!res.ok) throw new Error('Failed to fetch jobsites')
    return (await res.json()).jobsites ?? []
}

export async function createJobsite(body: JobsiteInput): Promise<{ ok: boolean; error?: string; job_id?: string }> {
    const res = await authedWrite('/api/v1/jobsites', 'POST', body)
    return res ? res.json() : { ok: false, error: 'Session expired' }
}

export async function updateJobsite(jobId: string, body: Partial<JobsiteInput>): Promise<{ ok: boolean; error?: string }> {
    const res = await authedWrite(`/api/v1/jobsites/${jobId}`, 'PATCH', body)
    return res ? res.json() : { ok: false, error: 'Session expired' }
}

// --- Companies / branches ---

export interface CompanyInput {
    company_name: string
    invite_code: string
    crm_type?: string
    crm_webhook_url?: string
}

export async function fetchCompanies(): Promise<Company[]> {
    const res = await authedGet('/api/v1/companies')
    if (!res.ok) throw new Error('Failed to fetch companies')
    return (await res.json()).companies ?? []
}

export async function createCompany(body: CompanyInput): Promise<{ ok: boolean; error?: string; company_id?: string }> {
    const res = await authedWrite('/api/v1/companies', 'POST', body)
    return res ? res.json() : { ok: false, error: 'Session expired' }
}

export async function updateCompany(companyId: string, body: Partial<CompanyInput>): Promise<{ ok: boolean; error?: string }> {
    const res = await authedWrite(`/api/v1/companies/${companyId}`, 'PATCH', body)
    return res ? res.json() : { ok: false, error: 'Session expired' }
}
