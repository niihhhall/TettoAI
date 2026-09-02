import React, { useState } from 'react'
import { Icon } from '@iconify/react'
import type { Inspection } from '../types'
import { Badge } from '../components/ui/Badge'
import { InspectionDrawer } from '../components/inspections/InspectionDrawer'
import { downloadCsv, toCsv } from '../lib/csv'

interface LeadsProps {
    inspections: Inspection[]
    approve: (sessionId: string) => Promise<boolean>
}

const Leads: React.FC<LeadsProps> = ({ inspections, approve }) => {
    const [selectedId, setSelectedId] = useState<string | null>(null)
    const selected = selectedId ? inspections.find(i => i.session_id === selectedId) ?? null : null

    const handleExport = () => {
        const csv = toCsv(
            ['Property Address', 'Claim #', 'Assigned Foreman', 'City Building Code', 'Line Items', 'Status'],
            inspections.map(i => [
                i.address ?? '', i.claim_number ?? '', i.crew_name ?? '',
                i.building_code ?? '', i.line_items.length, i.bounty_status,
            ]),
        )
        downloadCsv('codeverity-claims.csv', csv)
    }

    return (
        <div className="p-8 space-y-8 animate-fade-up max-w-[1700px] mx-auto">
            <div className="flex items-end justify-between px-2 gap-4">
                <div>
                    <h1 className="text-3xl font-bold text-ink tracking-tight">
                        Claims <span className="text-brand">Master</span>
                    </h1>
                    <p className="text-sm text-ink-muted mt-2">All supplement packages across jobsites</p>
                </div>
                <button
                    onClick={handleExport}
                    disabled={inspections.length === 0}
                    className="btn-secondary group disabled:opacity-50"
                >
                    <Icon icon="solar:chart-2-linear" width={16} className="group-hover:-translate-y-0.5 transition-transform" />
                    Export Claims CSV
                </button>
            </div>

            <div className="card overflow-hidden">
                <div className="overflow-x-auto custom-scrollbar">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b border-border text-left">
                                <Th>Property Address</Th>
                                <Th>Claim #</Th>
                                <Th>Assigned Foreman</Th>
                                <Th>City Building Code</Th>
                                <Th>Line Items</Th>
                                <Th>Status</Th>
                                <Th> </Th>
                            </tr>
                        </thead>
                        <tbody>
                            {inspections.length === 0 ? (
                                <tr>
                                    <td colSpan={7} className="text-center py-16 text-ink-faint text-sm">
                                        No claims yet.
                                    </td>
                                </tr>
                            ) : (
                                inspections.map(insp => (
                                    <tr
                                        key={insp.session_id}
                                        onClick={() => setSelectedId(insp.session_id)}
                                        className="border-b border-border/60 last:border-0 hover:bg-brand-muted/30 cursor-pointer transition-colors"
                                    >
                                        <Td className="font-semibold text-ink">{insp.address || '—'}</Td>
                                        <Td>{insp.claim_number || '—'}</Td>
                                        <Td>{insp.crew_name || '—'}</Td>
                                        <Td className="max-w-[220px] truncate">{insp.building_code || '—'}</Td>
                                        <Td>{insp.line_items.length}</Td>
                                        <Td><Badge value={insp.bounty_status} /></Td>
                                        <Td>
                                            <Icon icon="solar:arrow-right-linear" width={16} className="text-ink-faint" />
                                        </Td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            <InspectionDrawer inspection={selected} onClose={() => setSelectedId(null)} onApprove={approve} />
        </div>
    )
}

const Th: React.FC<{ children: React.ReactNode }> = ({ children }) => (
    <th className="px-5 py-4 text-[11px] font-semibold text-ink-muted uppercase tracking-wide whitespace-nowrap">{children}</th>
)

const Td: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
    <td className={`px-5 py-4 text-ink-soft ${className}`}>{children}</td>
)

export default Leads
