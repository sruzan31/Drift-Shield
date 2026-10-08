/**
 * REST API client for DriftShield backend.
 */

import type {
  ControlRequest,
  ControlResponse,
  CreateCSVRunRequest,
  CreateRunRequest,
  CSVValidationResponse,
  HealthStatus,
  IncidentItem,
  PaginatedResponse,
  RunDetail,
  RunSummary,
} from '../types';

export const API_BASE_URL =
  (import.meta.env.VITE_API_URL as string) || '';

class ApiError extends Error {
  status: number;
  data: any;

  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  try {
    const res = await fetch(url, { ...options, headers });
    if (!res.ok) {
      let errorData;
      try {
        errorData = await res.json();
      } catch {
        errorData = { detail: res.statusText };
      }
      throw new ApiError(
        errorData?.detail || errorData?.error || `HTTP ${res.status}: ${res.statusText}`,
        res.status,
        errorData
      );
    }
    return (await res.json()) as T;
  } catch (err: any) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(err?.message || 'Network connection failed', 0);
  }
}

export const api = {
  getHealth: (): Promise<HealthStatus> => request<HealthStatus>('/health'),

  getRuns: (page = 1, pageSize = 20): Promise<PaginatedResponse<RunSummary>> =>
    request<PaginatedResponse<RunSummary>>(`/api/runs?page=${page}&page_size=${pageSize}`),

  getRunDetail: (runId: string): Promise<RunDetail> =>
    request<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`),

  createRun: (data: CreateRunRequest): Promise<RunSummary> =>
    request<RunSummary>('/api/runs', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  validateCSV: (csvContent: string): Promise<CSVValidationResponse> => {
    const formData = new FormData();
    formData.append('csv_content', csvContent);
    return fetch(`${API_BASE_URL}/api/runs/validate-csv`, {
      method: 'POST',
      body: formData,
    }).then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'CSV validation failed');
      }
      return res.json();
    });
  },

  createCSVRun: (data: CreateCSVRunRequest): Promise<RunSummary> =>
    request<RunSummary>('/api/runs/csv-replay', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  controlRun: (runId: string, action: ControlRequest['action'], eventsPerSecond?: number): Promise<ControlResponse> =>
    request<ControlResponse>(`/api/runs/${encodeURIComponent(runId)}/control`, {
      method: 'POST',
      body: JSON.stringify({
        action,
        events_per_second: eventsPerSecond,
      }),
    }),

  getIncidents: (runId: string, page = 1, pageSize = 20): Promise<PaginatedResponse<IncidentItem>> =>
    request<PaginatedResponse<IncidentItem>>(
      `/api/runs/${encodeURIComponent(runId)}/incidents?page=${page}&page_size=${pageSize}`
    ),

  getEventPrediction: (runId: string, eventId: string): Promise<any> =>
    request<any>(
      `/api/runs/${encodeURIComponent(runId)}/events/${encodeURIComponent(eventId)}`
    ),

  // Theory Lab Endpoints
  createTheoryExperiment: (data: any): Promise<any> =>
    request<any>('/api/theory/experiments', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getTheoryExperiments: (limit = 20, offset = 0): Promise<any> =>
    request<any>(`/api/theory/experiments?limit=${limit}&offset=${offset}`),

  getTheoryExperiment: (id: string): Promise<any> =>
    request<any>(`/api/theory/experiments/${encodeURIComponent(id)}`),

  getTheoryExperimentResults: (id: string): Promise<any> =>
    request<any>(`/api/theory/experiments/${encodeURIComponent(id)}/results`),

  getTheoryExportUrl: (id: string, format: 'json' | 'csv' = 'json'): string =>
    `${API_BASE_URL}/api/theory/experiments/${encodeURIComponent(id)}/export?format=${format}`,
};
