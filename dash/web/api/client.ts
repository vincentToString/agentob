import axios from "axios";
import type { DashboardOverview } from "../types";
//import.meta.env.VITE_API_BASE ||
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

  // Individual endpoints
  getServices: async () => {
    const { data } = await client.get("/services");
    return data;
  },

  getQueues: async () => {
    const { data } = await client.get("/queues");
    return data;
  },

  getRecentReviews: async (limit = 50) => {
    const { data } = await client.get("/reviews/recent", { params: { limit } });
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

  // Chart data
  getReviewsOverTime: async (hours = 24) => {
    const { data } = await client.get("/charts/reviews-over-time", {
      params: { hours },
    });
    return data;
  },

  getLatencyOverTime: async (hours = 24) => {
    const { data } = await client.get("/charts/latency-over-time", {
      params: { hours },
    });
    return data;
  },

  getCostOverTime: async (days = 7) => {
    const { data } = await client.get("/charts/cost-over-time", {
      params: { days },
    });
    return data;
  },
};
