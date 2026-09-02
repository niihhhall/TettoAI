import React, { useMemo, useState } from 'react'
import { Icon } from '@iconify/react'
import { useCrew } from '../hooks/useCrew'
import { StatCard } from '../components/ui/StatCard'
import { downloadCsv, toCsv } from '../lib/csv'

const Instances: React.FC = () => {
    const { crew, isLoading, register } = useCrew()

    const [fullName, setFullName] = useState('')
    const [phone, setPhone] = useState('')
    const [companyCode, setCompanyCode] = useState('')
    const [submitting, setSubmitting] = useState(false)
    const [feedback, setFeedback] = useState<{ ok: boolean; msg: string } | null>(null)

    const stats = useMemo(() => {
        const totalBounties = crew.reduce((sum, c) => sum + (c.total_bounties_earned || 0), 0)
        const companies = new Set(crew.map(c => c.company_code).filter(Boolean))
        return [
            { label: 'Foremen', value: crew.length, icon: 'solar:users-group-rounded-linear', color: 'bg-brand-muted text-brand' },
            { label: 'Bounties Paid', value: `$${totalBounties.toFixed(2)}`, icon: 'solar:dollar-minimalistic-linear', color: 'bg-emerald-50 text-emerald-600' },
            { label: 'Companies', value: companies.size, icon: 'solar:buildings-linear', color: 'bg-amber-50 text-amber-600' },
        ]
    }, [crew])

    const handleExportBounties = () => {
        const csv = toCsv(
            ['Foreman', 'Phone', 'Company', 'Company Code', 'Bounty Earned (USD)'],
            crew.map(c => [
                c.full_name, c.phone_number, c.company_name ?? '',
                c.company_code ?? '', c.total_bounties_earned.toFixed(2),
            ]),
        )
        downloadCsv('codeverity-bounty-payouts.csv', csv)
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!fullName.trim() || !phone.trim() || !companyCode.trim()) return
        setSubmitting(true)
        setFeedback(null)
        const result = await register(fullName.trim(), phone.trim(), companyCode.trim())
        if (result.ok) {
            setFeedback({ ok: true, msg: `${fullName} registered.` })
            setFullName(''); setPhone(''); setCompanyCode('')
        } else {
            setFeedback({ ok: false, msg: result.error || 'Registration failed.' })
        }
        setSubmitting(false)
    }

    return (
        <div className="p-8 space-y-10 animate-fade-up max-w-[1700px] mx-auto">
            <div className="flex items-end justify-between px-2 gap-4">
                <div>
                    <h1 className="text-3xl font-bold text-ink tracking-tight">
                        Crew <span className="text-brand">Manager</span>
                    </h1>
                    <p className="text-sm text-ink-muted mt-2">Foreman roster, pre-registration & bounty ledger</p>
                </div>
                <button
                    onClick={handleExportBounties}
                    disabled={crew.length === 0}
                    className="btn-secondary group disabled:opacity-50"
                >
                    <Icon icon="solar:card-linear" width={16} className="group-hover:-translate-y-0.5 transition-transform" />
                    Export Bounty Payout CSV
                </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {stats.map((s, i) => (
                    <StatCard key={i} label={s.label} value={s.value} icon={s.icon} accentColor={s.color} />
                ))}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Pre-registration form */}
                <div className="card p-7 lg:col-span-1 h-fit">
                    <h2 className="text-lg font-bold text-ink tracking-tight mb-1">Pre-register Foreman</h2>
                    <p className="text-xs text-ink-muted mb-6">Link a phone number to a company code.</p>
                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div>
                            <label className="text-[11px] font-medium text-ink-faint mb-1.5 block">Full Name</label>
                            <input className="input-modern" value={fullName} onChange={e => setFullName(e.target.value)} placeholder="Marcus Johnson" />
                        </div>
                        <div>
                            <label className="text-[11px] font-medium text-ink-faint mb-1.5 block">Phone (E.164)</label>
                            <input className="input-modern" value={phone} onChange={e => setPhone(e.target.value)} placeholder="+12145550199" />
                        </div>
                        <div>
                            <label className="text-[11px] font-medium text-ink-faint mb-1.5 block">Company Code</label>
                            <input className="input-modern" value={companyCode} onChange={e => setCompanyCode(e.target.value)} placeholder="4821" />
                        </div>
                        <button type="submit" disabled={submitting} className="btn-premium w-full disabled:opacity-60">
                            {submitting ? 'Registering…' : 'Register Foreman'}
                        </button>
                        {feedback && (
                            <p className={`text-xs font-medium flex items-center gap-1.5 ${feedback.ok ? 'text-emerald-600' : 'text-red-500'}`}>
                                <Icon icon={feedback.ok ? 'solar:check-circle-linear' : 'solar:danger-triangle-linear'} width={14} />
                                {feedback.msg}
                            </p>
                        )}
                    </form>
                </div>

                {/* Bounty ledger */}
                <div className="card overflow-hidden lg:col-span-2">
                    <div className="px-6 py-5 border-b border-border">
                        <h2 className="text-lg font-bold text-ink tracking-tight">Bounty Ledger</h2>
                        <p className="text-xs text-ink-muted mt-0.5">$25 per approved supplement package</p>
                    </div>
                    <div className="overflow-x-auto custom-scrollbar">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-border text-left">
                                    <th className="px-5 py-3 text-[11px] font-semibold text-ink-muted uppercase tracking-wide">Foreman</th>
                                    <th className="px-5 py-3 text-[11px] font-semibold text-ink-muted uppercase tracking-wide">Phone</th>
                                    <th className="px-5 py-3 text-[11px] font-semibold text-ink-muted uppercase tracking-wide">Company</th>
                                    <th className="px-5 py-3 text-[11px] font-semibold text-ink-muted uppercase tracking-wide text-right">Earned</th>
                                </tr>
                            </thead>
                            <tbody>
                                {isLoading ? (
                                    <tr><td colSpan={4} className="text-center py-14 text-ink-faint text-sm">Loading roster…</td></tr>
                                ) : crew.length === 0 ? (
                                    <tr><td colSpan={4} className="text-center py-14 text-ink-faint text-sm">No foremen registered yet.</td></tr>
                                ) : (
                                    crew.map(c => (
                                        <tr key={c.crew_id} className="border-b border-border/60 last:border-0 hover:bg-brand-muted/30 transition-colors">
                                            <td className="px-5 py-4 font-semibold text-ink">{c.full_name}</td>
                                            <td className="px-5 py-4 text-ink-soft">{c.phone_number}</td>
                                            <td className="px-5 py-4 text-ink-soft">
                                                {c.company_name || '—'}
                                                {c.company_code && <span className="ml-2 text-[11px] text-ink-faint">({c.company_code})</span>}
                                            </td>
                                            <td className="px-5 py-4 text-right font-bold text-emerald-600">${c.total_bounties_earned.toFixed(2)}</td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    )
}

export default Instances
