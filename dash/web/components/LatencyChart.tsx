import React from 'react'
import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import type { LatencyMetrics } from '../types'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
)

interface LatencyChartProps {
  metrics: LatencyMetrics[]
}

export function LatencyChart({ metrics }: LatencyChartProps) {
  const chartData = {
    labels: metrics.map((m) => m.service),
    datasets: [
      {
        label: 'p50 (ms)',
        data: metrics.map((m) => m.p50_ms),
        borderColor: 'rgb(59, 130, 246)',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        fill: true,
      },
      {
        label: 'p95 (ms)',
        data: metrics.map((m) => m.p95_ms),
        borderColor: 'rgb(251, 191, 36)',
        backgroundColor: 'rgba(251, 191, 36, 0.1)',
        fill: true,
      },
      {
        label: 'p99 (ms)',
        data: metrics.map((m) => m.p99_ms),
        borderColor: 'rgb(239, 68, 68)',
        backgroundColor: 'rgba(239, 68, 68, 0.1)',
        fill: true,
      },
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top' as const,
        labels: {
          color: '#94a3b8',
        },
      },
      title: {
        display: true,
        text: 'Latency Percentiles by Service',
        color: '#e2e8f0',
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: {
          color: '#64748b',
        },
        grid: {
          color: 'rgba(148, 163, 184, 0.1)',
        },
      },
      x: {
        ticks: {
          color: '#64748b',
        },
        grid: {
          color: 'rgba(148, 163, 184, 0.1)',
        },
      },
    },
  }

  return (
    <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
      <div style={{ height: '300px' }}>
        <Line data={chartData} options={options} />
      </div>
    </div>
  )
}
