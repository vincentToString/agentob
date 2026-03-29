import React, { useState } from 'react'
import { ChevronRight, ChevronDown } from 'lucide-react'

interface SpanNode {
  span_id: string
  parent_span_id: string | null
  span_type: string
  name: string
  duration_ms: number | null
  cost_usd: number | null
  tokens_input: number | null
  tokens_output: number | null
  tool_name: string | null
  tool_status: string | null
  is_anomalous: boolean
  anomaly_type: string | null
  depth: number
  children: SpanNode[]
}

interface SpanTreeProps {
  spans: SpanNode[]
  onSpanClick?: (span: SpanNode) => void
}

function SpanTreeNode({
  span,
  depth,
  onSpanClick,
}: {
  span: SpanNode
  depth: number
  onSpanClick?: (span: SpanNode) => void
}) {
  const [isExpanded, setIsExpanded] = useState(depth < 2) // Auto-expand first 2 levels

  const hasChildren = span.children && span.children.length > 0

  const typeColors: Record<string, string> = {
    llm_call: 'text-blue-600 dark:text-blue-400',
    tool_use: 'text-purple-600 dark:text-purple-400',
    decision: 'text-indigo-600 dark:text-indigo-400',
    retrieval: 'text-cyan-600 dark:text-cyan-400',
    error: 'text-red-600 dark:text-red-400',
    custom: 'text-neutral-600 dark:text-neutral-400',
  }

  const typeColor = typeColors[span.span_type] || typeColors.custom

  return (
    <div>
      <div
        className={`flex items-center py-1.5 px-3 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 rounded transition-colors group ${
          span.is_anomalous ? 'bg-red-50/50 dark:bg-red-900/10' : ''
        }`}
        style={{ paddingLeft: `${depth * 24 + 12}px` }}
      >
        {/* Expand/Collapse Button */}
        <button
          onClick={(e) => {
            e.stopPropagation()
            if (hasChildren) setIsExpanded(!isExpanded)
          }}
          className={`mr-2 ${hasChildren ? 'opacity-100' : 'opacity-0'}`}
        >
          {hasChildren &&
            (isExpanded ? (
              <ChevronDown className="w-4 h-4 text-neutral-400" />
            ) : (
              <ChevronRight className="w-4 h-4 text-neutral-400" />
            ))}
        </button>

        {/* Span Info */}
        <div
          className="flex-1 flex items-center gap-3 min-w-0 cursor-pointer"
          onClick={() => onSpanClick?.(span)}
        >
          <span className={`text-xs font-medium ${typeColor} shrink-0`}>
            {span.span_type}
          </span>
          <span className="text-sm text-neutral-900 dark:text-neutral-100 truncate font-medium">
            {span.name}
          </span>
        </div>

        {/* Metrics */}
        <div className="flex items-center gap-4 text-xs text-neutral-500 dark:text-neutral-400 ml-4">
          {span.duration_ms && (
            <span className="font-mono">{span.duration_ms}ms</span>
          )}
          {span.cost_usd && (
            <span className="font-mono text-neutral-600 dark:text-neutral-300">
              ${span.cost_usd.toFixed(4)}
            </span>
          )}
          {span.tool_status && (
            <span
              className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                span.tool_status === 'success'
                  ? 'text-green-700 bg-green-50 dark:text-green-400 dark:bg-green-900/20'
                  : span.tool_status === 'error'
                  ? 'text-red-700 bg-red-50 dark:text-red-400 dark:bg-red-900/20'
                  : 'text-neutral-600 bg-neutral-100 dark:text-neutral-400 dark:bg-neutral-800'
              }`}
            >
              {span.tool_status}
            </span>
          )}
          {span.is_anomalous && (
            <span className="text-red-600 dark:text-red-400 font-medium">⚠</span>
          )}
        </div>
      </div>

      {/* Children */}
      {hasChildren && isExpanded && (
        <div>
          {span.children.map((child) => (
            <SpanTreeNode
              key={child.span_id}
              span={child}
              depth={depth + 1}
              onSpanClick={onSpanClick}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export function SpanTree({ spans, onSpanClick }: SpanTreeProps) {
  if (!spans || spans.length === 0) {
    return (
      <div className="text-center py-12 text-neutral-400">
        No span data available
      </div>
    )
  }

  return (
    <div className="space-y-0.5">
      {spans.map((span) => (
        <SpanTreeNode
          key={span.span_id}
          span={span}
          depth={0}
          onSpanClick={onSpanClick}
        />
      ))}
    </div>
  )
}
