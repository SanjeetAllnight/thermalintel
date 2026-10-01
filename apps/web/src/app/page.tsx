'use client';

import React, { useEffect, useState } from 'react';
import apiClient from '../lib/api-client';
import {
  SummaryResponse,
  Hotspot,
  Alert,
  HealthResponse,
  SourcesResponse,
} from '../types/api';

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [hotspots, setHotspots] = useState<Hotspot[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [sources, setSources] = useState<SourcesResponse | null>(null);
  const [selectedHotspotId, setSelectedHotspotId] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [hRes, sRes, hsRes, aRes, srcRes] = await Promise.all([
        apiClient.getHealth().catch(() => null),
        apiClient.getSummary().catch(() => null),
        apiClient.getHotspots({ page_size: 50 }).catch(() => null),
        apiClient.getAlerts().catch(() => null),
        apiClient.getSources().catch(() => null),
      ]);

      if (hRes) setHealth(hRes);
      if (sRes) setSummary(sRes);
      if (hsRes) setHotspots(hsRes.items);
      if (aRes) setAlerts(aRes.items);
      if (srcRes) setSources(srcRes);
    } catch (err: any) {
      setError(err?.message || 'Failed to connect to ThermalIntel API backend.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const handleRefresh = async () => {
    try {
      setRefreshing(true);
      await apiClient.refreshData();
      await fetchDashboardData();
    } catch (err: any) {
      alert(`Refresh failed: ${err?.message}`);
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100">
      {/* Top Navigation Bar */}
      <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur px-6 py-3.5 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-amber-500 to-red-600 flex items-center justify-center font-bold text-white shadow-md shadow-red-500/20">
            TI
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-lg font-bold tracking-tight text-white">ThermalIntel</h1>
              <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 font-mono">
                v0.1.0
              </span>
            </div>
            <p className="text-xs text-slate-400">Satellite Thermal Anomaly & AI Risk Intelligence</p>
          </div>
        </div>

        {/* Status Indicators & Controls */}
        <div className="flex items-center space-x-4">
          {/* Data Mode Indicator */}
          <div className="flex items-center space-x-1.5 px-3 py-1 rounded-full bg-slate-800/80 border border-slate-700 text-xs">
            <span
              className={`w-2 h-2 rounded-full ${
                health?.data_mode === 'live' ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'
              }`}
            />
            <span className="font-medium text-slate-300">
              Mode: <strong className="uppercase text-white">{health?.data_mode || 'DEMO'}</strong>
            </span>
          </div>

          {/* Backend Status */}
          <div className="hidden md:flex items-center space-x-1.5 px-3 py-1 rounded-full bg-slate-800/80 border border-slate-700 text-xs">
            <span
              className={`w-2 h-2 rounded-full ${health?.status === 'ok' ? 'bg-emerald-400' : 'bg-red-400'}`}
            />
            <span className="text-slate-400">
              API: <strong className="text-slate-200">{health?.status || 'Connecting...'}</strong>
            </span>
          </div>

          {/* Refresh Action */}
          <button
            id="btn-sync-refresh"
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center space-x-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-red-600 hover:bg-red-500 active:scale-95 disabled:opacity-50 text-white transition-all shadow-md shadow-red-600/20"
          >
            <span>{refreshing ? 'Syncing...' : '↻ Sync Telemetry'}</span>
          </button>
        </div>
      </header>

      {/* Main Content Dashboard Container */}
      <main className="flex-1 p-6 space-y-6 max-w-7xl mx-auto w-full">
        {error && (
          <div className="p-4 rounded-lg bg-red-950/50 border border-red-800 text-red-300 text-sm flex items-center justify-between">
            <span>⚠️ {error}</span>
            <button
              onClick={fetchDashboardData}
              className="text-xs font-bold underline hover:text-white"
            >
              Retry
            </button>
          </div>
        )}

        {/* KPI Summary Overview Bar */}
        <section id="kpi-summary-cards" className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 shadow-sm">
            <div className="text-xs text-slate-400 font-medium">Active Hotspots</div>
            <div className="text-2xl font-black text-white mt-1">
              {summary ? summary.total_active_hotspots : '—'}
            </div>
            <div className="text-[11px] text-slate-500 mt-1">Normalized VIIRS pixels</div>
          </div>

          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 shadow-sm">
            <div className="text-xs text-red-400 font-medium">Critical Risk Hotspots</div>
            <div className="text-2xl font-black text-red-500 mt-1">
              {summary ? summary.critical_risk_count : '—'}
            </div>
            <div className="text-[11px] text-slate-500 mt-1">Score ≥ 75 / 100</div>
          </div>

          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 shadow-sm">
            <div className="text-xs text-amber-400 font-medium">High Risk Hotspots</div>
            <div className="text-2xl font-black text-amber-500 mt-1">
              {summary ? summary.high_risk_count : '—'}
            </div>
            <div className="text-[11px] text-slate-500 mt-1">Score 50 – 74</div>
          </div>

          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 shadow-sm">
            <div className="text-xs text-cyan-400 font-medium">Mean Radiative Power</div>
            <div className="text-2xl font-black text-cyan-400 mt-1">
              {summary ? `${summary.average_frp} MW` : '—'}
            </div>
            <div className="text-[11px] text-slate-500 mt-1">Peak: {summary?.max_frp || 0} MW</div>
          </div>

          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 shadow-sm">
            <div className="text-xs text-rose-400 font-medium">Active Alerts</div>
            <div className="text-2xl font-black text-rose-400 mt-1">
              {summary ? summary.active_alerts_count : alerts.length}
            </div>
            <div className="text-[11px] text-slate-500 mt-1">Unacknowledged events</div>
          </div>
        </section>

        {/* Primary Interactive Split View: Map + Incident Feeds */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 min-h-[580px]">
          {/* Map Area Placeholder Container (Target for agent-ui Leaflet Map) */}
          <section
            id="map-container"
            className="lg:col-span-8 rounded-xl bg-slate-900 border border-slate-800 flex flex-col overflow-hidden relative"
          >
            <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
              <div className="flex items-center space-x-2">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
                <h2 className="text-sm font-semibold text-white">Geospatial Thermal Anomaly Map</h2>
              </div>
              <div className="text-xs text-slate-400 font-mono">
                {hotspots.length} Points Renderable
              </div>
            </div>

            {/* Interactive Map Surface Scaffold */}
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-slate-950/60 min-h-[420px]">
              <div className="w-14 h-14 rounded-2xl bg-slate-800/80 border border-slate-700 flex items-center justify-center text-amber-500 mb-3 text-2xl">
                🗺️
              </div>
              <h3 className="text-base font-semibold text-slate-200">Interactive Map View Surface</h3>
              <p className="text-xs text-slate-400 max-w-md mt-1 mb-4">
                Target component for Leaflet visualization, cluster markers, and heatmaps.
                Backend data is pre-fetched and ready to mount.
              </p>
              <div className="flex flex-wrap gap-2 justify-center text-xs">
                <span className="px-2.5 py-1 rounded bg-slate-800 text-slate-300 font-mono">
                  Coordinates: 38.74°N, -122.81°W
                </span>
                <span className="px-2.5 py-1 rounded bg-slate-800 text-slate-300 font-mono">
                  Active Clusters: 3
                </span>
              </div>
            </div>
          </section>

          {/* Incident Feed & Filter List Area (Target for agent-ui Incident Feed) */}
          <section
            id="incident-list-container"
            className="lg:col-span-4 rounded-xl bg-slate-900 border border-slate-800 flex flex-col overflow-hidden"
          >
            <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
              <h2 className="text-sm font-semibold text-white">Detected Incidents</h2>
              <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                {hotspots.length} Records
              </span>
            </div>

            <div className="flex-1 overflow-y-auto max-h-[520px] p-3 space-y-2.5">
              {loading && hotspots.length === 0 ? (
                <div className="p-6 text-center text-xs text-slate-500">Loading incidents...</div>
              ) : hotspots.length === 0 ? (
                <div className="p-6 text-center text-xs text-slate-500">No thermal anomalies found.</div>
              ) : (
                hotspots.map((h) => (
                  <div
                    key={h.id}
                    onClick={() => setSelectedHotspotId(h.id)}
                    className={`p-3 rounded-lg border transition-all cursor-pointer ${
                      selectedHotspotId === h.id
                        ? 'border-red-500 bg-red-950/20 shadow-md'
                        : 'border-slate-800 bg-slate-950/40 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono font-semibold text-slate-200">
                        {h.id}
                      </span>
                      <span
                        className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${
                          h.risk_level === 'critical'
                            ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                            : h.risk_level === 'high'
                            ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                            : 'bg-slate-800 text-slate-400'
                        }`}
                      >
                        {h.risk_level} ({Math.round(h.risk_score)})
                      </span>
                    </div>

                    <div className="text-xs font-medium text-slate-300 mt-1 line-clamp-1">
                      {h.nearest_place || 'Unclassified Territory'}
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-slate-500 mt-2">
                      <span>Source: <strong className="capitalize text-slate-400">{h.source_type}</strong></span>
                      <span>FRP: <strong className="text-cyan-400">{h.frp} MW</strong></span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>

        {/* Secondary Analytics & Detail Grids */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Incident Detail Drawer / Explainable Risk Inspection */}
          <section
            id="incident-detail-drawer"
            className="lg:col-span-7 rounded-xl bg-slate-900 border border-slate-800 p-5"
          >
            <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
              <h2 className="text-sm font-semibold text-white">
                Incident Deep-Dive & Explainable AI Factors
              </h2>
              <span className="text-xs text-slate-400 font-mono">
                {selectedHotspotId ? `Selected: ${selectedHotspotId}` : 'Select an incident above'}
              </span>
            </div>

            <div className="text-xs text-slate-400 space-y-3">
              <p>
                Target component for <code>GET /api/hotspots/{'{id}'}</code> detail inspector:
                OSM geospatial proximity, Open-Meteo fire weather indices, historical recurrence metrics,
                and feature attribution factors explaining why the model assigned the risk score.
              </p>
              <div className="p-4 rounded-lg bg-slate-950/80 border border-slate-800/80 font-mono text-[11px] text-slate-300">
                Ready for agent-ui detail drawer mounting.
              </div>
            </div>
          </section>

          {/* Analytics Charts & Source Distribution (Target for Recharts) */}
          <section
            id="analytics-charts-container"
            className="lg:col-span-5 rounded-xl bg-slate-900 border border-slate-800 p-5"
          >
            <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
              <h2 className="text-sm font-semibold text-white">Source Breakdown & Analytics</h2>
              <span className="text-xs text-slate-400 font-mono">Recharts Surface</span>
            </div>

            <div className="space-y-3">
              {sources?.sources.map((s) => (
                <div key={s.source_type} className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-300 font-medium">{s.display_name}</span>
                    <span className="text-slate-400">{s.count} ({s.percentage}%)</span>
                  </div>
                  <div className="w-full bg-slate-800 rounded-full h-1.5">
                    <div
                      className="bg-red-500 h-1.5 rounded-full"
                      style={{ width: `${s.percentage}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800 py-3 px-6 text-center text-xs text-slate-500">
        ThermalIntel Architecture Foundation • Hackathon Parallel Agent Framework • Port 3000 (UI) ↔ Port 8000 (API)
      </footer>
    </div>
  );
}
