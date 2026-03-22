import React from 'react'
import { DollarSign, Zap } from 'lucide-react'
import type { TokenEstimate } from '../types'

interface TokenEstimatesProps {
  estimates: TokenEstimate[]
}

export function TokenEstimates({ estimates }: TokenEstimatesProps) {
  const totalTokens = estimates.reduce((sum, e) => sum + e.estimated_tokens_in_queue, 0)
  const totalCost = estimates.reduce((sum, e) => sum + e.estimated_cost_usd, 0)

  return (
    <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
      <h2 className="text-xl font-bold text-white mb-4 flex items-center">
        <Zap className="w-5 h-5 mr-2 text-yellow-400" />
        Token Estimates
      </h2>

      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="bg-slate-900/50 rounded-lg p-4">
          <p className="text-slate-400 text-sm mb-1">Total Tokens in Queue</p>
          <p className="text-2xl font-bold text-yellow-400">{totalTokens.toLocaleString()}</p>
        </div>
        <div className="bg-slate-900/50 rounded-lg p-4">
          <p className="text-slate-400 text-sm mb-1">Estimated Cost</p>
          <p className="text-2xl font-bold text-green-400">${totalCost.toFixed(4)}</p>
        </div>
      </div>

      <div className="space-y-3">
        {estimates.map((estimate) => (
          <div
            key={estimate.queue_name}
            className="flex items-center justify-between p-3 bg-slate-900/50 rounded-lg"
          >
            <div>
              <p className="text-white font-medium">{estimate.queue_name}</p>
              <p className="text-slate-400 text-sm">
                Avg: {estimate.avg_tokens_per_review.toLocaleString()} tokens/review
              </p>
            </div>
            <div className="text-right">
              <p className="text-yellow-400 font-medium">
                {estimate.estimated_tokens_in_queue.toLocaleString()}
              </p>
              <p className="text-slate-500 text-sm">${estimate.estimated_cost_usd.toFixed(4)}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
