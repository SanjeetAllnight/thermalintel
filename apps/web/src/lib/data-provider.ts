import apiClient from './api-client';
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
  DataMode,
} from '../types/api';
import {
  mockHealth,
  mockHotspots,
  mockIncidents,
  mockSummary,
  mockAlerts,
  mockSources,
} from './mock-data';

export type AppDataMode = 'auto' | 'live' | 'demo';

class DataProvider {
  private modePreference: AppDataMode = 'auto';
  private lastDetectedMode: DataMode = 'demo';
  private backendAvailable: boolean = false;

  constructor() {
    // Mode defaults to auto (check backend, fallback to demo if unreachable)
  }

  setModePreference(mode: AppDataMode) {
    this.modePreference = mode;
  }

  getModePreference(): AppDataMode {
    return this.modePreference;
  }

  getActiveDataMode(): DataMode {
    if (this.modePreference === 'demo') return 'demo';
    if (this.modePreference === 'live') return this.backendAvailable ? 'live' : 'demo';
    return this.lastDetectedMode;
  }

  isBackendAvailable(): boolean {
    return this.backendAvailable;
  }

  /**
   * Health Check & Mode Detection
   */
  async getHealth(): Promise<HealthResponse> {
    if (this.modePreference === 'demo') {
      this.lastDetectedMode = 'demo';
      return { ...mockHealth, data_mode: 'demo' };
    }

    try {
      const health = await apiClient.getHealth();
      this.backendAvailable = health?.status === 'ok';
      this.lastDetectedMode = health?.data_mode || 'live';
      return health;
    } catch {
      this.backendAvailable = false;
      this.lastDetectedMode = 'demo';
      return {
        ...mockHealth,
        data_mode: 'demo',
        services: {
          ...mockHealth.services,
          database: 'offline (falling back to local memory)',
          firms_api: 'offline (using local dataset)',
        },
      };
    }
  }

  /**
   * Hotspots Feed with in-memory filtering fallback
   */
  async getHotspots(params?: HotspotFilterParams): Promise<HotspotsResponse> {
    const activeMode = this.getActiveDataMode();

    if (activeMode === 'live' && this.backendAvailable) {
      try {
        return await apiClient.getHotspots(params);
      } catch (err) {
        console.warn('Live API getHotspots failed, falling back to mock provider:', err);
      }
    }

    // In-memory filter on mock data
    let filtered = [...mockHotspots];

    if (params) {
      if (params.risk_level) {
        filtered = filtered.filter(
          (h) => h.risk_level.toLowerCase() === params.risk_level?.toLowerCase()
        );
      }
      if (params.source_type) {
        filtered = filtered.filter(
          (h) => h.source_type.toLowerCase() === params.source_type?.toLowerCase()
        );
      }
      if (params.min_frp !== undefined) {
        filtered = filtered.filter((h) => h.frp >= (params.min_frp || 0));
      }
      if (params.is_anomaly !== undefined) {
        filtered = filtered.filter((h) => h.is_anomaly === params.is_anomaly);
      }
      if (params.min_confidence) {
        if (params.min_confidence === 'high') {
          filtered = filtered.filter((h) => h.confidence === 'high');
        }
      }
    }

    const pageSize = params?.page_size || 50;
    const page = params?.page || 1;
    const startIndex = (page - 1) * pageSize;
    const paginated = filtered.slice(startIndex, startIndex + pageSize);

    return {
      items: paginated,
      total: filtered.length,
      page,
      page_size: pageSize,
      data_mode: 'demo',
      generated_at: new Date().toISOString(),
    };
  }

  /**
   * Deep-dive Incident Detail Dossier
   */
  async getIncidentDetail(id: string): Promise<IncidentDetail> {
    const activeMode = this.getActiveDataMode();

    if (activeMode === 'live' && this.backendAvailable) {
      try {
        return await apiClient.getHotspotDetail(id);
      } catch (err) {
        console.warn(`Live API getHotspotDetail(${id}) failed, falling back to mock:`, err);
      }
    }

    const incident = mockIncidents[id];
    if (incident) {
      return incident;
    }

    // Fallback if ID is unknown: create safe synthetic item
    const fallbackHotspot = mockHotspots.find((h) => h.id === id) || mockHotspots[0];
    return mockIncidents[fallbackHotspot.id];
  }

  /**
   * Dashboard Summary KPIs
   */
  async getSummary(): Promise<SummaryResponse> {
    const activeMode = this.getActiveDataMode();

    if (activeMode === 'live' && this.backendAvailable) {
      try {
        return await apiClient.getSummary();
      } catch (err) {
        console.warn('Live API getSummary failed, falling back to mock provider:', err);
      }
    }

    return {
      ...mockSummary,
      last_sync_time: new Date().toISOString(),
    };
  }

  /**
   * Operational Alerts
   */
  async getAlerts(severity?: string, unreadOnly: boolean = false): Promise<AlertsResponse> {
    const activeMode = this.getActiveDataMode();

    if (activeMode === 'live' && this.backendAvailable) {
      try {
        return await apiClient.getAlerts(severity, unreadOnly);
      } catch (err) {
        console.warn('Live API getAlerts failed, falling back to mock provider:', err);
      }
    }

    let items = [...mockAlerts];
    if (severity) {
      items = items.filter((a) => a.severity.toLowerCase() === severity.toLowerCase());
    }
    if (unreadOnly) {
      items = items.filter((a) => !a.is_acknowledged);
    }

    return {
      items,
      total: items.length,
      unread_count: items.filter((a) => !a.is_acknowledged).length,
      generated_at: new Date().toISOString(),
    };
  }

  /**
   * Sources Breakdown Analytics
   */
  async getSources(): Promise<SourcesResponse> {
    const activeMode = this.getActiveDataMode();

    if (activeMode === 'live' && this.backendAvailable) {
      try {
        return await apiClient.getSources();
      } catch (err) {
        console.warn('Live API getSources failed, falling back to mock provider:', err);
      }
    }

    return mockSources;
  }

  /**
   * Sync / Refresh Telemetry Trigger
   */
  async refreshData(payload?: RefreshRequest): Promise<RefreshResponse> {
    const activeMode = this.getActiveDataMode();

    if (activeMode === 'live' && this.backendAvailable) {
      try {
        return await apiClient.refreshData(payload);
      } catch (err) {
        console.warn('Live API refreshData failed, simulating locally:', err);
      }
    }

    // Deterministic simulation
    return {
      status: 'success',
      message: 'Telemetry re-synchronized across active orbital passes and ground stations.',
      ingested_count: mockHotspots.length,
      data_mode: 'demo',
      timestamp: new Date().toISOString(),
      execution_time_seconds: 0.048,
    };
  }
}

export const dataProvider = new DataProvider();
export default dataProvider;
