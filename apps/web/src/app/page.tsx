'use client';

import React, { useState } from 'react';
import { useDashboardData } from '../hooks/useDashboardData';
import { useIncidentFilter } from '../hooks/useIncidentFilter';
import { useIncidentSelection } from '../hooks/useIncidentSelection';
import { useKeyboardNavigation } from '../hooks/useKeyboardNavigation';

import { Header } from '../components/dashboard/Header';
import { KpiStrip } from '../components/dashboard/KpiStrip';
import { FilterBar } from '../components/dashboard/FilterBar';
import { MapContainer } from '../components/map/MapContainer';
import { IncidentFeed } from '../components/incidents/IncidentFeed';
import { IncidentDetailDrawer } from '../components/incidents/IncidentDetailDrawer';
import { AlertsFeed } from '../components/alerts/AlertsFeed';
import { AnalyticsPanel } from '../components/analytics/AnalyticsPanel';
import { ReplayControl } from '../components/system/ReplayControl';
import { Bell, Flame, BarChart3, AlertCircle } from 'lucide-react';

export default function DashboardPage() {
  // Domain Hook 1: Telemetry and Provider State
  const {
    health,
    summary,
    hotspots: allHotspots,
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
    refresh,
    setModePreference,
    retry,
  } = useDashboardData();

  // Domain Hook 2: Multi-Axis Filtering and Regional Slicing
  const {
    filters,
    selectedRegion,
    sortBy,
    filteredHotspots,
    totalCount,
    filteredCount,
    setFilters,
    resetFilters,
    setSelectedRegion,
    setSortBy,
  } = useIncidentFilter(allHotspots);

  // Domain Hook 3: Incident Selection and Unknown Incident Error Handling
  const {
    selectedHotspotId,
    selectedIncident,
    loadingDetail,
    detailError,
    drawerOpen,
    selectIncident,
    closeDrawer,
  } = useIncidentSelection();

  // Domain Hook 4: Keyboard Accessibility (Arrow keys, Esc)
  useKeyboardNavigation({
    hotspots: filteredHotspots,
    selectedId: selectedHotspotId,
    onSelect: selectIncident,
    onCloseDrawer: closeDrawer,
    isDrawerOpen: drawerOpen,
  });

  // UI Presentation State
  const [activeTab, setActiveTab] = useState<'queue_map' | 'alerts' | 'analytics'>('queue_map');

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100 font-sans selection:bg-red-500 selection:text-white">
      {/* 1. SYSTEM STATUS & HEADER (Persistent System Mode, Source Health, Zone Selection) */}
      <Header
        health={health}
        dataMode={dataMode}
        systemMode={systemMode}
        modePreference={modePreference}
        sourceHealthList={sourceHealthList}
        cacheAgeSeconds={cacheAgeSeconds}
        isStale={isStale}
        onModeChange={setModePreference}
        onRefresh={refresh}
        refreshing={refreshing}
        selectedRegion={selectedRegion}
        onRegionChange={setSelectedRegion}
        lastUpdated={lastUpdated}
      />

      {/* Main Command Center Canvas */}
      <main className="flex-1 p-3 sm:p-5 lg:p-6 space-y-4 max-w-[1720px] mx-auto w-full">
        {/* Replay Standby Subsystem (Requirement 14) */}
        {modePreference === 'replay' && (
          <ReplayControl
            isActive={true}
            onToggleReplay={(enable) => setModePreference(enable ? 'replay' : 'auto')}
          />
        )}

        {/* Global Connection / Telemetry Alert Notice */}
        {error && (
          <div
            className="p-4 rounded-xl bg-red-950/70 border border-red-800 text-red-200 text-xs flex items-center justify-between shadow-lg"
            role="alert"
          >
            <div className="flex items-center space-x-2.5">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0" aria-hidden="true" />
              <span className="font-medium">{error}</span>
            </div>
            <button
              type="button"
              onClick={retry}
              className="text-xs font-bold underline hover:text-white ml-3 cursor-pointer"
            >
              Retry Sync
            </button>
          </div>
        )}

        {/* Tactical KPI Metric Strip */}
        <KpiStrip
          summary={summary}
          activeFilterCount={filteredCount}
          totalHotspotsCount={totalCount}
          activeAlertsCount={alerts.length}
          loading={loading}
        />

        {/* Multi-Axis Incident Filter Bar */}
        <FilterBar
          filters={filters}
          onChange={setFilters}
          onReset={resetFilters}
          totalCount={totalCount}
          filteredCount={filteredCount}
        />

        {/* Command Center Operational View Switcher */}
        <div
          role="tablist"
          aria-label="Command Center Views"
          className="flex items-center space-x-2 border-b border-slate-800 pb-1 text-xs font-mono"
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'queue_map'}
            id="tab-queue-map"
            onClick={() => setActiveTab('queue_map')}
            className={`flex items-center space-x-2 px-3 py-2 rounded-t-lg transition-all border-b-2 font-bold ${
              activeTab === 'queue_map'
                ? 'border-red-500 text-white bg-slate-900'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Flame className="w-3.5 h-3.5 text-red-500" aria-hidden="true" />
            <span>Prioritized Queue & Tactical Map</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-300">
              {filteredCount}
            </span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'alerts'}
            id="tab-alerts"
            onClick={() => setActiveTab('alerts')}
            className={`flex items-center space-x-2 px-3 py-2 rounded-t-lg transition-all border-b-2 font-bold ${
              activeTab === 'alerts'
                ? 'border-rose-500 text-white bg-slate-900'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Bell className="w-3.5 h-3.5 text-rose-400" aria-hidden="true" />
            <span>Operational Alerts</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-rose-950 text-rose-300 border border-rose-800">
              {alerts.length} Active
            </span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'analytics'}
            id="tab-analytics"
            onClick={() => setActiveTab('analytics')}
            className={`flex items-center space-x-2 px-3 py-2 rounded-t-lg transition-all border-b-2 font-bold ${
              activeTab === 'analytics'
                ? 'border-cyan-500 text-white bg-slate-900'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <BarChart3 className="w-3.5 h-3.5 text-cyan-400" aria-hidden="true" />
            <span>Risk & Source Analytics</span>
          </button>
        </div>

        {/* PRIMARY VIEW: PRIORITIZED QUEUE (Primary Scannable) + TACTICAL MAP */}
        {activeTab === 'queue_map' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 lg:gap-5 min-h-[580px]">
            {/* Primary Scannable Incident Queue (Desktop: 5 cols, Mobile: Top full width) */}
            <div className="lg:col-span-5 min-h-[460px] lg:min-h-[580px] flex flex-col order-1">
              <IncidentFeed
                hotspots={filteredHotspots}
                selectedHotspotId={selectedHotspotId}
                onSelectIncident={selectIncident}
                loading={loading}
                sortBy={sortBy}
                onSortChange={setSortBy}
                onResetFilters={resetFilters}
              />
            </div>

            {/* Tactical Geospatial Map (Desktop: 7 cols) */}
            <section
              id="map-container"
              role="region"
              aria-label="Tactical Geospatial Satellite Map"
              className="lg:col-span-7 rounded-xl bg-slate-900 border border-slate-800 flex flex-col overflow-hidden shadow-xl min-h-[460px] lg:min-h-[580px] relative order-2"
            >
              <div className="px-4 py-2.5 border-b border-slate-800 flex items-center justify-between bg-slate-900/95 z-10">
                <div className="flex items-center space-x-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-500 motion-safe:animate-pulse" />
                  <h2 className="text-xs font-bold uppercase tracking-wider text-white font-mono">
                    Tactical Geospatial Satellite Map (VIIRS 375m)
                  </h2>
                </div>
                <div className="text-[11px] text-slate-400 font-mono">
                  {filteredCount} Rendered Hotspots
                </div>
              </div>

              {/* Map Surface */}
              <div className="flex-1 w-full h-full relative">
                <MapContainer
                  hotspots={filteredHotspots}
                  selectedHotspotId={selectedHotspotId}
                  onSelectIncident={selectIncident}
                  selectedRegion={selectedRegion}
                />
              </div>
            </section>
          </div>
        )}

        {/* SECONDARY VIEW 2: ALERTS DEDICATED FEED */}
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
                setActiveTab('queue_map');
                selectIncident(id);
              }}
            />
          </div>
        )}

        {/* SECONDARY VIEW 3: ANALYTICS VIEW */}
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
      </main>

      {/* SELECTED INCIDENT: Slide-Over Incident Detail Dossier Drawer */}
      {drawerOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity"
            onClick={closeDrawer}
            aria-hidden="true"
          />
          <IncidentDetailDrawer
            incident={selectedIncident}
            onClose={closeDrawer}
            loading={loadingDetail}
            error={detailError}
          />
        </>
      )}

      {/* Footer */}
      <footer className="border-t border-slate-800/80 py-3 px-6 text-center text-xs text-slate-500 bg-slate-950/90 font-mono mt-8">
        ThermalIntel Operational Command Center • Remote Sensing & AI Hazard Intelligence
      </footer>
    </div>
  );
}
