import React, { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { api } from '../api/client'
import type { TraceDetail } from '../types'
import { SpanTree } from './SpanTree'
import { formatDistanceToNow } from 'date-fns'

interface TraceDetailModalProps {
  runId: string
  onClose: () => void
}

export function TraceDetailModal({ runId, onClose }: TraceDetailModalProps) {
  const [trace, setTrace] = useState<TraceDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedSpan, setSelectedSpan] = useState<any>(null)

  useEffect(() => {
    const fetchTrace = async () => {
      try {
        const data = await api.getTraceDetail(runId)
        setTrace(data)
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load trace')
      } finally {
        setLoading(false)
      }
    }

    fetchTrace()
  }, [runId])

  // Close on Escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (selectedSpan) {
          setSelectedSpan(null)
        } else {
          onClose()
        }
      }
    }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [onClose, selectedSpan])

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
        <div className="bg-white dark:bg-neutral-900 rounded-lg p-8">
          <div className="text-neutral-900 dark:text-neutral-100">Loading trace...</div>
        </div>
      </div>
    )
  }

  if (error || !trace) {
    return (
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
        <div className="bg-white dark:bg-neutral-900 rounded-lg p-8 max-w-md">
          <div className="text-red-600 dark:text-red-400 mb-4">
            {error || 'Trace not found'}
          </div>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-neutral-900 dark:bg-white text-white dark:text-neutral-900 rounded hover:bg-neutral-700 dark:hover:bg-neutral-200 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    )
  }

  return (
    <>
      {/* Main Modal */}
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
        <div className="bg-white dark:bg-neutral-900 rounded-lg shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col border border-neutral-200 dark:border-neutral-800">
          {/* Header */}
          <div className="flex items-start justify-between p-6 border-b border-neutral-200 dark:border-neutral-800">
            <div className="flex-1">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
                {trace.agent_name}
              </h2>
              <div className="mt-2 flex items-center gap-4 text-sm text-neutral-500 dark:text-neutral-400">
                <span>Run ID: {trace.run_id.substring(0, 8)}</span>
                <span>•</span>
                <span>{formatDistanceToNow(new Date(trace.started_at), { addSuffix: true })}</span>
                <span>•</span>
                <span className={`font-medium ${
                  trace.status === 'completed'
                    ? 'text-green-600 dark:text-green-400'
                    : 'text-red-600 dark:text-red-400'
                }`}>
                  {trace.status}
                </span>
              </div>
            </div>
            <button
              onClick={onClose}
              className="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200 transition-colors p-1"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Summary Stats */}
          <div className="grid grid-cols-5 gap-4 p-6 border-b border-neutral-200 dark:border-neutral-800">
            <div>
              <div className="text-xs text-neutral-500 dark:text-neutral-400 mb-1">Spans</div>
              <div className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
                {trace.total_spans}
              </div>
            </div>
            <div>
              <div className="text-xs text-neutral-500 dark:text-neutral-400 mb-1">Duration</div>
              <div className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
                {trace.duration_ms ? `${(trace.duration_ms / 1000).toFixed(2)}s` : '-'}
              </div>
            </div>
            <div>
              <div className="text-xs text-neutral-500 dark:text-neutral-400 mb-1">Cost</div>
              <div className="text-lg font-semibold font-mono text-neutral-900 dark:text-neutral-100">
                ${trace.total_cost_usd.toFixed(4)}
              </div>
            </div>
            <div>
              <div className="text-xs text-neutral-500 dark:text-neutral-400 mb-1">Anomalies</div>
              <div className={`text-lg font-semibold ${
                trace.anomaly_count > 0
                  ? 'text-amber-600 dark:text-amber-400'
                  : 'text-neutral-900 dark:text-neutral-100'
              }`}>
                {trace.anomaly_count}
              </div>
            </div>
            <div>
              <div className="text-xs text-neutral-500 dark:text-neutral-400 mb-1">Deviation</div>
              <div className={`text-lg font-semibold ${
                trace.baseline_deviation_score > 5
                  ? 'text-red-600 dark:text-red-400'
                  : trace.baseline_deviation_score > 2
                  ? 'text-amber-600 dark:text-amber-400'
                  : 'text-neutral-900 dark:text-neutral-100'
              }`}>
                {trace.baseline_deviation_score.toFixed(1)}
              </div>
            </div>
          </div>

          {/* LLM Summary */}
          {trace.llm_summary && (
            <div className="p-6 border-b border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-800/50">
              <div className="text-xs text-neutral-500 dark:text-neutral-400 mb-2">Summary</div>
              <div className="text-sm text-neutral-700 dark:text-neutral-300">
                {trace.llm_summary}
              </div>
            </div>
          )}

          {/* Span Tree */}
          <div className="flex-1 overflow-auto p-6">
            <div className="text-xs text-neutral-500 dark:text-neutral-400 mb-3">Execution Tree</div>
            <SpanTree spans={trace.span_tree} onSpanClick={setSelectedSpan} />
          </div>
        </div>
      </div>

      {/* Span Detail Drawer */}
      {selectedSpan && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
          onClick={() => setSelectedSpan(null)}
        >
          <div
            className="bg-white dark:bg-neutral-900 rounded-lg shadow-2xl max-w-2xl w-full max-h-[80vh] overflow-auto border border-neutral-200 dark:border-neutral-800"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6 border-b border-neutral-200 dark:border-neutral-800 flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-neutral-900 dark:text-neutral-100">
                  {selectedSpan.name}
                </div>
                <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                  {selectedSpan.span_type}
                </div>
              </div>
              <button
                onClick={() => setSelectedSpan(null)}
                className="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-4">
              {selectedSpan.input_data && (
                <div>
                  <div className="text-xs text-neutral-500 dark:text-neutral-400 mb-2">Input</div>
                  <pre className="bg-neutral-50 dark:bg-neutral-800 p-3 rounded text-xs overflow-auto max-h-48 text-neutral-900 dark:text-neutral-100">
                    {JSON.stringify(selectedSpan.input_data, null, 2)}
                  </pre>
                </div>
              )}

              {selectedSpan.output_data && (
                <div>
                  <div className="text-xs text-neutral-500 dark:text-neutral-400 mb-2">Output</div>
                  <pre className="bg-neutral-50 dark:bg-neutral-800 p-3 rounded text-xs overflow-auto max-h-48 text-neutral-900 dark:text-neutral-100">
                    {JSON.stringify(selectedSpan.output_data, null, 2)}
                  </pre>
                </div>
              )}

              {selectedSpan.anomaly_type && (
                <div>
                  <div className="text-xs text-neutral-500 dark:text-neutral-400 mb-2">Anomaly</div>
                  <div className="text-sm text-red-600 dark:text-red-400">
                    {selectedSpan.anomaly_description}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
