import axios from "axios";
import type {
  Bill, BillStats, SyncResult, AgentRunResult,
  Transaction, SpendStats, InsightsResponse, TransactionSyncResult,
} from "@/types";

const DEV_TOKEN = import.meta.env.VITE_DEV_TOKEN || "";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
});

// Attach token on every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token") || DEV_TOKEN;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ─── Bills ────────────────────────────────────────────────────────────────────

export const billsApi = {
  list: (params?: { status?: string; overpriced?: boolean; limit?: number }) =>
    api.get<Bill[]>("/api/v1/bills", { params }).then((r) => r.data),

  stats: () => api.get<BillStats>("/api/v1/bills/stats").then((r) => r.data),

  get: (id: string) => api.get<Bill>(`/api/v1/bills/${id}`).then((r) => r.data),

  update: (id: string, data: Partial<Bill>) =>
    api.patch<Bill>(`/api/v1/bills/${id}`, data).then((r) => r.data),

  delete: (id: string) => api.delete(`/api/v1/bills/${id}`),

  markPaid: (id: string) =>
    api.post<Bill>(`/api/v1/bills/${id}/mark-paid`).then((r) => r.data),

  runAgent: (id: string) =>
    api.post<AgentRunResult>(`/api/v1/bills/${id}/run-agent`).then((r) => r.data),

  runAllPending: () =>
    api.post<AgentRunResult[]>("/api/v1/bills/run-all-pending").then((r) => r.data),
};

// ─── Ingestion ────────────────────────────────────────────────────────────────

export const ingestionApi = {
  sync: () => api.post<SyncResult>("/api/v1/ingestion/sync").then((r) => r.data),

  manualAdd: (data: {
    provider: string;
    amount: number;
    due_date: string;
    bill_type?: string;
    currency?: string;
  }) => api.post("/api/v1/ingestion/manual", null, { params: data }).then((r) => r.data),
};

// ─── Transactions ─────────────────────────────────────────────────────────────

export const transactionsApi = {
  list: (params?: { type?: string; category?: string; date_from?: string; date_to?: string; limit?: number }) =>
    api.get<Transaction[]>("/api/v1/transactions", { params }).then((r) => r.data),

  stats: (days = 30) =>
    api.get<SpendStats>("/api/v1/transactions/stats", { params: { days } }).then((r) => r.data),

  insights: (days = 30) =>
    api.get<InsightsResponse>("/api/v1/transactions/insights", { params: { days } }).then((r) => r.data),

  sync: () =>
    api.post<TransactionSyncResult>("/api/v1/ingestion/transactions/sync").then((r) => r.data),

  delete: (id: number) => api.delete(`/api/v1/transactions/${id}`),
};

// ─── Health ───────────────────────────────────────────────────────────────────

export const healthApi = {
  check: () => api.get("/health").then((r) => r.data),
};
