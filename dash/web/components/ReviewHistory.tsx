import React from 'react'
import { Clock, CheckCircle, XCircle, Loader } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import type { ReviewHistoryItem } from '../types'

interface ReviewHistoryProps {
  reviews: ReviewHistoryItem[]
}

const statusIcons = {
  completed: CheckCircle,
  failed: XCircle,
  processing: Loader,
  queued: Clock,
}

const statusColors = {
  completed: 'text-green-400',
  failed: 'text-red-400',
  processing: 'text-blue-400',
  queued: 'text-yellow-400',
}

export function ReviewHistory({ reviews }: ReviewHistoryProps) {
  return (
    <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
      <h2 className="text-xl font-bold text-white mb-4 flex items-center">
        <Clock className="w-5 h-5 mr-2 text-green-400" />
        Recent Reviews
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="text-left text-slate-400 text-sm border-b border-slate-700">
              <th className="pb-3 font-medium">Repository</th>
              <th className="pb-3 font-medium">PR</th>
              <th className="pb-3 font-medium">Status</th>
              <th className="pb-3 font-medium">Time</th>
              <th className="pb-3 font-medium">Tokens</th>
              <th className="pb-3 font-medium">Cost</th>
            </tr>
          </thead>
          <tbody className="text-sm">
            {reviews.slice(0, 10).map((review) => {
              const StatusIcon = statusIcons[review.status as keyof typeof statusIcons] || Clock
              const colorClass = statusColors[review.status as keyof typeof statusColors] || 'text-slate-400'

              return (
                <tr
                  key={review.review_id}
                  className="border-b border-slate-700/50 hover:bg-slate-900/50 transition-colors"
                >
                  <td className="py-3 text-white">
                    <a
                      href={review.pr_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:text-blue-400 transition-colors"
                    >
                      {review.repo_name}
                    </a>
                  </td>
                  <td className="py-3 text-slate-300">#{review.pr_number}</td>
                  <td className="py-3">
                    <div className="flex items-center space-x-2">
                      <StatusIcon className={`w-4 h-4 ${colorClass}`} />
                      <span className={colorClass}>{review.status}</span>
                    </div>
                  </td>
                  <td className="py-3 text-slate-400">
                    {review.processing_time
                      ? `${review.processing_time.toFixed(1)}s`
                      : formatDistanceToNow(new Date(review.created_at), { addSuffix: true })}
                  </td>
                  <td className="py-3 text-slate-300">
                    {review.tokens_used ? review.tokens_used.toLocaleString() : '-'}
                  </td>
                  <td className="py-3 text-slate-300">
                    {review.estimated_cost ? `$${review.estimated_cost.toFixed(4)}` : '-'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
