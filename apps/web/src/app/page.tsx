'use client';

import React, { useEffect, useState, useMemo, useCallback } from 'react';
import dataProvider, { AppDataMode } from '../lib/data-provider';
import {
  SummaryResponse,
  Hotspot,
  Alert,
  HealthResponse,
  SourcesResponse,
  IncidentDetail,
  DataMode,
} from '../types/api';
import { Header } from '../components/dashboard/Header';
import { KpiStrip } from '../components/dashboard/KpiStrip';
import { FilterBar, FilterState } from '../components/dashboard/FilterBar';
import { MapContainer } from '../components/map/MapContainer';
import { IncidentFeed } from '../components/incidents/IncidentFeed';
import { IncidentDetailDrawer } from '../components/incidents/IncidentDetailDrawer';
import { AlertsFeed } from '../components/alerts/AlertsFeed';
import { AnalyticsPanel } from '../components/analytics/AnalyticsPanel';
import { Bell, Flame, BarChart3, AlertCircle, RefreshCw } from 'lucide-react';

const initialFilters: FilterState = {
  searchQuery: '',
  riskLevel: 'all',
  sourceType: 'all',
  minFrp: 0,
  anomalyOnly: false,
  minConfidence: 'all',
};

export default function DashboardPage() {
  // Telemetry & System State
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [dataMode, setDataMode] = useState<DataMode>('demo');
  const [modePreference, setModePreference] = useState<AppDataMode>('auto');
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [allHotspots, setAllHotspots] = useState<Hotspot[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [sources, setSources] = useState<SourcesResponse | null>(null);

  // Active View & Selection State
  const [selectedRegion, setSelectedRegion] = useState<string>('all');
  const [filters, setFilters] = useState<FilterState>(initialFilters);
  const [selectedHotspotId, setSelectedHotspotId] = useState<string | null>(null);
  const [selectedIncident, setSelectedIncident] = useState<IncidentDetail | null>(null);
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'map_feed' | 'alerts' | 'analytics'>('map_feed');

  // Loading & Error States
  const [loading, setLoading] = useState<boolean>(true);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>('');

  // Fetch Full Dashboard Telemetry
  const fetchDashboardData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      // 1. Health check & active mode detection
      const hRes = await dataProvider.getHealth();
      setHealth(hRes);
      const activeMode = dataProvider.getActiveDataMode();
      setDataMode(activeMode);

      // 2. Fetch parallel endpoints
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
    } catch (err: any) {
      console.error('Failed to load dashboard telemetry:', err);
      setError(err?.message || 'Error communicating with ThermalIntel data provider.');
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial Load
  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  // Handle Manual Mode Preference Change (Auto vs Demo)
  const handleModeChange = (newMode: AppDataMode) => {
    dataProvider.setModePreference(newMode);
    setModePreference(newMode);
    fetchDashboardData();
  };

  // Sync / Refresh Telemetry Trigger
  const handleRefresh = async () => {
    try {
      setRefreshing(true);
      await dataProvider.refreshData();
      await fetchDashboardData();
    } catch (err: any) {
      alert(`Refresh failed: ${err?.message}`);
    } finally {
      setRefreshing(false);
    }
  };

  // Open & Fetch Incident Detail
  const handleSelectIncident = async (id: string) => {
    setSelectedHotspotId(id);
    setDrawerOpen(true);
    setLoadingDetail(true);

    try {
      const detail = await dataProvider.getIncidentDetail(id);
      setSelectedIncident(detail);
    } catch (err) {
      console.error(`Failed to load incident detail for ${id}:`, err);
    } finally {
      setLoadingDetail(false);
    }
  };

  // Close Incident Drawer
  const handleCloseDrawer = () => {
    setDrawerOpen(false);
  };

  // Regional Hotspots Filtering
  const regionalHotspots = useMemo(() => {
    if (selectedRegion === 'all') return allHotspots;
    if (selectedRegion === 'california') {
      return allHotspots.filter(
        (h) => h.nearest_place?.includes('CA') || (h.latitude >= 32.5 && h.latitude <= 42.0 && h.longitude >= -124.5 && h.longitude <= -114.0)
      );
    }
    if (selectedRegion === 'gulf_industrial') {
      return allHotspots.filter(
        (h) => h.nearest_place?.includes('TX') || (h.latitude >= 25.0 && h.latitude <= 32.0 && h.longitude >= -98.0 && h.longitude <= -88.0)
      );
    }
    if (selectedRegion === 'pacific_nw') {
      return allHotspots.filter(
        (h) => h.nearest_place?.includes('OR') || h.nearest_place?.includes('WA')
      );
    }
    if (selectedRegion === 'hawaii') {
      return allHotspots.filter(
        (h) => h.nearest_place?.includes('HI') || (h.latitude >= 18.0 && h.latitude <= 23.0 && h.longitude >= -161.0 && h.longitude <= -154.0)
      );
    }
    return allHotspots;
  }, [allHotspots, selectedRegion]);

  // Client-Side Multi-Axis Filter Application
  const filteredHotspots = useMemo(() => {
    return regionalHotspots.filter((h) => {
      // Search query (ID, place, cluster)
      if (filters.searchQuery.trim()) {
        const query = filters.searchQuery.toLowerCase();
        const matchId = h.id.toLowerCase().includes(query);
        const matchPlace = (h.nearest_place || '').toLowerCase().includes(query);
        const matchCluster = (h.cluster_id || '').toLowerCase().includes(query);
        if (!matchId && !matchPlace && !matchCluster) return false;
      }

      // Risk level
      if (filters.riskLevel !== 'all' && h.risk_level.toLowerCase() !== filters.riskLevel.toLowerCase()) {
        return false;
      }

      // Source type
      if (filters.sourceType !== 'all' && h.source_type.toLowerCase() !== filters.sourceType.toLowerCase()) {
        return false;
      }

      // Min FRP
      if (filters.minFrp > 0 && h.frp < filters.minFrp) {
        return false;
      }

      // Statistical anomaly only
      if (filters.anomalyOnly && !h.is_anomaly) {
        return false;
      }

      return true;
    });
  }, [regionalHotspots, filters]);

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100 font-sans selection:bg-red-500 selection:text-white">
      {/* Top Navigation & Status Bar */}
      <Header
        health={health}
        dataMode={dataMode}
        modePreference={modePreference}
        onModeChange={handleModeChange}
        onRefresh={handleRefresh}
        refreshing={refreshing}
        selectedRegion={selectedRegion}
        onRegionChange={setSelectedRegion}
        lastUpdated={lastUpdated}
      />

      {/* Main Command Dashboard Canvas */}
      <main className="flex-1 p-3 sm:p-5 lg:p-6 space-y-4 max-w-[1720px] mx-auto w-full">
        {/* Connection Notice / Error Recovery */}
        {error && (
          <div className="p-4 rounded-xl bg-red-950/60 border border-red-800 text-red-200 text-xs flex items-center justify-between shadow-md">
            <div className="flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
              <span>{error}</span>
            </div>
            <button
              type="button"
              onClick={fetchDashboardData}
              className="text-xs font-bold underline hover:text-white ml-3"
            >
              Retry
            </button>
          </div>
        )}

        {/* Top KPI Metric Strip */}
        <KpiStrip
          summary={summary}
          activeFilterCount={filteredHotspots.length}
          totalHotspotsCount={allHotspots.length}
          activeAlertsCount={alerts.length}
          loading={loading}
        />

        {/* Global Multi-Axis Filter Bar */}
        <FilterBar
          filters={filters}
          onChange={setFilters}
          onReset={() => setFilters(initialFilters)}
          totalCount={regionalHotspots.length}
          filteredCount={filteredHotspots.length}
        />

        {/* Operational Section Navigation Tabs */}
        <div className="flex items-center space-x-2 border-b border-slate-800 pb-1 text-xs font-mono">
          <button
            type="button"
            onClick={() => setActiveTab('map_feed')}
            className={`flex items-center space-x-2 px-3 py-2 rounded-t-lg transition-all border-b-2 font-bold ${
              activeTab === 'map_feed'
                ? 'border-red-500 text-white bg-slate-900'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Flame className="w-3.5 h-3.5 text-red-500" />
            <span>Tactical Map & Incident Queue</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-300">
              {filteredHotspots.length}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('alerts')}
            className={`flex items-center space-x-2 px-3 py-2 rounded-t-lg transition-all border-b-2 font-bold ${
              activeTab === 'alerts'
                ? 'border-rose-500 text-white bg-slate-900'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Bell className="w-3.5 h-3.5 text-rose-400" />
            <span>Operational Alerts</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-rose-950 text-rose-300 border border-rose-800">
              {alerts.length} Active
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('analytics')}
            className={`flex items-center space-x-2 px-3 py-2 rounded-t-lg transition-all border-b-2 font-bold ${
              activeTab === 'analytics'
                ? 'border-cyan-500 text-white bg-slate-900'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <BarChart3 className="w-3.5 h-3.5 text-cyan-400" />
            <span>Risk & Source Analytics</span>
          </button>
        </div>

        {/* Primary View Area 1: Tactical Map + Incident Queue */}
        {activeTab === 'map_feed' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 lg:gap-5 min-h-[580px]">
            {/* Interactive Leaflet Geospatial Map Container */}
            <section
              id="map-container"
              className="lg:col-span-8 rounded-xl bg-slate-900 border border-slate-800 flex flex-col overflow-hidden shadow-xl min-h-[460px] lg:min-h-[580px] relative"
            >
              <div className="px-4 py-2.5 border-b border-slate-800 flex items-center justify-between bg-slate-900/95 z-10">
                <div className="flex items-center space-x-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse" />
                  <h2 className="text-xs font-bold uppercase tracking-wider text-white font-mono">
                    Tactical Geospatial Satellite Map (VIIRS 375m)
                  </h2>
                </div>
                <div className="text-[11px] text-slate-400 font-mono">
                  {filteredHotspots.length} Rendered Hotspots
                </div>
              </div>

              {/* Map Surface */}
              <div className="flex-1 w-full h-full relative">
                <MapContainer
                  hotspots={filteredHotspots}
                  selectedHotspotId={selectedHotspotId}
                  onSelectIncident={handleSelectIncident}
                  selectedRegion={selectedRegion}
                />
              </div>
            </section>

            {/* Incident Feed Column */}
            <div className="lg:col-span-4 min-h-[460px] lg:min-h-[580px] flex flex-col">
              <IncidentFeed
                hotspots={filteredHotspots}
                selectedHotspotId={selectedHotspotId}
                onSelectIncident={handleSelectIncident}
                loading={loading}
                onResetFilters={() => setFilters(initialFilters)}
              />
            </div>
          </div>
        )}

        {/* Primary View Area 2: Alerts Dedicated Feed */}
        {activeTab === 'alerts' && (
          <div className="max-w-4xl mx-auto space-y-4 py-2">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <div>
                <h3 className="text-sm font-bold uppercase text-white font-mono">
                  Dispatched Operational Threat Advisories
                </h3>
                <p className="text-xs text-slate-400">
                  Real-time algorithmic alert triggers generated for high-FRP anomalies near settlements and infrastructure.
                </p>
              </div>
              <span className="text-xs font-mono text-slate-400">
                Total: {alerts.length} Advisories
              </span>
            </div>
            <AlertsFeed
              alerts={alerts}
              onSelectIncident={(id) => {
                setActiveTab('map_feed');
                handleSelectIncident(id);
              }}
            />
          </div>
        )}

        {/* Primary View Area 3: Dedicated Analytics Deep-Dive */}
        {activeTab === 'analytics' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 py-2">
            <div className="lg:col-span-8">
              <AnalyticsPanel
                summary={summary}
                sources={sources}
                hotspots={allHotspots}
              />
            </div>
            <div className="lg:col-span-4 space-y-4">
              <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 shadow-md space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 font-mono">
                  Intelligence Engine Architecture
                </h3>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Thermal anomalies are normalized from near-real-time satellite passes, enriched with OSM critical infrastructure proximities and Open-Meteo fire weather indices, then evaluated by the composite ML risk engine.
                </p>
                <div className="p-3 rounded-lg bg-slate-950 font-mono text-[11px] text-cyan-300 space-y-1">
                  <div>Algorithm: Random Forest + IsolationForest</div>
                  <div>Attribution: Feature Weight Scoring</div>
                  <div>Risk Output: Calibrated 0–100 Matrix</div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Secondary Bottom Grid: Always Visible Analytical Synopsis */}
        {activeTab === 'map_feed' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 pt-2">
            <div className="lg:col-span-7">
              <AnalyticsPanel
                summary={summary}
                sources={sources}
                hotspots={filteredHotspots}
              />
            </div>

            <div className="lg:col-span-5 flex flex-col justify-between p-5 rounded-xl bg-slate-900/90 border border-slate-800 shadow-lg space-y-3">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <div className="flex items-center space-x-2">
                  <Bell className="w-4 h-4 text-rose-400" />
                  <h3 className="text-xs font-bold uppercase tracking-wider text-white font-mono">
                    Urgent Operational Alerts ({alerts.length})
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setActiveTab('alerts')}
                  className="text-xs text-red-400 hover:text-red-300 font-semibold"
                >
                  View All &rarr;
                </button>
              </div>

              <div className="space-y-2 overflow-y-auto max-h-[220px]">
                {alerts.slice(0, 2).map((a) => (
                  <div
                    key={a.id}
                    onClick={() => handleSelectIncident(a.hotspot_id)}
                    className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 hover:border-slate-700 cursor-pointer transition-all space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-bold uppercase px-1.5 py-0.2 rounded bg-red-500/20 text-red-400 border border-red-500/30">
                        {a.severity}
                      </span>
                      <span className="text-[10px] font-mono text-slate-500">
                        Hotspot: {a.hotspot_id.split('-').pop()}
                      </span>
                    </div>
                    <div className="text-xs font-semibold text-slate-200 line-clamp-1">
                      {a.title}
                    </div>
                    <div className="text-[11px] text-slate-400 line-clamp-1">
                      {a.message}
                    </div>
                  </div>
                ))}
              </div>

              <div className="pt-2 border-t border-slate-800/80 text-[11px] text-slate-500 font-mono flex justify-between">
                <span>INCIDENT DEFENSE READY</span>
                <span>DISPATCH ADVISORY ACTIVE</span>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Slide-Over Incident Detail Dossier Drawer */}
      {drawerOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity"
            onClick={handleCloseDrawer}
          />
          <IncidentDetailDrawer
            incident={selectedIncident}
            onClose={handleCloseDrawer}
            loading={loadingDetail}
          />
        </>
      )}

      {/* Footer */}
      <footer className="border-t border-slate-800/80 py-3 px-6 text-center text-xs text-slate-500 bg-slate-950/90 font-mono mt-8">
        ThermalIntel Command Center • Geospatial Anomaly & AI Risk Intelligence • Next.js 14 • Leaflet • Recharts
      </footer>
    </div>
  );
}
