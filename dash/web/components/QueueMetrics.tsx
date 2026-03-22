import React from 'react'
import { Inbox, Users } from 'lucide-react'
import type { QueueStats } from '../types'

interface QueueMetricsProps {
  queues: QueueStats[]
}

export function QueueMetrics({ queues }: QueueMetricsProps) {
  return (
    <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
      <h2 className="text-xl font-bold text-white mb-4 flex items-center">
        <Inbox className="w-5 h-5 mr-2 text-purple-400" />
        Queue Status
      </h2>
      <div className="space-y-4">
        {queues.map((queue) => (
          <div key={queue.queue_name} className="bg-slate-900/50 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-white font-medium">{queue.queue_name}</h3>
              <div className="flex items-center text-slate-400 text-sm">
                <Users className="w-4 h-4 mr-1" />
                {queue.consumers} consumer{queue.consumers !== 1 ? 's' : ''}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div>
                <p className="text-slate-400 text-xs mb-1">Ready</p>
                <p className="text-xl font-bold text-yellow-400">{queue.messages_ready}</p>
              </div>
              <div>
                <p className="text-slate-400 text-xs mb-1">Processing</p>
                <p className="text-xl font-bold text-blue-400">{queue.messages_unacked}</p>
              </div>
              <div>
                <p className="text-slate-400 text-xs mb-1">Total</p>
                <p className="text-xl font-bold text-white">{queue.messages_total}</p>
              </div>
            </div>

            {queue.avg_processing_time && (
              <div className="mt-3 pt-3 border-t border-slate-700">
                <p className="text-slate-400 text-xs">Avg Processing Time</p>
                <p className="text-sm text-white">
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
