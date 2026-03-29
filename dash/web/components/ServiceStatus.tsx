import React from "react";
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
  healthy: "text-green-600 dark:text-green-400",
  degraded: "text-amber-600 dark:text-amber-400",
  down: "text-red-600 dark:text-red-400",
  unknown: "text-neutral-400",
};

const activityColors = {
  idle: "text-green-600 dark:text-green-400",
  busy: "text-amber-600 dark:text-amber-400",
};

export function ServiceStatus({ services }: ServiceStatusProps) {
  return (
    <div className="bg-white dark:bg-neutral-900 rounded-lg p-6 border border-neutral-200 dark:border-neutral-800">
      <h2 className="text-sm font-medium text-neutral-900 dark:text-neutral-100 mb-4 flex items-center">
        <Activity className="w-4 h-4 mr-2 text-neutral-600 dark:text-neutral-400" />
        Service Health
      </h2>
      <div className="space-y-2">
        {services.map((service) => {
          const StatusIcon = statusIcons[service.status];
          const colorClass = statusColors[service.status];

          return (
            <div
              key={`${service.service_name}-${service.instance_id}`}
              className="flex items-center justify-between p-4 bg-neutral-50 dark:bg-neutral-800/50 rounded border border-neutral-200 dark:border-neutral-800 hover:border-neutral-300 dark:hover:border-neutral-700 transition-colors"
            >
              <div className="flex items-center space-x-3">
                <StatusIcon className={`w-5 h-5 ${colorClass}`} />
                <div>
                  <p className="text-sm font-medium text-neutral-900 dark:text-neutral-100">
                    {service.service_name}
                  </p>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400">
                    {service.instance_id}
                  </p>
                </div>
              </div>
              <div className="text-right space-y-1">
                <div className="flex items-center justify-end gap-2">
                  <span className={`text-xs font-medium px-2 py-1 rounded ${colorClass} bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700`}>
                    {service.status.toUpperCase()}
                  </span>
                  {service.activity != null && (
                    <span className={`text-xs font-medium px-2 py-1 rounded ${activityColors[service.activity]} bg-white dark:bg-neutral-800 border ${
                      service.activity === 'busy'
                        ? 'border-amber-300 dark:border-amber-700 animate-pulse'
                        : 'border-green-300 dark:border-green-700'
                    }`}>
                      {service.activity.toUpperCase()}
                    </span>
                  )}
                </div>
                {service.uptime_seconds != null && (
                  <p className="text-xs text-neutral-500 dark:text-neutral-400">
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
