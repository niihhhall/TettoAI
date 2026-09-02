import React, { useMemo, useState } from 'react'
import { Icon } from '@iconify/react'
import { useJobsites } from '../hooks/useJobsites'
import { StatCard } from '../components/ui/StatCard'
import type { Jobsite } from '../types'
import type { JobsiteInput } from '../lib/api'

const EMPTY: JobsiteInput = {
    property_address: '', claim_number: '', city: '', state: '',
    zip_code: '', county: '', municipal_code_summary: '',
}

const Jobsites: React.FC = () => {
    const { jobsites, isLoading, create, update } = useJobsites()

    const [form, setForm] = useState<JobsiteInput>(EMPTY)
    const [editingId, setEditingId] = useState<string | null>(null)
    const [submitting, setSubmitting] = useState(false)
    const [feedback, setFeedback] = useState<{ ok: boolean; msg: string } | null>(null)

    const stats = useMemo(() => {
        const withClaim = jobsites.filter(j => j.claim_number).length
        const cities = new Set(jobsites.map(j => j.city).filter(Boolean))
        return [
            { label: 'Jobsites', value: jobsites.length, icon: 'solar:map-point-linear', color: 'bg-brand-muted text-brand' },
            { label: 'With Claim #', value: withClaim, icon: 'solar:document-text-linear', color: 'bg-emerald-50 text-emerald-600' },
            { label: 'Cities', value: cities.size, icon: 'solar:city-linear', color: 'bg-amber-50 text-amber-600' },
        ]
    }, [jobsites])

    const set = (k: keyof JobsiteInput) => (e: React.ChangeEvent<HTMLInputElement>) =>
        setForm(prev => ({ ...prev, [k]: e.target.value }))

    const resetForm = () => { setForm(EMPTY); setEditingId(null); setFeedback(null) }

    const startEdit = (j: Jobsite) => {
        setEditingId(j.job_id)
        setForm({
            property_address: j.property_address ?? '',
            claim_number: j.claim_number ?? '',
            city: j.city ?? '',
            state: j.state ?? '',
            zip_code: j.zip_code ?? '',
            county: j.county ?? '',
            municipal_code_summary: j.municipal_code_summary ?? '',
        })
        setFeedback(null)
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!form.property_address.trim()) {
            setFeedback({ ok: false, msg: 'Property address is required.' })
            return
        }
        setSubmitting(true)
        setFeedback(null)
        const result = editingId ? await update(editingId, form) : await create(form)
        if (result.ok) {
            setFeedback({ ok: true, msg: editingId ? 'Jobsite updated.' : 'Jobsite added.' })
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
                    Jobsite <span className="text-brand">Management</span>
                </h1>
                <p className="text-sm text-ink-muted mt-2">Preload jobsites your foremen pick on WhatsApp — address, claim number & municipal code.</p>
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
                            {editingId ? 'Edit Jobsite' : 'Add Jobsite'}
                        </h2>
                        {editingId && (
                            <button onClick={resetForm} className="text-xs text-ink-muted hover:text-brand flex items-center gap-1">
                                <Icon icon="solar:add-circle-linear" width={14} /> New
                            </button>
                        )}
                    </div>
                    <p className="text-xs text-ink-muted mb-6">Only the property address is required.</p>
                    <form onSubmit={handleSubmit} className="space-y-4">
                        <Field label="Property Address *" value={form.property_address} onChange={set('property_address')} placeholder="1420 Elmwood Dr, Dallas, TX 75201" />
                        <div className="grid grid-cols-2 gap-3">
                            <Field label="Claim #" value={form.claim_number} onChange={set('claim_number')} placeholder="A-1029" />
                            <Field label="City" value={form.city} onChange={set('city')} placeholder="Dallas" />
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <Field label="State" value={form.state} onChange={set('state')} placeholder="TX" />
                            <Field label="ZIP" value={form.zip_code} onChange={set('zip_code')} placeholder="75201" />
                        </div>
                        <Field label="County" value={form.county} onChange={set('county')} placeholder="Dallas County" />
                        <Field label="Municipal Code Summary" value={form.municipal_code_summary} onChange={set('municipal_code_summary')} placeholder="Dallas municipal roofing code" />
                        <button type="submit" disabled={submitting} className="btn-premium w-full disabled:opacity-60">
                            {submitting ? 'Saving…' : editingId ? 'Update Jobsite' : 'Add Jobsite'}
                        </button>
                        {feedback && (
                            <p className={`text-xs font-medium flex items-center gap-1.5 ${feedback.ok ? 'text-emerald-600' : 'text-red-500'}`}>
                                <Icon icon={feedback.ok ? 'solar:check-circle-linear' : 'solar:danger-triangle-linear'} width={14} />
                                {feedback.msg}
                            </p>
                        )}
                    </form>
                </div>

                {/* Jobsite table */}
                <div className="card overflow-hidden lg:col-span-2">
                    <div className="px-6 py-5 border-b border-border">
                        <h2 className="text-lg font-bold text-ink tracking-tight">Jobsites</h2>
                        <p className="text-xs text-ink-muted mt-0.5">Includes foreman-created sites (auto-added from GPS)</p>
                    </div>
                    <div className="overflow-x-auto custom-scrollbar">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-border text-left">
                                    <th className="px-5 py-3 text-[11px] font-semibold text-ink-muted uppercase tracking-wide">Address</th>
                                    <th className="px-5 py-3 text-[11px] font-semibold text-ink-muted uppercase tracking-wide">Claim #</th>
                                    <th className="px-5 py-3 text-[11px] font-semibold text-ink-muted uppercase tracking-wide">City</th>
                                    <th className="px-5 py-3 text-[11px] font-semibold text-ink-muted uppercase tracking-wide text-right">Edit</th>
                                </tr>
                            </thead>
                            <tbody>
                                {isLoading ? (
                                    <tr><td colSpan={4} className="text-center py-14 text-ink-faint text-sm">Loading jobsites…</td></tr>
                                ) : jobsites.length === 0 ? (
                                    <tr><td colSpan={4} className="text-center py-14 text-ink-faint text-sm">No jobsites yet. Add one on the left.</td></tr>
                                ) : (
                                    jobsites.map(j => (
                                        <tr key={j.job_id} className="border-b border-border/60 last:border-0 hover:bg-brand-muted/30 transition-colors">
                                            <td className="px-5 py-4 font-semibold text-ink">{j.property_address}</td>
                                            <td className="px-5 py-4 text-ink-soft">{j.claim_number || '—'}</td>
                                            <td className="px-5 py-4 text-ink-soft">{j.city || '—'}</td>
                                            <td className="px-5 py-4 text-right">
                                                <button onClick={() => startEdit(j)} className="btn-secondary !py-1.5 !px-3 text-xs">
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

export default Jobsites
