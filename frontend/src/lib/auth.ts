// Operator session: JWT + operator profile in localStorage. Pure storage/header helpers —
// no imports from api.ts (avoids a cycle; api.ts imports from here).

const TOKEN_KEY = 'codeverity_token'
const OPERATOR_KEY = 'codeverity_operator'

export interface OperatorProfile {
    email: string
    company_id: string
    company_name: string | null
    role: string
}

export function getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY)
}

export function getOperator(): OperatorProfile | null {
    const raw = localStorage.getItem(OPERATOR_KEY)
    return raw ? (JSON.parse(raw) as OperatorProfile) : null
}

export function isAuthenticated(): boolean {
    return Boolean(getToken())
}

export function setSession(token: string, operator: OperatorProfile): void {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(OPERATOR_KEY, JSON.stringify(operator))
}

export function logout(): void {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(OPERATOR_KEY)
}

export function authHeaders(): Record<string, string> {
    const token = getToken()
    return token ? { Authorization: `Bearer ${token}` } : {}
}
