import React, { useState } from 'react'
import { createPortal } from 'react-dom'
import { Icon } from '@iconify/react'
import type { Inspection, InspectionLineItem, PhotoEvidence } from '../../types'
import { Badge } from '../ui/Badge'

interface InspectionDrawerProps {
    inspection: Inspection | null
    onClose: () => void
    onApprove: (sessionId: string) => Promise<boolean>
}

function lineItemText(item: InspectionLineItem): string {
    return `${item.code} - ${item.description} - ${item.qty} ${item.unit}`
}

export const InspectionDrawer: React.FC<InspectionDrawerProps> = ({ inspection, onClose, onApprove }) => {
    const [copied, setCopied] = useState<string | null>(null)
    const [approving, setApproving] = useState(false)

    if (!inspection) return null

    const copy = async (key: string, text: string) => {
        try {
            await navigator.clipboard.writeText(text)
            setCopied(key)
            window.setTimeout(() => setCopied(null), 1500)
        } catch {
            /* clipboard unavailable */
        }
    }

    const copyAll = () => {
        const all = inspection.line_items.map(lineItemText).join('\n')
        copy('__all__', all)
    }

    const handleApprove = async () => {
        setApproving(true)
        await onApprove(inspection.session_id)
        setApproving(false)
    }

    // Portal to <body> so `fixed` escapes any transformed/max-width ancestor (e.g. the
    // page's animate-fade-up wrapper) and truly covers the viewport — not just the content area.
    return createPortal(
        <div className="fixed inset-0 z-[100] flex justify-end">
            {/* Backdrop: barely-there dim so the page behind stays crisp; the panel's shadow
                provides the elevation. Click anywhere to close. */}
            <div className="absolute inset-0 bg-ink/10 animate-in fade-in duration-200" onClick={onClose} />

            {/* Slide-over panel */}
            <div className="relative w-full max-w-2xl h-full bg-white shadow-2xl flex flex-col animate-fade-right overflow-hidden">
                {/* Header */}
                <div className="flex items-start justify-between p-7 border-b border-border bg-white">
                    <div className="flex items-center gap-4">
                        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-brand to-brand-dark flex items-center justify-center text-white shadow-card">
                            <Icon icon="solar:home-2-linear" width={24} />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold tracking-tight text-ink">
                                {inspection.address || 'Unlocated jobsite'}
                            </h2>
                            <div className="flex items-center gap-3 mt-1.5">
                                <span className="text-xs text-ink-muted">{inspection.crew_name || 'Unknown foreman'}</span>
                                <Badge value={inspection.bounty_status} />
                            </div>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="w-10 h-10 flex items-center justify-center hover:bg-bg-elevated rounded-xl transition-all text-ink-faint hover:text-ink border border-transparent hover:border-border"
                    >
                        <Icon icon="solar:close-circle-linear" width={24} />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar p-7 space-y-8">
                    {/* Meta */}
                    <div className="grid grid-cols-2 gap-4">
                        <MetaCell label="Claim #" value={inspection.claim_number || '—'} icon="solar:document-text-linear" />
                        <MetaCell label="City" value={inspection.city || '—'} icon="solar:map-point-linear" />
                        <MetaCell label="Company" value={inspection.company_name || '—'} icon="solar:buildings-linear" />
                        <MetaCell label="Building Code" value={inspection.building_code || '—'} icon="solar:shield-check-linear" />
                        <MetaCell
                            label="Supplement Value"
                            value={inspection.supplement_value != null ? `$${inspection.supplement_value.toLocaleString()}` : 'Pending'}
                            icon="solar:dollar-minimalistic-linear"
                        />
                        <MetaCell
                            label="Submitted"
                            value={inspection.created_at ? new Date(inspection.created_at).toLocaleString() : '—'}
                            icon="solar:clock-circle-linear"
                        />
                    </div>

                    {/* 1-click Xactimate copy buttons */}
                    <section className="space-y-3">
                        <div className="flex items-center justify-between">
                            <h3 className="text-xs font-semibold text-ink-muted uppercase tracking-wide">Xactimate Line Items</h3>
                            {inspection.line_items.length > 0 && (
                                <button onClick={copyAll} className="btn-ghost text-xs">
                                    <Icon icon="solar:copy-linear" width={14} />
                                    {copied === '__all__' ? 'Copied all' : 'Copy all'}
                                </button>
                            )}
                        </div>
                        {inspection.line_items.length === 0 ? (
                            <p className="text-xs text-ink-faint">No line items extracted yet.</p>
                        ) : (
                            <div className="space-y-2">
                                {inspection.line_items.map((item, i) => (
                                    <div
                                        key={`${item.code}-${i}`}
                                        className="p-3 rounded-xl bg-bg-elevated border border-border space-y-2"
                                    >
                                        <div className="flex items-center justify-between gap-3">
                                            <div className="min-w-0">
                                                <p className="text-sm font-semibold text-ink truncate">
                                                    <span className="text-brand">{item.code}</span> {item.description}
                                                </p>
                                                <p className="text-xs text-ink-muted">{item.qty} {item.unit}</p>
                                            </div>
                                            <button
                                                onClick={() => copy(`${item.code}-${i}`, lineItemText(item))}
                                                className="btn-secondary shrink-0 !py-2 !px-3 text-xs"
                                            >
                                                <Icon icon="solar:copy-linear" width={14} />
                                                {copied === `${item.code}-${i}` ? 'Copied' : `Copy ${item.code}`}
                                            </button>
                                        </div>
                                        {/* Linked photo evidence — the whole point of the per-photo model. */}
                                        {item.photo_urls && item.photo_urls.length > 0 && (
                                            <div className="flex items-center gap-2 pt-0.5">
                                                <span className="text-[10px] font-medium text-emerald-600 flex items-center gap-1 shrink-0">
                                                    <Icon icon="solar:gallery-linear" width={12} />
                                                    {item.photo_urls.length} photo{item.photo_urls.length > 1 ? 's' : ''}
                                                </span>
                                                <div className="flex gap-1.5">
                                                    {item.photo_urls.slice(0, 4).map((url, pi) => (
                                                        <a key={pi} href={url} target="_blank" rel="noreferrer"
                                                            className="w-8 h-8 rounded-md overflow-hidden border border-border hover:border-brand/50 transition-all">
                                                            <img src={url} alt="" className="w-full h-full object-cover" />
                                                        </a>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        )}
                    </section>

                    {/* Per-photo evidence: each photo with its vision caption, damage chips,
                        and optional per-photo voice note + transcript. Falls back to a plain
                        grid for older records that predate the evidence model. */}
                    {(() => {
                        const evidence: PhotoEvidence[] =
                            inspection.photo_evidence && inspection.photo_evidence.length > 0
                                ? inspection.photo_evidence
                                : inspection.photos.map((url) => ({ url }))
                        if (evidence.length === 0) return null
                        return (
                            <section className="space-y-3">
                                <h3 className="text-xs font-semibold text-ink-muted uppercase tracking-wide">
                                    Geo-tagged Evidence ({evidence.length})
                                </h3>
                                <div className="grid grid-cols-2 gap-3">
                                    {evidence.map((ev, i) => (
                                        <div key={i} className="rounded-xl overflow-hidden border border-border bg-white">
                                            <a href={ev.url} target="_blank" rel="noreferrer" className="block aspect-video bg-bg-elevated">
                                                <img src={ev.url} alt={ev.caption || `Evidence ${i + 1}`} className="w-full h-full object-cover" />
                                            </a>
                                            <div className="p-3 space-y-2">
                                                <div className="flex items-center justify-between">
                                                    <span className="text-[10px] font-semibold text-ink-faint uppercase tracking-wide">Photo {i + 1}</span>
                                                    {ev.voice_note_url && (
                                                        <span className="text-[10px] text-brand flex items-center gap-1">
                                                            <Icon icon="solar:microphone-linear" width={12} /> Voice
                                                        </span>
                                                    )}
                                                </div>
                                                {ev.caption && <p className="text-xs text-ink-soft leading-snug">{ev.caption}</p>}
                                                {ev.damage_types && ev.damage_types.length > 0 && (
                                                    <div className="flex flex-wrap gap-1">
                                                        {ev.damage_types.map((d, di) => (
                                                            <span key={di} className="text-[10px] px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-100">{d}</span>
                                                        ))}
                                                    </div>
                                                )}
                                                {ev.voice_note_url && (
                                                    <audio controls src={ev.voice_note_url} className="w-full h-8" />
                                                )}
                                                {ev.transcript && <p className="text-[11px] italic text-ink-muted leading-snug">“{ev.transcript}”</p>}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </section>
                        )
                    })()}

                    {/* Closing voice note (overall scope) */}
                    {inspection.voice_note_url && (
                        <section className="space-y-3">
                            <h3 className="text-xs font-semibold text-ink-muted uppercase tracking-wide">Closing Voice Note (overall scope)</h3>
                            <audio controls src={inspection.voice_note_url} className="w-full">
                                Your browser does not support audio playback.
                            </audio>
                        </section>
                    )}

                    {/* Transcript */}
                    {inspection.transcription && (
                        <section className="space-y-3">
                            <h3 className="text-xs font-semibold text-ink-muted uppercase tracking-wide">Field Scope Transcript</h3>
                            <p className="text-sm text-ink-soft leading-relaxed p-4 rounded-xl bg-bg-elevated border border-border">
                                {inspection.transcription}
                            </p>
                        </section>
                    )}

                    {/* PDF preview */}
                    <section className="space-y-3">
                        <h3 className="text-xs font-semibold text-ink-muted uppercase tracking-wide">Supplement PDF</h3>
                        {inspection.pdf_url ? (
                            <iframe
                                title="Supplement PDF"
                                src={inspection.pdf_url}
                                className="w-full h-[420px] rounded-xl border border-border bg-white"
                            />
                        ) : (
                            <p className="text-xs text-ink-faint">PDF not compiled yet.</p>
                        )}
                    </section>
                </div>

                {/* Footer action */}
                <div className="p-5 border-t border-border bg-white flex items-center justify-between gap-4">
                    {inspection.pdf_url && (
                        <a href={inspection.pdf_url} target="_blank" rel="noreferrer" className="btn-secondary text-xs">
                            <Icon icon="solar:download-linear" width={16} />
                            Download PDF Report
                        </a>
                    )}
                    {inspection.bounty_status === 'APPROVED' && inspection.crm_status && (
                        <span className="text-xs text-ink-muted">
                            CRM: {inspection.crm_status}
                        </span>
                    )}
                    <button
                        onClick={handleApprove}
                        disabled={approving || inspection.bounty_status === 'APPROVED'}
                        className="btn-premium ml-auto !py-3 !px-5 text-sm disabled:opacity-60"
                    >
                        <span className="flex items-center gap-2">
                            <Icon icon="solar:check-circle-linear" width={18} />
                            {inspection.bounty_status === 'APPROVED'
                                ? 'Approved'
                                : approving ? 'Approving…' : 'Approve & Push to CRM'}
                        </span>
                    </button>
                </div>
            </div>
        </div>,
        document.body,
    )
}

const MetaCell: React.FC<{ label: string; value: string; icon: string }> = ({ label, value, icon }) => (
    <div className="flex items-center gap-3 p-3 rounded-xl bg-white border border-border">
        <div className="w-9 h-9 rounded-lg bg-brand-muted text-brand flex items-center justify-center shrink-0">
            <Icon icon={icon} width={18} />
        </div>
        <div className="min-w-0">
            <p className="text-[10px] font-medium text-ink-faint">{label}</p>
            <p className="text-sm font-semibold text-ink truncate">{value}</p>
        </div>
    </div>
)
