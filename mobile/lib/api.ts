import axios, { type AxiosRequestConfig } from "axios";

import { useAuth } from "@/lib/auth";
import { useAppConfig } from "@/lib/config";
import type {
  AgentRunResult,
  Bill,
  BillStats,
  InsightsResponse,
  SpendStats,
  StatementAnalysisResponse,
  SyncResult,
  Transaction,
  TransactionSyncResult,
  UploadableDocument,
} from "@/lib/types";

type ApiRequestConfig = AxiosRequestConfig & {
  timeoutMs?: number;
};

function guessMimeType(name: string) {
  if (name.toLowerCase().endsWith(".pdf")) {
    return "application/pdf";
  }
  return "text/csv";
}

export function formatApiError(error: unknown) {
  if (axios.isAxiosError(error)) {
    const responseData = error.response?.data as { detail?: string } | undefined;
    return responseData?.detail || error.message || "Request failed.";
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Something went wrong.";
}

export function useApi() {
  const { apiBaseUrl } = useAppConfig();
  const { token } = useAuth();

  async function request<T>(config: ApiRequestConfig) {
    const { timeoutMs, headers, ...axiosConfig } = config;
    const response = await axios.request<T>({
      baseURL: apiBaseUrl,
      headers: {
        Accept: "application/json",
        ...(axiosConfig.data instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      timeout: timeoutMs ?? 60_000,
      ...axiosConfig,
    });
    return response.data;
  }

  return {
    billsApi: {
      list: (params?: { status?: string; overpriced?: boolean; limit?: number }) =>
        request<Bill[]>({ url: "/api/v1/bills", method: "GET", params }),
      stats: () => request<BillStats>({ url: "/api/v1/bills/stats", method: "GET" }),
      get: (id: string) => request<Bill>({ url: `/api/v1/bills/${id}`, method: "GET" }),
      markPaid: (id: string) =>
        request<Bill>({ url: `/api/v1/bills/${id}/mark-paid`, method: "POST" }),
      runAgent: (id: string) =>
        request<AgentRunResult>({ url: `/api/v1/bills/${id}/run-agent`, method: "POST" }),
      runAllPending: () =>
        request<AgentRunResult[]>({
          url: "/api/v1/bills/run-all-pending",
          method: "POST",
        }),
    },
    ingestionApi: {
      sync: () => request<SyncResult>({ url: "/api/v1/ingestion/sync", method: "POST" }),
    },
    transactionsApi: {
      list: (params?: {
        type?: string;
        category?: string;
        date_from?: string;
        date_to?: string;
        limit?: number;
      }) => request<Transaction[]>({ url: "/api/v1/transactions", method: "GET", params }),
      stats: (days = 30) =>
        request<SpendStats>({
          url: "/api/v1/transactions/stats",
          method: "GET",
          params: { days },
        }),
      insights: (days = 30) =>
        request<InsightsResponse>({
          url: "/api/v1/transactions/insights",
          method: "GET",
          params: { days },
        }),
      sync: () =>
        request<TransactionSyncResult>({
          url: "/api/v1/ingestion/transactions/sync",
          method: "POST",
          timeoutMs: 300_000,
        }),
      delete: (id: number) =>
        request<void>({ url: `/api/v1/transactions/${id}`, method: "DELETE" }),
    },
    statementsApi: {
      analyze: (file: UploadableDocument) => {
        const formData = new FormData();
        formData.append(
          "file",
          {
            uri: file.uri,
            name: file.name,
            type: file.mimeType || guessMimeType(file.name),
          } as never
        );
        return request<StatementAnalysisResponse>({
          url: "/api/v1/statements/analyze",
          method: "POST",
          data: formData,
        });
      },
    },
    healthApi: {
      check: () =>
        request<{ status?: string; [key: string]: unknown }>({
          url: "/health",
          method: "GET",
        }),
    },
  };
}
