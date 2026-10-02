'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import dataProvider, { AppDataMode } from '../lib/data-provider';
import {
  HealthResponse,
  SummaryResponse,
  Hotspot,
  Alert,
  SourcesResponse,
  DataMode,
} from '../types/api';
import { SystemMode, SourceHealthItem } from '../types/system';

export interface DashboardDataState {
  health: HealthResponse | null;
  summary: SummaryResponse | null;
  hotspots: Hotspot[];
  alerts: Alert[];
  sources: SourcesResponse | null;
  dataMode: DataMode;
  systemMode: SystemMode;
  modePreference: AppDataMode;
  sourceHealthList: SourceHealthItem[];
  cacheAgeSeconds: number;
  isStale: boolean;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  lastUpdated: string;
}

export function useDashboardData() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [hotspots, setAllHotspots] = useState<Hotspot[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [sources, setSources] = useState<SourcesResponse | null>(null);
  const [dataMode, setDataMode] = useState<DataMode>('demo');
  const [modePreference, setModePreferenceState] = useState<AppDataMode>('auto');

  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>('');
  const [cacheAgeSeconds, setCacheAgeSeconds] = useState<number>(0);

  // Fetch full telemetry data
  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      // 1. Health check & active mode detection
      const hRes = await dataProvider.getHealth();
      setHealth(hRes);
      setDataMode(dataProvider.getActiveDataMode());

      // 2. Parallel endpoints fetch
      const [sRes, hsRes, aRes, srcRes] = await Promise.all([
        dataProvider.getSummary(),
        dataProvider.getHotspots({ page_size: 100 }),
        dataProvider.getAlerts(),
        dataProvider.getSources(),
      ]);

      setSummary(sRes);
      setAllHotspots(hsRes.items || []);
      setAlerts(aRes.items || []);
      setSources(srcRes);
      setLastUpdated(new Date().toLocaleTimeString());
      setCacheAgeSeconds(0);
    } catch (err: any) {
      console.error('useDashboardData error:', err);
      setError(err?.message || 'Error communicating with ThermalIntel telemetry provider.');
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Periodic cache age updater (every 10 seconds)
  useEffect(() => {
    const timer = setInterval(() => {
      setCacheAgeSeconds(dataProvider.getCacheAgeSeconds());
    }, 10000);
    return () => clearInterval(timer);
  }, []);

  // Mode change handler
  const handleModeChange = useCallback(
    (newMode: AppDataMode) => {
      dataProvider.setModePreference(newMode);
      setModePreferenceState(newMode);
      fetchData();
    },
    [fetchData]
  );

  // Safe manual refresh trigger
  const handleRefresh = useCallback(async () => {
    try {
      setRefreshing(true);
      const res = await dataProvider.refreshData();
      if (res.status === 'throttled') {
        console.info(res.message);
      }
      await fetchData();
    } catch (err: any) {
      setError(`Telemetry sync error: ${err?.message}`);
    } finally {
      setRefreshing(false);
    }
  }, [fetchData]);

  // Derived system mode and source health
  const systemMode = useMemo<SystemMode>(() => {
    return dataProvider.getSystemMode();
  }, [dataMode, modePreference, cacheAgeSeconds]);

  const isStale = useMemo(() => {
    return dataProvider.isCacheStale();
  }, [cacheAgeSeconds]);

  const sourceHealthList = useMemo<SourceHealthItem[]>(() => {
    return dataProvider.getSourceHealthList(health);
  }, [health]);

  return {
    health,
    summary,
    hotspots,
    alerts,
    sources,
    dataMode,
    systemMode,
    modePreference,
    sourceHealthList,
    cacheAgeSeconds,
    isStale,
    loading,
    refreshing,
    error,
    lastUpdated,
    refresh: handleRefresh,
    setModePreference: handleModeChange,
    retry: fetchData,
  };
}

export default useDashboardData;
