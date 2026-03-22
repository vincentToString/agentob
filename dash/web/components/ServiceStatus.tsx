import React, { act } from "react";
import { Activity, CheckCircle, XCircle, AlertCircle } from "lucide-react";
import type { ServiceInstance } from "../types";

interface ServiceStatusProps {
  services: ServiceInstance[];
}

const statusIcons = {
  healthy: CheckCircle,
  degraded: AlertCircle,
  down: XCircle,
  unknown: Activity,
};

const statusColors = {
  healthy: "text-green-400",
  degraded: "text-yellow-400",
  down: "text-red-400",
  unknown: "text-slate-400",
};

const activityColors = {
  idle: "text-green-400",
  busy: "text-yellow-400",
};

export function ServiceStatus({ services }: ServiceStatusProps) {
  return (
    <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
      <h2 className="text-xl font-bold text-white mb-4 flex items-center">
        <Activity className="w-5 h-5 mr-2 text-blue-400" />
        Service Health
      </h2>
      <div className="space-y-3">
        {services.map((service) => {
          const StatusIcon = statusIcons[service.status];
          const colorClass = statusColors[service.status];

          return (
            <div
              key={`${service.service_name}-${service.instance_id}`}
              className="flex items-center justify-between p-4 bg-slate-900/50 rounded-lg border border-slate-700/50 hover:border-slate-600/50 transition-colors"
            >
              <div className="flex items-center space-x-3">
                <StatusIcon className={`w-6 h-6 ${colorClass}`} />
                <div>
                  <p className="text-white font-semibold">
                    {service.service_name}
                  </p>
                  <p className="text-slate-400 text-xs">
                    {service.instance_id}
                  </p>
                </div>
              </div>
              <div className="text-right space-y-1">
                <div className="flex items-center justify-end gap-2">
                  <span className={`text-xs font-semibold px-2 py-1 rounded ${colorClass} bg-slate-800/80`}>
                    {service.status.toUpperCase()}
                  </span>
                  {service.activity != null && (
                    <span className={`text-xs font-semibold px-2 py-1 rounded ${activityColors[service.activity]} bg-slate-800/80 border ${
                      service.activity === 'busy' ? 'border-yellow-500/30 animate-pulse' : 'border-green-500/30'
                    }`}>
                      {service.activity.toUpperCase()}
                    </span>
                  )}
                </div>
                {service.uptime_seconds != null && (
                  <p className="text-slate-500 text-xs">
                    Uptime: {Math.floor(service.uptime_seconds / 3600)}h {Math.floor((service.uptime_seconds % 3600) / 60)}m
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
