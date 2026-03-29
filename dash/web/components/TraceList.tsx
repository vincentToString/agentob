import React from 'react'
import { formatDistanceToNow } from 'date-fns'
import type { TraceListItem } from '../types'

interface TraceListProps {
  traces: TraceListItem[]
  onTraceClick: (runId: string) => void
}

export function TraceList({ traces, onTraceClick }: TraceListProps) {
  return (
    <div className="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-800 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 border-b border-neutral-200 dark:border-neutral-800">
              <th className="px-6 py-3">Agent</th>
              <th className="px-6 py-3">Status</th>
              <th className="px-6 py-3">Spans</th>
              <th className="px-6 py-3">Duration</th>
              <th className="px-6 py-3">Cost</th>
              <th className="px-6 py-3">Anomalies</th>
              <th className="px-6 py-3">Deviation</th>
              <th className="px-6 py-3">Time</th>
            </tr>
          </thead>
          <tbody>
            {traces.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-6 py-12 text-center text-neutral-400">
                  No traces yet. Start sending agent traces to see them here.
                </td>
              </tr>
            ) : (
              traces.map((trace) => (
                <tr
                  key={trace.run_id}
                  onClick={() => onTraceClick(trace.run_id)}
                  className="border-b border-neutral-100 dark:border-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 cursor-pointer transition-colors"
                >
                  <td className="px-6 py-4">
                    <div className="font-medium text-neutral-900 dark:text-neutral-100">
                      {trace.agent_name}
                    </div>
                    {trace.agent_framework && (
                      <div className="text-xs text-neutral-500 dark:text-neutral-400">
                        {trace.agent_framework}
                      </div>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <span
                      className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${
                        trace.status === 'completed'
                          ? 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400'
                          : trace.status === 'failed'
                          ? 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400'
                          : 'bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300'
                      }`}
                    >
                      {trace.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-neutral-700 dark:text-neutral-300">
                    {trace.total_spans}
                  </td>
                  <td className="px-6 py-4 text-sm text-neutral-700 dark:text-neutral-300">
                    {trace.duration_ms ? `${(trace.duration_ms / 1000).toFixed(2)}s` : '-'}
                  </td>
                  <td className="px-6 py-4 text-sm font-mono text-neutral-700 dark:text-neutral-300">
                    ${trace.total_cost_usd.toFixed(4)}
                  </td>
                  <td className="px-6 py-4">
                    {trace.anomaly_count > 0 ? (
                      <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400">
                        {trace.anomaly_count}
                      </span>
                    ) : (
                      <span className="text-neutral-400 text-sm">-</span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    {trace.baseline_deviation_score > 0 ? (
                      <span
                        className={`text-sm font-medium ${
                          trace.baseline_deviation_score > 5
                            ? 'text-red-600 dark:text-red-400'
                            : trace.baseline_deviation_score > 2
                            ? 'text-amber-600 dark:text-amber-400'
                            : 'text-neutral-500 dark:text-neutral-400'
                        }`}
                      >
                        {trace.baseline_deviation_score.toFixed(1)}
                      </span>
                    ) : (
                      <span className="text-neutral-400 text-sm">-</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-sm text-neutral-500 dark:text-neutral-400">
                    {formatDistanceToNow(new Date(trace.started_at), { addSuffix: true })}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
