import { useState, useEffect } from 'react'
import { api } from '../api/client'
import type { DashboardOverview } from '../types'

export function useDashboardData(refreshInterval = 5000) {
  const [data, setData] = useState<DashboardOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const overview = await api.getOverview()
        setData(overview)
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch data')
      } finally {
        setLoading(false)
      }
    }

    fetchData()
    const interval = setInterval(fetchData, refreshInterval)

    return () => clearInterval(interval)
  }, [refreshInterval])

  return { data, loading, error }
}
