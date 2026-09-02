import React, { useState } from 'react'
import { Icon } from '@iconify/react'
import type { Inspection } from '../types'
import { Badge } from '../components/ui/Badge'
import { InspectionDrawer } from '../components/inspections/InspectionDrawer'

interface ConversationsProps {
    inspections: Inspection[]
    connected: boolean
    approve: (sessionId: string) => Promise<boolean>
    onDelete: (sessionId: string) => Promise<boolean>
}

/** Initials for a foreman avatar chip, e.g. "Marcus Johnson" -> "MJ". */
function initials(name: string | null | undefined): string {
    const parts = (name || '').trim().split(/\s+/).filter(Boolean)
    if (!parts.length) return '??'
    return (parts[0][0] + (parts[1]?.[0] ?? '')).toUpperCase()
}

/** A small labelled pill badge (photos / items / claim code). */
const MetaPill: React.FC<{ icon: string; label: string; tone?: 'default' | 'brand' }> = ({
    icon, label, tone = 'default',
}) => (
    <span
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold border ${
            tone === 'brand'
                ? 'bg-brand-muted border-brand/15 text-brand'
                : 'bg-bg-elevated border-border text-ink-muted'
        }`}
    >
        <Icon icon={icon} width={13} />
        {label}
    </span>
)

const Conversations: React.FC<ConversationsProps> = ({ inspections, connected, approve, onDelete }) => {
    const [selectedId, setSelectedId] = useState<string | null>(null)
    const [deletingId, setDeletingId] = useState<string | null>(null)
    const selected = selectedId ? inspections.find(i => i.session_id === selectedId) ?? null : null

    const handleDelete = async (e: React.MouseEvent, insp: Inspection) => {
        e.stopPropagation()
        const who = insp.crew_name ? ` from ${insp.crew_name}` : ''
        if (!window.confirm(`Delete this inspection${who}? This can't be undone.`)) return
        setDeletingId(insp.session_id)
        await onDelete(insp.session_id)
        setDeletingId(null)
    }

    return (
        <div className="p-8 space-y-8 animate-fade-up max-w-[1700px] mx-auto">
            <div className="flex items-center justify-between px-2">
                <div>
                    <h1 className="text-3xl font-bold text-ink tracking-tight">
                        Live <span className="text-brand">Feed</span>
                    </h1>
                    <p className="text-sm text-ink-muted mt-2">Real-time field intake from the crew</p>
                </div>
                <div className={`flex items-center gap-2 px-4 py-2 rounded-full border ${
                    connected ? 'bg-emerald-50 border-emerald-100' : 'bg-amber-50 border-amber-100'
                }`}>
                    <span className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-500 animate-pulse-dot' : 'bg-amber-500'}`} />
                    <span className={`text-xs font-semibold ${connected ? 'text-emerald-600' : 'text-amber-600'}`}>
                        {connected ? 'Live' : 'Reconnecting…'}
                    </span>
                </div>
            </div>

            {inspections.length === 0 ? (
                <div className="card p-16 text-center">
                    <Icon icon="solar:inbox-linear" width={40} className="text-ink-faint mx-auto mb-4" />
                    <p className="text-sm font-medium text-ink-muted">No inspections yet.</p>
                    <p className="text-xs text-ink-faint mt-1">Field submissions will appear here in real time.</p>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                    {inspections.map((insp) => (
                        <div
                            key={insp.session_id}
                            role="button"
                            tabIndex={0}
                            onClick={() => setSelectedId(insp.session_id)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                    e.preventDefault()
                                    setSelectedId(insp.session_id)
                                }
                            }}
                            className={`card p-6 text-left cursor-pointer hover:border-brand/30 hover:shadow-lift transition-all duration-300 group ${
                                deletingId === insp.session_id ? 'opacity-50 pointer-events-none' : ''
                            }`}
                        >
                            <div className="flex items-start justify-between gap-3 mb-4">
                                <div className="flex items-start gap-3 min-w-0">
                                    <span className="shrink-0 w-10 h-10 rounded-full bg-brand text-white text-xs font-bold leading-none flex items-center justify-center ring-2 ring-brand-100">
                                        {initials(insp.crew_name)}
                                    </span>
                                    <div className="min-w-0">
                                        {/* Name on top */}
                                        <h3 className="text-base font-bold text-ink tracking-tight truncate">
                                            {insp.crew_name || 'Unknown foreman'}
                                        </h3>
                                        {/* Address below */}
                                        <p className="mt-0.5 flex items-center gap-1 text-xs font-medium text-ink-soft truncate">
                                            <Icon icon="solar:map-point-linear" width={13} className="shrink-0 text-ink-faint" />
                                            <span className="truncate">{insp.address || 'Unlocated jobsite'}</span>
                                        </p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-1.5 shrink-0">
                                    <Badge value={insp.bounty_status} />
                                    <button
                                        type="button"
                                        onClick={(e) => handleDelete(e, insp)}
                                        title="Delete inspection"
                                        aria-label="Delete inspection"
                                        className="w-8 h-8 flex items-center justify-center rounded-lg text-ink-faint hover:text-red-600 hover:bg-red-50 border border-transparent hover:border-red-100 transition-all"
                                    >
                                        <Icon icon="solar:trash-bin-trash-linear" width={16} />
                                    </button>
                                </div>
                            </div>

                            <div className="flex flex-wrap items-center gap-2 mb-4">
                                <MetaPill icon="solar:gallery-linear" label={`${insp.photos.length} photos`} />
                                <MetaPill icon="solar:clipboard-list-linear" label={`${insp.line_items.length} items`} />
                                {insp.claim_number && (
                                    <MetaPill icon="solar:document-text-linear" label={insp.claim_number} tone="brand" />
                                )}
                            </div>

                            {insp.transcription && (
                                <p className="text-xs text-ink-soft line-clamp-2 leading-relaxed">
                                    {insp.transcription}
                                </p>
                            )}

                            <div className="mt-4 flex items-center gap-1.5 text-xs font-medium text-brand opacity-0 group-hover:opacity-100 transition-opacity">
                                Open package
                                <Icon icon="solar:arrow-right-linear" width={14} />
                            </div>
                        </div>
                    ))}
                </div>
            )}

            <InspectionDrawer inspection={selected} onClose={() => setSelectedId(null)} onApprove={approve} />
        </div>
    )
}

export default Conversations
