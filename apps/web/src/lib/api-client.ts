/**
 * Typed API client for ThermalIntel Backend
 * Implements all 7 frozen API endpoints.
 */

import {
  HealthResponse,
  HotspotsResponse,
  IncidentDetail,
  SummaryResponse,
  AlertsResponse,
  SourcesResponse,
  RefreshRequest,
  RefreshResponse,
  HotspotFilterParams,
} from '../types/api';

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

class ThermalIntelApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
  }

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`API Error [${response.status}]: ${errorText || response.statusText}`);
    }

    return response.json() as Promise<T>;
  }

  /**
   * GET /api/health
   */
  async getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>('/health');
  }

  /**
   * GET /api/hotspots
   */
  async getHotspots(params?: HotspotFilterParams): Promise<HotspotsResponse> {
    const query = new URLSearchParams();
    if (params) {
      if (params.risk_level) query.append('risk_level', params.risk_level);
      if (params.source_type) query.append('source_type', params.source_type);
      if (params.min_frp !== undefined) query.append('min_frp', params.min_frp.toString());
      if (params.min_confidence) query.append('min_confidence', params.min_confidence);
      if (params.is_anomaly !== undefined) query.append('is_anomaly', params.is_anomaly.toString());
      if (params.cluster_id) query.append('cluster_id', params.cluster_id);
      if (params.page !== undefined) query.append('page', params.page.toString());
      if (params.page_size !== undefined) query.append('page_size', params.page_size.toString());
    }
    const qs = query.toString();
    return this.request<HotspotsResponse>(`/hotspots${qs ? `?${qs}` : ''}`);
  }

  /**
   * GET /api/hotspots/{id}
   */
  async getHotspotDetail(id: string): Promise<IncidentDetail> {
    return this.request<IncidentDetail>(`/hotspots/${encodeURIComponent(id)}`);
  }

  /**
   * GET /api/summary
   */
  async getSummary(): Promise<SummaryResponse> {
    return this.request<SummaryResponse>('/summary');
  }

  /**
   * GET /api/alerts
   */
  async getAlerts(severity?: string, unreadOnly: boolean = false): Promise<AlertsResponse> {
    const query = new URLSearchParams();
    if (severity) query.append('severity', severity);
    if (unreadOnly) query.append('unread_only', 'true');
    const qs = query.toString();
    return this.request<AlertsResponse>(`/alerts${qs ? `?${qs}` : ''}`);
  }

  /**
   * GET /api/sources
   */
  async getSources(): Promise<SourcesResponse> {
    return this.request<SourcesResponse>('/sources');
  }

  /**
   * POST /api/refresh
   */
  async refreshData(payload?: RefreshRequest): Promise<RefreshResponse> {
    return this.request<RefreshResponse>('/refresh', {
      method: 'POST',
      body: JSON.stringify(payload || { force_sample: false }),
    });
  }
}

export const apiClient = new ThermalIntelApiClient();
export default apiClient;
