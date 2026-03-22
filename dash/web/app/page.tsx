"use client";
import { Activity, Clock, TrendingUp, DollarSign, Zap } from "lucide-react";
import { useDashboardData } from "../hooks/useDashboardData";
import { StatCard } from "../components/StatCard";
import { ServiceStatus } from "../components/ServiceStatus";
import { QueueMetrics } from "../components/QueueMetrics";
import { ReviewHistory } from "../components/ReviewHistory";
import { TokenEstimates } from "../components/TokenEstimates";
import { LatencyChart } from "../components/LatencyChart";

export default function Home() {
  const { data, loading, error } = useDashboardData(5000);
  if (loading && !data) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="text-center">
          <Activity className="w-12 h-12 text-blue-400 animate-spin mx-auto mb-4" />
          <p className="text-slate-400">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="text-center max-w-md">
          <div className="bg-red-500/20 text-red-400 p-4 rounded-lg mb-4">
            <p className="font-medium">Failed to load dashboard</p>
            <p className="text-sm mt-2">{error}</p>
          </div>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="min-h-screen bg-slate-900 text-white">
      {/* Header */}
      <header className="bg-slate-800 border-b border-slate-700 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="text-3xl">🦉</div>
            <div>
              <h1 className="text-2xl font-bold">PROwl Dashboard</h1>
              <p className="text-slate-400 text-sm">
                Real-time monitoring & metrics
              </p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-slate-400 text-sm">Last updated</p>
            <p className="text-white font-medium">
              {new Date(data.timestamp).toLocaleTimeString()}
            </p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Top Stats Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
          <StatCard
            title="Reviews Today"
            value={data.total_reviews_today}
            icon={Activity}
            color="blue"
          />
          <StatCard
            title="Success Rate (24h)"
            value={`${data.success_rate_24h.toFixed(1)}%`}
            icon={TrendingUp}
            color="green"
            subtitle="Last 24 hours"
          />
          <StatCard
            title="Avg Processing Time"
            value={`${data.avg_processing_time_24h.toFixed(1)}s`}
            icon={Clock}
            color="purple"
          />
          <StatCard
            title="Cost Today"
            value={`$${data.total_cost_today.toFixed(2)}`}
            icon={DollarSign}
            color="yellow"
          />
          <StatCard
            title="Weekly Reviews"
            value={data.total_reviews_week}
            icon={Zap}
            color="blue"
            subtitle="Last 7 days"
          />
        </div>

        {/* Service & Queue Status */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <ServiceStatus services={data.services} />
          <QueueMetrics queues={data.queues} />
        </div>

        {/* Token Estimates & Latency Chart */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <TokenEstimates estimates={data.token_estimates} />
          <LatencyChart metrics={data.latency_metrics} />
        </div>

        {/* Review History */}
        <ReviewHistory reviews={data.recent_reviews} />
      </main>

      {/* Footer */}
      <footer className="bg-slate-800 border-t border-slate-700 px-6 py-4 mt-12">
        <div className="max-w-7xl mx-auto text-center text-slate-400 text-sm">
          <p>PROwl Dashboard v0.1.0 | Auto-refresh every 5s</p>
        </div>
      </footer>
    </div>
  );
}
