import { useCallback, useEffect, useState } from 'react'
import type { Company } from '../types'
import { fetchCompanies, createCompany, updateCompany, type CompanyInput } from '../lib/api'

/** Company Branches management: company profiles, invite codes, and CRM config. */
export function useCompanies() {
    const [companies, setCompanies] = useState<Company[]>([])
    const [isLoading, setIsLoading] = useState(true)

    const load = useCallback(async () => {
        try {
            setCompanies(await fetchCompanies())
        } catch {
            /* backend unreachable — keep existing list */
        } finally {
            setIsLoading(false)
        }
    }, [])

    useEffect(() => {
        load()
        const interval = window.setInterval(load, 20000)
        return () => window.clearInterval(interval)
    }, [load])

    const create = useCallback(async (body: CompanyInput) => {
        const result = await createCompany(body)
        if (result.ok) await load()
        return result
    }, [load])

    const update = useCallback(async (companyId: string, body: Partial<CompanyInput>) => {
        const result = await updateCompany(companyId, body)
        if (result.ok) await load()
        return result
    }, [load])

    return { companies, isLoading, create, update, refetch: load }
}
