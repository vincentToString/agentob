import React from 'react'
import { Inbox, Users } from 'lucide-react'
import type { QueueStats } from '../types'

interface QueueMetricsProps {
  queues: QueueStats[]
}

export function QueueMetrics({ queues }: QueueMetricsProps) {
  return (
    <div className="bg-white dark:bg-neutral-900 rounded-lg p-6 border border-neutral-200 dark:border-neutral-800">
      <h2 className="text-sm font-medium text-neutral-900 dark:text-neutral-100 mb-4 flex items-center">
        <Inbox className="w-4 h-4 mr-2 text-neutral-600 dark:text-neutral-400" />
        Queue Status
      </h2>
      <div className="space-y-3">
        {queues.map((queue) => (
          <div key={queue.queue_name} className="bg-neutral-50 dark:bg-neutral-800/50 rounded border border-neutral-200 dark:border-neutral-800 p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-neutral-900 dark:text-neutral-100">{queue.queue_name}</h3>
              <div className="flex items-center text-neutral-500 dark:text-neutral-400 text-xs">
                <Users className="w-3 h-3 mr-1" />
                {queue.consumers} consumer{queue.consumers !== 1 ? 's' : ''}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div>
                <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-1">Ready</p>
                <p className="text-lg font-semibold text-amber-600 dark:text-amber-400">{queue.messages_ready}</p>
              </div>
              <div>
                <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-1">Processing</p>
                <p className="text-lg font-semibold text-blue-600 dark:text-blue-400">{queue.messages_unacked}</p>
              </div>
              <div>
                <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-1">Total</p>
                <p className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">{queue.messages_total}</p>
              </div>
            </div>

            {queue.avg_processing_time && (
              <div className="mt-3 pt-3 border-t border-neutral-200 dark:border-neutral-800">
                <p className="text-xs text-neutral-500 dark:text-neutral-400">Avg Processing Time</p>
                <p className="text-sm font-medium text-neutral-900 dark:text-neutral-100">
                  {queue.avg_processing_time.toFixed(2)}s
                </p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
