import React from 'react'
import { LucideIcon } from 'lucide-react'

interface StatCardProps {
  title: string
  value: string | number
  icon: LucideIcon
  trend?: {
    value: number
    isPositive: boolean
  }
  subtitle?: string
  color?: 'blue' | 'green' | 'yellow' | 'red' | 'purple' | 'neutral'
}

const colorClasses = {
  blue: 'bg-blue-500/10 text-blue-600 dark:bg-blue-500/20 dark:text-blue-400',
  green: 'bg-green-500/10 text-green-600 dark:bg-green-500/20 dark:text-green-400',
  yellow: 'bg-yellow-500/10 text-yellow-600 dark:bg-yellow-500/20 dark:text-yellow-400',
  red: 'bg-red-500/10 text-red-600 dark:bg-red-500/20 dark:text-red-400',
  purple: 'bg-purple-500/10 text-purple-600 dark:bg-purple-500/20 dark:text-purple-400',
  neutral: 'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400',
}

export function StatCard({ title, value, icon: Icon, trend, subtitle, color = 'neutral' }: StatCardProps) {
  return (
    <div className="bg-white dark:bg-neutral-900 rounded-lg p-6 border border-neutral-200 dark:border-neutral-800 hover:border-neutral-300 dark:hover:border-neutral-700 transition-colors">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-neutral-500 dark:text-neutral-400 text-sm font-medium mb-1">{title}</p>
          <p className="text-3xl font-bold text-neutral-900 dark:text-neutral-100 mb-1">{value}</p>
          {subtitle && <p className="text-neutral-400 dark:text-neutral-500 text-xs">{subtitle}</p>}
          {trend && (
            <div className={`flex items-center mt-2 text-sm ${trend.isPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
              <span>{trend.isPositive ? '↑' : '↓'}</span>
              <span className="ml-1">{Math.abs(trend.value)}%</span>
            </div>
          )}
        </div>
        <div className={`p-3 rounded-lg ${colorClasses[color]}`}>
          <Icon className="w-6 h-6" />
        </div>
      </div>
    </div>
  )
}
