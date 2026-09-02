import { useCallback, useEffect, useState } from 'react'
import type { Jobsite } from '../types'
import { fetchJobsites, createJobsite, updateJobsite, type JobsiteInput } from '../lib/api'

/** Jobsite management: the operator's company jobsites that foremen pick on WhatsApp. */
export function useJobsites() {
    const [jobsites, setJobsites] = useState<Jobsite[]>([])
    const [isLoading, setIsLoading] = useState(true)

    const load = useCallback(async () => {
        try {
            setJobsites(await fetchJobsites())
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

    const create = useCallback(async (body: JobsiteInput) => {
        const result = await createJobsite(body)
        if (result.ok) await load()
        return result
    }, [load])

    const update = useCallback(async (jobId: string, body: Partial<JobsiteInput>) => {
        const result = await updateJobsite(jobId, body)
        if (result.ok) await load()
        return result
    }, [load])

    return { jobsites, isLoading, create, update, refetch: load }
}
