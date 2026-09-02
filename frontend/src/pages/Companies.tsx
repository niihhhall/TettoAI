import React, { useMemo, useState } from 'react'
import { Icon } from '@iconify/react'
import { useCompanies } from '../hooks/useCompanies'
import { StatCard } from '../components/ui/StatCard'
import type { Company } from '../types'
import type { CompanyInput } from '../lib/api'

const EMPTY: CompanyInput = { company_name: '', invite_code: '', crm_type: 'JobNimbus', crm_webhook_url: '' }

const Companies: React.FC = () => {
    const { companies, isLoading, create, update } = useCompanies()

    const [form, setForm] = useState<CompanyInput>(EMPTY)
    const [editingId, setEditingId] = useState<string | null>(null)
    const [submitting, setSubmitting] = useState(false)
    const [feedback, setFeedback] = useState<{ ok: boolean; msg: string } | null>(null)

    const stats = useMemo(() => {
        const withCrm = companies.filter(c => c.crm_webhook_url).length
        return [
            { label: 'Branches', value: companies.length, icon: 'solar:buildings-3-linear', color: 'bg-brand-muted text-brand' },
            { label: 'CRM Connected', value: withCrm, icon: 'solar:link-circle-linear', color: 'bg-emerald-50 text-emerald-600' },
        ]
    }, [companies])

    const set = (k: keyof CompanyInput) => (e: React.ChangeEvent<HTMLInputElement>) =>
        setForm(prev => ({ ...prev, [k]: e.target.value }))

    const resetForm = () => { setForm(EMPTY); setEditingId(null); setFeedback(null) }

    const startEdit = (c: Company) => {
        setEditingId(c.company_id)
        setForm({
            company_name: c.company_name ?? '',
            invite_code: c.invite_code ?? '',
            crm_type: c.crm_type ?? 'JobNimbus',
            crm_webhook_url: c.crm_webhook_url ?? '',
        })
        setFeedback(null)
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!form.company_name.trim() || !form.invite_code.trim()) {
            setFeedback({ ok: false, msg: 'Company name and invite code are required.' })
            return
        }
        setSubmitting(true)
        setFeedback(null)
        const result = editingId ? await update(editingId, form) : await create(form)
        if (result.ok) {
            setFeedback({ ok: true, msg: editingId ? 'Branch updated.' : 'Branch added.' })
            resetForm()
        } else {
            setFeedback({ ok: false, msg: result.error || 'Save failed.' })
        }
        setSubmitting(false)
    }

    return (
        <div className="p-8 space-y-10 animate-fade-up max-w-[1700px] mx-auto">
            <div className="px-2">
                <h1 className="text-3xl font-bold text-ink tracking-tight">
                    Company <span className="text-brand">Branches</span>
                </h1>
                <p className="text-sm text-ink-muted mt-2">Manage contractor companies — invite code (foreman onboarding) and CRM webhook (approval push).</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {stats.map((s, i) => (
                    <StatCard key={i} label={s.label} value={s.value} icon={s.icon} accentColor={s.color} />
                ))}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Create / edit form */}
                <div className="card p-7 lg:col-span-1 h-fit">
                    <div className="flex items-center justify-between mb-1">
                        <h2 className="text-lg font-bold text-ink tracking-tight">
                            {editingId ? 'Edit Branch' : 'Add Branch'}
                        </h2>
                        {editingId && (
                            <button onClick={resetForm} className="text-xs text-ink-muted hover:text-brand flex items-center gap-1">
                                <Icon icon="solar:add-circle-linear" width={14} /> New
                            </button>
                        )}
                    </div>
                    <p className="text-xs text-ink-muted mb-6">The invite code is what foremen type to join on WhatsApp.</p>
                    <form onSubmit={handleSubmit} className="space-y-4">
                        <Field label="Company Name *" value={form.company_name} onChange={set('company_name')} placeholder="Apex Roofing" />
                        <Field label="Invite Code *" value={form.invite_code} onChange={set('invite_code')} placeholder="4821" />
                        <Field label="CRM Type" value={form.crm_type} onChange={set('crm_type')} placeholder="JobNimbus" />
                        <Field label="CRM Webhook URL" value={form.crm_webhook_url} onChange={set('crm_webhook_url')} placeholder="https://hooks.jobnimbus.com/..." />
                        <button type="submit" disabled={submitting} className="btn-premium w-full disabled:opacity-60">
                            {submitting ? 'Saving…' : editingId ? 'Update Branch' : 'Add Branch'}
                        </button>
                        {feedback && (
                            <p className={`text-xs font-medium flex items-center gap-1.5 ${feedback.ok ? 'text-emerald-600' : 'text-red-500'}`}>
                                <Icon icon={feedback.ok ? 'solar:check-circle-linear' : 'solar:danger-triangle-linear'} width={14} />
                                {feedback.msg}
                            </p>
                        )}
                    </form>
                </div>

                {/* Branch table */}
                <div className="card overflow-hidden lg:col-span-2">
                    <div className="px-6 py-5 border-b border-border">
                        <h2 className="text-lg font-bold text-ink tracking-tight">Branches</h2>
                        <p className="text-xs text-ink-muted mt-0.5">Contractor companies on this deployment</p>
                    </div>
                    <div className="overflow-x-auto custom-scrollbar">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-border text-left">
                                    <th className="px-5 py-3 text-[11px] font-semibold text-ink-muted uppercase tracking-wide">Company</th>
                                    <th className="px-5 py-3 text-[11px] font-semibold text-ink-muted uppercase tracking-wide">Invite Code</th>
                                    <th className="px-5 py-3 text-[11px] font-semibold text-ink-muted uppercase tracking-wide">CRM</th>
                                    <th className="px-5 py-3 text-[11px] font-semibold text-ink-muted uppercase tracking-wide text-right">Edit</th>
                                </tr>
                            </thead>
                            <tbody>
                                {isLoading ? (
                                    <tr><td colSpan={4} className="text-center py-14 text-ink-faint text-sm">Loading branches…</td></tr>
                                ) : companies.length === 0 ? (
                                    <tr><td colSpan={4} className="text-center py-14 text-ink-faint text-sm">No branches yet. Add one on the left.</td></tr>
                                ) : (
                                    companies.map(c => (
                                        <tr key={c.company_id} className="border-b border-border/60 last:border-0 hover:bg-brand-muted/30 transition-colors">
                                            <td className="px-5 py-4 font-semibold text-ink">{c.company_name}</td>
                                            <td className="px-5 py-4"><span className="font-mono text-xs px-2 py-1 rounded bg-bg-elevated border border-border text-ink-soft">{c.invite_code}</span></td>
                                            <td className="px-5 py-4 text-ink-soft">
                                                {c.crm_type || '—'}
                                                {c.crm_webhook_url
                                                    ? <span className="ml-2 text-[10px] text-emerald-600">● connected</span>
                                                    : <span className="ml-2 text-[10px] text-ink-faint">○ no webhook</span>}
                                            </td>
                                            <td className="px-5 py-4 text-right">
                                                <button onClick={() => startEdit(c)} className="btn-secondary !py-1.5 !px-3 text-xs">
                                                    <Icon icon="solar:pen-linear" width={13} /> Edit
                                                </button>
                                            </td>
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

const Field: React.FC<{ label: string; value?: string; onChange: (e: React.ChangeEvent<HTMLInputElement>) => void; placeholder?: string }> = ({ label, value, onChange, placeholder }) => (
    <div>
        <label className="text-[11px] font-medium text-ink-faint mb-1.5 block">{label}</label>
        <input className="input-modern" value={value ?? ''} onChange={onChange} placeholder={placeholder} />
    </div>
)

export default Companies
