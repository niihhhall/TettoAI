import React, { useState } from 'react'
import { Icon } from '@iconify/react'
import { login } from '../../lib/api'

interface LoginScreenProps {
    onSuccess: () => void
}

export const LoginScreen: React.FC<LoginScreenProps> = ({ onSuccess }) => {
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [error, setError] = useState<string | null>(null)
    const [submitting, setSubmitting] = useState(false)

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setError(null)
        setSubmitting(true)
        try {
            const result = await login(email.trim(), password)
            if (result.ok) {
                onSuccess()
            } else {
                setError(result.error ?? 'Login failed')
            }
        } catch {
            setError('Cannot reach the server. Check your connection and try again.')
        } finally {
            setSubmitting(false)
        }
    }

    return (
        <div className="min-h-screen bg-bg-base flex items-center justify-center p-6">
            <div className="w-full max-w-md space-y-8 animate-in fade-in zoom-in duration-700">
                <div className="text-center space-y-5">
                    <div className="mx-auto w-14 h-14 rounded-2xl overflow-hidden shadow-lift">
                        <img src="/logo.jpg" alt="CodeVerity logo" className="w-full h-full object-cover" />
                    </div>
                    <h1 className="text-3xl font-bold text-ink tracking-tight">
                        Code<span className="text-brand">Verity</span>
                    </h1>
                    <p className="text-sm text-ink-muted">Sign in to the operator console</p>
                </div>

                <div className="card p-8 relative overflow-hidden">
                    <form onSubmit={handleSubmit} className="space-y-6 relative z-10">
                        <div className="space-y-2">
                            <label htmlFor="op-email" className="block text-xs font-semibold text-ink-soft pl-1">Email</label>
                            <input
                                id="op-email"
                                type="email"
                                autoComplete="username"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                placeholder="operator@company.com"
                                className="input-modern w-full"
                                required
                            />
                        </div>
                        <div className="space-y-2">
                            <label htmlFor="op-password" className="block text-xs font-semibold text-ink-soft pl-1">Password</label>
                            <input
                                id="op-password"
                                type="password"
                                autoComplete="current-password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="Your password"
                                className="input-modern w-full"
                                required
                            />
                        </div>

                        {error && (
                            <p role="alert" className="text-sm text-red-600 flex items-center gap-2">
                                <Icon icon="solar:danger-triangle-linear" width={16} />
                                {error}
                            </p>
                        )}

                        <button
                            type="submit"
                            disabled={submitting}
                            className="btn-premium w-full flex items-center justify-center gap-2 group/btn disabled:opacity-60"
                        >
                            {submitting ? 'Signing in…' : (
                                <>Sign in <Icon icon="solar:arrow-right-linear" width={18} className="group-hover/btn:translate-x-1 transition-transform" /></>
                            )}
                        </button>
                    </form>
                </div>

                <div className="flex items-center justify-center gap-6 text-[11px] text-ink-faint pt-4 font-medium">
                    <div className="flex items-center gap-2">
                        <Icon icon="solar:shield-check-linear" width={16} /> Secure session
                    </div>
                    <div className="w-1 h-1 rounded-full bg-gray-300"></div>
                    <div>CodeVerity</div>
                </div>
            </div>
        </div>
    )
}
