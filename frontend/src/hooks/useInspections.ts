import { useCallback, useEffect, useRef, useState } from 'react'
import type { Inspection } from '../types'
import { approveInspection, deleteInspection, fetchInspections, inspectionsWsUrl } from '../lib/api'

interface WsMessage {
    type: 'snapshot' | 'inspection.completed' | 'inspection.updated' | 'inspection.deleted' | 'ping'
    data?: Inspection[] | Inspection | { session_id: string }
}

/**
 * Live inspection feed over WebSocket with exponential-backoff auto-reconnect (PRD §3.3).
 * Backend pings every 30s; we reconnect on any drop. Falls back to a REST backfill so the
 * dashboard is populated even if the socket is briefly unavailable.
 */
export function useInspections() {
    const [inspections, setInspections] = useState<Inspection[]>([])
    const [connected, setConnected] = useState(false)
    const wsRef = useRef<WebSocket | null>(null)
    const attemptRef = useRef(0)
    const timerRef = useRef<number | undefined>(undefined)
    const closedByUs = useRef(false)

    const upsert = useCallback((incoming: Inspection) => {
        setInspections(prev => [incoming, ...prev.filter(p => p.session_id !== incoming.session_id)])
    }, [])

    useEffect(() => {
        closedByUs.current = false

        // REST backfill first so the UI is never empty on first paint.
        fetchInspections().then(setInspections).catch(() => { /* WS snapshot will fill in */ })

        const connect = () => {
            let ws: WebSocket
            try {
                ws = new WebSocket(inspectionsWsUrl())
            } catch {
                scheduleReconnect()
                return
            }
            wsRef.current = ws

            ws.onopen = () => {
                setConnected(true)
                attemptRef.current = 0
            }
            ws.onmessage = (event) => {
                let msg: WsMessage
                try {
                    msg = JSON.parse(event.data)
                } catch {
                    return
                }
                if (msg.type === 'ping') return
                if (msg.type === 'snapshot' && Array.isArray(msg.data)) {
                    setInspections(msg.data)
                } else if (msg.type === 'inspection.deleted' && msg.data && !Array.isArray(msg.data)) {
                    const id = (msg.data as { session_id: string }).session_id
                    setInspections(prev => prev.filter(p => p.session_id !== id))
                } else if (
                    (msg.type === 'inspection.completed' || msg.type === 'inspection.updated') &&
                    msg.data && !Array.isArray(msg.data)
                ) {
                    upsert(msg.data as Inspection)
                }
            }
            ws.onclose = () => {
                setConnected(false)
                if (!closedByUs.current) scheduleReconnect()
            }
            ws.onerror = () => ws.close()
        }

        const scheduleReconnect = () => {
            const delay = Math.min(30000, 1000 * 2 ** attemptRef.current)
            attemptRef.current += 1
            timerRef.current = window.setTimeout(connect, delay)
        }

        connect()

        return () => {
            closedByUs.current = true
            if (timerRef.current) window.clearTimeout(timerRef.current)
            wsRef.current?.close()
        }
    }, [upsert])

    const approve = useCallback(async (sessionId: string) => {
        const res = await approveInspection(sessionId)
        if (res.ok) {
            // Reflect the SERVER's truth (bounty + CRM delivery), not a fabricated status.
            setInspections(prev =>
                prev.map(i =>
                    i.session_id === sessionId
                        ? {
                            ...i,
                            bounty_status: res.bounty_status ?? i.bounty_status,
                            crm_status: res.crm_status ?? i.crm_status,
                        }
                        : i,
                ),
            )
        }
        return res.ok
    }, [])

    const remove = useCallback(async (sessionId: string) => {
        const res = await deleteInspection(sessionId)
        if (res.ok) {
            // Optimistic local removal; the WS 'inspection.deleted' event keeps other consoles in sync.
            setInspections(prev => prev.filter(i => i.session_id !== sessionId))
        }
        return res.ok
    }, [])

    const refetch = useCallback(() => {
        fetchInspections().then(setInspections).catch(() => { /* ignore */ })
    }, [])

    return { inspections, connected, approve, remove, refetch }
}
