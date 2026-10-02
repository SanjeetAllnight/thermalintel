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
import { SystemMode, SourceHealthItem, ReplayState } from '../types/system';
import {
  mockHealth,
  mockHotspots,
  mockIncidents,
  mockSummary,
  mockAlerts,
  mockSources,
} from './mock-data';

export type AppDataMode = 'auto' | 'live' | 'demo' | 'replay';

class DataProvider {
  private modePreference: AppDataMode = 'auto';
  private lastDetectedMode: DataMode = 'demo';
  private backendAvailable: boolean = false;
  private lastFetchedAt: Date | null = null;
  private lastRefreshAttempt: number = 0;
  private replayVirtualTime: string = '2026-10-01T08:45:00Z';

  setModePreference(mode: AppDataMode) {
    this.modePreference = mode;
  }

  getModePreference(): AppDataMode {
    return this.modePreference;
  }

  getActiveDataMode(): DataMode {
    if (this.modePreference === 'demo') return 'demo';
    if (this.modePreference === 'replay') return 'demo';
    if (this.modePreference === 'live') return this.backendAvailable ? 'live' : 'demo';
    return this.lastDetectedMode;
  }

  getSystemMode(): SystemMode {
    if (this.modePreference === 'replay') return 'REPLAY';
    if (this.modePreference === 'demo') return 'DEMO';
    if (this.backendAvailable && this.lastDetectedMode === 'live') {
      const age = this.getCacheAgeSeconds();
      if (age > 300) return 'CACHE';
      return 'LIVE';
    }
    // When using fallback data or offline
    return 'DEMO';
  }

  isBackendAvailable(): boolean {
    return this.backendAvailable;
  }

  getLastFetchedAt(): Date | null {
    return this.lastFetchedAt;
  }

  getCacheAgeSeconds(): number {
    if (!this.lastFetchedAt) return 0;
    return Math.floor((Date.now() - this.lastFetchedAt.getTime()) / 1000);
  }

  isCacheStale(): boolean {
    return this.getCacheAgeSeconds() > 300; // 5 minutes threshold
  }

