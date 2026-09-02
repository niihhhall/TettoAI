import { useCallback, useEffect, useState } from 'react'
import type { CrewRow } from '../types'
import { fetchCrew, registerCrew } from '../lib/api'

/** Crew Manager data: roster + bounty ledger, with pre-registration. */
export function useCrew() {
    const [crew, setCrew] = useState<CrewRow[]>([])
    const [isLoading, setIsLoading] = useState(true)

    const load = useCallback(async () => {
        try {
            setCrew(await fetchCrew())
        } catch {
            /* backend unreachable — leave existing roster */
        } finally {
            setIsLoading(false)
        }
    }, [])

    useEffect(() => {
        load()
        const interval = window.setInterval(load, 15000)
        return () => window.clearInterval(interval)
    }, [load])

    const register = useCallback(
        async (fullName: string, phone: string, companyCode: string) => {
            const result = await registerCrew(fullName, phone, companyCode)
            if (result.ok) await load()
            return result
        },
        [load],
    )

    return { crew, isLoading, register, refetch: load }
}
