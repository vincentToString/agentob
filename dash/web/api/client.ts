import axios from "axios";
import type { DashboardOverview, TraceListItem, TraceDetail, AlertItem } from "../types";

const API_BASE = "/api";

const client = axios.create({
  baseURL: API_BASE,
  timeout: 10000,
});

export const api = {
  // Main overview
  getOverview: async (): Promise<DashboardOverview> => {
    const { data } = await client.get<DashboardOverview>("/overview");
    return data;
  },

  // Trace endpoints
  getTraces: async (limit = 20, project_id?: string): Promise<TraceListItem[]> => {
    const { data } = await client.get<TraceListItem[]>("/traces", {
      params: { limit, project_id },
    });
    return data;
  },

  getTraceDetail: async (runId: string): Promise<TraceDetail> => {
    const { data } = await client.get<TraceDetail>(`/traces/${runId}`);
    return data;
  },

  getAlerts: async (limit = 50, severity?: string): Promise<AlertItem[]> => {
    const { data } = await client.get<AlertItem[]>("/alerts", {
      params: { limit, severity },
    });
    return data;
  },

  // Infrastructure endpoints
  getServices: async () => {
    const { data } = await client.get("/services");
    return data;
  },

  getQueues: async () => {
    const { data } = await client.get("/queues");
    return data;
  },

  getTokenEstimates: async () => {
    const { data } = await client.get("/tokens/estimates");
    return data;
  },

  getLatencyMetrics: async () => {
    const { data } = await client.get("/latency");
    return data;
  },
};