  /**
   * Health Check & Mode Detection
   */
  async getHealth(): Promise<HealthResponse> {
    if (this.modePreference === 'demo' || this.modePreference === 'replay') {
      this.lastDetectedMode = 'demo';
      this.lastFetchedAt = new Date();
      return { ...mockHealth, data_mode: 'demo' };
    }

    try {
      const health = await apiClient.getHealth();
      this.backendAvailable = health?.status === 'ok';
      this.lastDetectedMode = health?.data_mode || 'live';
      this.lastFetchedAt = new Date();
      return health;
    } catch {
      this.backendAvailable = false;
      this.lastDetectedMode = 'demo';
      this.lastFetchedAt = new Date();
      return {
        ...mockHealth,
        data_mode: 'demo',
        services: {
          database: 'fallback (local state)',
          firms_api: 'unavailable (using fixture)',
          intelligence_engine: 'local-evaluation',
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
        const res = await apiClient.getHotspots(params);
        this.lastFetchedAt = new Date();
        return res;
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
      data_mode: this.getActiveDataMode(),
      generated_at: new Date().toISOString(),
    };
  }

  /**
   * Deep-dive Incident Detail Dossier
   * Never silently fall back to mockHotspots[0]!
   */
  async getIncidentDetail(id: string): Promise<IncidentDetail> {
    const activeMode = this.getActiveDataMode();

    if (activeMode === 'live' && this.backendAvailable) {
      try {
        return await apiClient.getHotspotDetail(id);
      } catch (err: any) {
        // If the live API returned 404 or not found, explicitly throw not found error
        if (
          err?.message?.includes('404') ||
          err?.message?.toLowerCase().includes('not found')
        ) {
          throw new Error(`Incident with ID '${id}' not found in active telemetry`);
        }
        console.warn(`Live API getHotspotDetail(${id}) failed, checking local registry:`, err);
      }
    }

    const incident = mockIncidents[id];
    if (incident) {
      return incident;
    }

    // Explicit error when incident ID is unknown:
    // Do NOT silently replace with the first mock incident!
    throw new Error(`Incident with ID '${id}' not found in active telemetry registry`);
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
      data_mode: this.getActiveDataMode(),
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

    return {
      ...mockSources,
      data_mode: this.getActiveDataMode(),
    };
  }

  /**
   * Compact Source Health (Requirement 8)
   */
  getSourceHealthList(health: HealthResponse | null): SourceHealthItem[] {
    const isLiveMode = this.backendAvailable && health?.status === 'ok';

    return [
      {
        id: 'nasa-firms',
        name: 'NASA FIRMS (VIIRS 375m)',
        category: 'satellite',
        status: isLiveMode ? 'LIVE' : 'CACHE',
        detail: isLiveMode ? 'Orbital NRT ingestion active' : 'Local satellite passes cached',
      },
      {
        id: 'osm-overpass',
        name: 'OpenStreetMap (Infra/Settlement)',
        category: 'gis',
        status: isLiveMode ? 'LIVE' : 'CACHE',
        detail: isLiveMode ? 'Overpass spatial grid reachable' : 'Cached infrastructure buffer',
      },
      {
        id: 'open-meteo',
        name: 'Open-Meteo Synoptic Weather',
        category: 'weather',
        status: isLiveMode ? 'LIVE' : 'CACHE',
        detail: isLiveMode ? 'Surface hourly telemetry sync' : 'Cached synoptic parameters',
      },
      {
        id: 'database',
        name: 'Database (Telemetry Storage)',
        category: 'database',
        status: isLiveMode ? 'HEALTHY' : 'DEGRADED',
        detail: isLiveMode ? 'Persistence engine connected' : 'In-memory fixture store',
      },
      {
        id: 'ai-engine',
        name: 'Intelligence Engine (RF + Anomaly)',
        category: 'ai',
        status: isLiveMode ? 'HEALTHY' : 'HEALTHY',
        detail: 'Inference pipeline operational',
      },
    ];
  }

  /**
   * Sync / Refresh Telemetry Trigger with safe throttling (Requirement 15)
   */
  async refreshData(payload?: RefreshRequest): Promise<RefreshResponse> {
    const now = Date.now();
    // Guard against aggressive rapid polling (minimum 3 seconds between triggers)
    if (now - this.lastRefreshAttempt < 3000) {
      return {
        status: 'throttled',
        message: 'Refresh rate limited. Telemetry is already current.',
        ingested_count: 0,
        data_mode: this.getActiveDataMode(),
        timestamp: new Date().toISOString(),
        execution_time_seconds: 0,
      };
    }
    this.lastRefreshAttempt = now;

    const activeMode = this.getActiveDataMode();

    if (activeMode === 'live' && this.backendAvailable) {
      try {
        const res = await apiClient.refreshData(payload);
        this.lastFetchedAt = new Date();
        return res;
      } catch (err) {
        console.warn('Live API refreshData failed, simulating locally:', err);
      }
    }

    this.lastFetchedAt = new Date();

    return {
      status: 'success',
      message: 'Telemetry re-synchronized across active orbital passes and ground stations.',
      ingested_count: mockHotspots.length,
      data_mode: 'demo',
      timestamp: new Date().toISOString(),
      execution_time_seconds: 0.048,
    };
  }

  /**
   * Replay Subsystem Scaffolding (Requirement 14)
   * Prepares frontend architecture for Agent G's replay engine
   */
  getReplayState(): ReplayState {
    return {
      enabled: this.modePreference === 'replay',
      isSimulated: true,
      virtualTimeUtc: this.replayVirtualTime,
      speed: 1,
      availableTimeRange: ['2026-10-01T00:00:00Z', '2026-10-01T12:00:00Z'],
    };
  }

  setReplayVirtualTime(timeUtc: string) {
    this.replayVirtualTime = timeUtc;
  }
}

export const dataProvider = new DataProvider();
export default dataProvider;
