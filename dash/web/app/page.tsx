"use client";
import { useState } from "react";
import { Activity, Clock, TrendingUp, DollarSign, Zap } from "lucide-react";
import { useDashboardData } from "../hooks/useDashboardData";
import { StatCard } from "../components/StatCard";
import { ServiceStatus } from "../components/ServiceStatus";
import { QueueMetrics } from "../components/QueueMetrics";
import { TraceList } from "../components/TraceList";
import { TraceDetailModal } from "../components/TraceDetailModal";

type Tab = "traces" | "infrastructure";

export default function Home() {
  const { data, loading, error } = useDashboardData(5000);
  const [activeTab, setActiveTab] = useState<Tab>("traces");
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);

  if (loading && !data) {
    return (
      <div className="min-h-screen bg-white dark:bg-neutral-950 flex items-center justify-center">
        <div className="text-center">
          <Activity className="w-8 h-8 text-neutral-400 animate-spin mx-auto mb-4" />
          <p className="text-neutral-500 dark:text-neutral-400 text-sm">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-white dark:bg-neutral-950 flex items-center justify-center">
        <div className="text-center max-w-md">
          <div className="bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 p-4 rounded-lg mb-4 border border-red-200 dark:border-red-900">
            <p className="font-medium">Failed to load dashboard</p>
            <p className="text-sm mt-2">{error}</p>
          </div>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-neutral-900 dark:bg-white text-white dark:text-neutral-900 rounded hover:bg-neutral-700 dark:hover:bg-neutral-200 transition-colors text-sm font-medium"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="min-h-screen bg-white dark:bg-neutral-950 text-neutral-900 dark:text-neutral-100">
      {/* Header */}
      <header className="border-b border-neutral-200 dark:border-neutral-800 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">AgentOB</h1>
            <p className="text-neutral-500 dark:text-neutral-400 text-sm mt-0.5">
              Agent Observability Platform
            </p>
          </div>
          <div className="text-right">
            <p className="text-neutral-500 dark:text-neutral-400 text-xs">Last updated</p>
            <p className="text-neutral-900 dark:text-neutral-100 font-medium text-sm">
              {new Date(data.timestamp).toLocaleTimeString()}
            </p>
          </div>
        </div>
      </header>

      {/* Tab Navigation */}
      <div className="border-b border-neutral-200 dark:border-neutral-800">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex gap-8">
            <button
              onClick={() => setActiveTab("traces")}
              className={`py-4 text-sm font-medium border-b-2 transition-colors ${
                activeTab === "traces"
                  ? "border-neutral-900 dark:border-white text-neutral-900 dark:text-white"
                  : "border-transparent text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300"
              }`}
            >
              Traces
            </button>
            <button
              onClick={() => setActiveTab("infrastructure")}
              className={`py-4 text-sm font-medium border-b-2 transition-colors ${
                activeTab === "infrastructure"
                  ? "border-neutral-900 dark:border-white text-neutral-900 dark:text-white"
                  : "border-transparent text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300"
              }`}
            >
              Infrastructure
            </button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {activeTab === "traces" ? (
          <>
            {/* Top Stats Row */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
              <StatCard
                title="Traces Today"
                value={data.total_reviews_today}
                icon={Activity}
                color="neutral"
              />
              <StatCard
                title="Success Rate"
                value={`${data.success_rate_24h.toFixed(1)}%`}
                icon={TrendingUp}
                color="green"
                subtitle="Last 24h"
              />
              <StatCard
                title="Avg Processing"
                value={`${data.avg_processing_time_24h.toFixed(1)}s`}
                icon={Clock}
                color="neutral"
              />
              <StatCard
                title="Cost Today"
                value={`$${data.total_cost_today.toFixed(2)}`}
                icon={DollarSign}
                color="neutral"
              />
              <StatCard
                title="Weekly Traces"
                value={data.total_reviews_week}
                icon={Zap}
                color="neutral"
                subtitle="Last 7 days"
              />
            </div>

            {/* Alerts Section */}
            {data.recent_alerts && data.recent_alerts.length > 0 && (
              <div className="mb-8">
                <h2 className="text-sm font-medium text-neutral-900 dark:text-neutral-100 mb-3">
                  Recent Alerts
                </h2>
                <div className="space-y-2">
                  {data.recent_alerts.slice(0, 5).map((alert) => (
                    <div
                      key={alert.alert_id}
                      className={`p-4 rounded-lg border ${
                        alert.severity === 'critical'
                          ? 'bg-red-50 dark:bg-red-900/10 border-red-200 dark:border-red-900/50'
                          : alert.severity === 'warning'
                          ? 'bg-amber-50 dark:bg-amber-900/10 border-amber-200 dark:border-amber-900/50'
                          : 'bg-neutral-50 dark:bg-neutral-900 border-neutral-200 dark:border-neutral-800'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div>
                          <div className="text-sm font-medium text-neutral-900 dark:text-neutral-100">
                            {alert.title}
                          </div>
                          {alert.description && (
                            <div className="text-xs text-neutral-600 dark:text-neutral-400 mt-1">
                              {alert.description}
                            </div>
                          )}
                        </div>
                        <span
                          className={`text-xs px-2 py-1 rounded font-medium ${
                            alert.severity === 'critical'
                              ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
                              : alert.severity === 'warning'
                              ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400'
                              : 'bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-400'
                          }`}
                        >
                          {alert.severity}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Trace List */}
            <div>
              <h2 className="text-sm font-medium text-neutral-900 dark:text-neutral-100 mb-3">
                Recent Traces
              </h2>
              <TraceList
                traces={data.recent_traces || []}
                onTraceClick={setSelectedTraceId}
              />
            </div>
          </>
        ) : (
          <>
            {/* Service & Queue Status */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <ServiceStatus services={data.services} />
              <QueueMetrics queues={data.queues} />
            </div>
          </>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-neutral-200 dark:border-neutral-800 px-6 py-4 mt-12">
        <div className="max-w-7xl mx-auto text-center text-neutral-500 dark:text-neutral-400 text-xs">
          <p>AgentOB v0.1.0 • Auto-refresh every 5s</p>
        </div>
      </footer>

      {/* Trace Detail Modal */}
      {selectedTraceId && (
        <TraceDetailModal
          runId={selectedTraceId}
          onClose={() => setSelectedTraceId(null)}
        />
      )}
    </div>
  );
}
