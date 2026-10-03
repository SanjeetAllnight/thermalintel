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
import { NavRail } from '../components/navigation/NavRail';
import {
  Bell,
  Flame,
  BarChart3,
  AlertCircle,
  Maximize2,
  ChevronLeft,
  ChevronRight,
  SlidersHorizontal,
  Compass,
  Layers,
  Settings,
  X,
} from 'lucide-react';

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
  const [isFeedCollapsed, setIsFeedCollapsed] = useState<boolean>(false);
  const [activeNav, setActiveNav] = useState<'command' | 'incidents' | 'alerts' | 'analytics' | 'sources' | 'layers' | 'settings'>('command');
  const [settingsModalOpen, setSettingsModalOpen] = useState<boolean>(false);

  // Sync NavRail clicks with Tabs
  const handleNavChange = (nav: 'command' | 'incidents' | 'alerts' | 'analytics' | 'sources' | 'layers' | 'settings') => {
    setActiveNav(nav);
    if (nav === 'command') {
      setActiveTab('queue_map');
      setIsFeedCollapsed(false);
    } else if (nav === 'incidents') {
      setActiveTab('queue_map');
      setIsFeedCollapsed(false);
    } else if (nav === 'alerts') {
      setActiveTab('alerts');
    } else if (nav === 'analytics' || nav === 'sources') {
      setActiveTab('analytics');
    } else if (nav === 'layers') {
      setActiveTab('queue_map');
    } else if (nav === 'settings') {
      setSettingsModalOpen(true);
    }
  };

  return (
    <div className="min-h-screen flex bg-void text-foreground font-sans selection:bg-thermal-DEFAULT selection:text-void">
      {/* 1. COMPACT NAVIGATION RAIL (Left Anchor) */}
      <NavRail
        activeView={activeNav}
        onViewChange={handleNavChange}
        incidentCount={filteredCount}
        alertCount={alerts.length}
        criticalCount={summary?.critical_risk_count ?? 0}
        isReplayActive={modePreference === 'replay'}
        onToggleReplay={() => setModePreference(modePreference === 'replay' ? 'auto' : 'replay')}
      />

      {/* Main Command Center Canvas */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* 2. SYSTEM STATUS & HEADER (Persistent System Mode, Source Health, Zone Selection) */}
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

        {/* Operational Workspace */}
        <main className="flex-1 p-3 sm:p-4 lg:p-5 space-y-3.5 max-w-[1920px] mx-auto w-full">
          {/* Global Connection / Telemetry Alert Notice */}
          {error && (
            <div
              className="p-3.5 rounded bg-destructive/15 border border-destructive/60 text-destructive text-xs flex items-center justify-between shadow-[0_0_15px_rgba(255,51,102,0.2)]"
              role="alert"
            >
              <div className="flex items-center space-x-2.5">
                <AlertCircle className="w-4 h-4 shrink-0" aria-hidden="true" />
                <span className="font-mono font-medium">{error}</span>
              </div>
              <button
                type="button"
                onClick={retry}
                className="text-xs font-mono font-bold uppercase tracking-wider underline hover:text-white ml-3 cursor-pointer"
              >
                Retry Sync
              </button>
            </div>
          )}

          {/* Compact Tactical KPI Metric Strip */}
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
            className="flex items-center space-x-2 border-b border-cyber-border pb-1 text-xs font-mono select-none"
          >
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'queue_map'}
              id="tab-queue-map"
              onClick={() => {
                setActiveTab('queue_map');
                setActiveNav('command');
              }}
              className={`flex items-center space-x-2 px-3.5 py-2 rounded-t transition-all border-b-2 font-bold uppercase tracking-wider cursor-pointer ${ activeTab === 'queue_map' ? 'border-thermal-DEFAULT text-thermal-bright bg-surface shadow-[0_-2px_10px_rgba(255,107,0,0.15)]' : 'border-transparent text-subtle hover:text-foreground hover:bg-elevated/40' }`}
            >
              <Flame className="w-3.5 h-3.5 text-thermal-DEFAULT" aria-hidden="true" />
              <span>Prioritized Queue & Tactical Map</span>
              <span className="text-[10px] px-1.5 py-0.2 rounded bg-elevated text-subtle font-mono border border-cyber-border">
                {filteredCount}
              </span>
            </button>

            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'alerts'}
              id="tab-alerts"
              onClick={() => {
                setActiveTab('alerts');
                setActiveNav('alerts');
              }}
              className={`flex items-center space-x-2 px-3.5 py-2 rounded-t transition-all border-b-2 font-bold uppercase tracking-wider cursor-pointer ${ activeTab === 'alerts' ? 'border-destructive text-destructive bg-surface shadow-[0_-2px_10px_rgba(255,51,102,0.15)]' : 'border-transparent text-subtle hover:text-foreground hover:bg-elevated/40' }`}
            >
              <Bell className="w-3.5 h-3.5 text-destructive" aria-hidden="true" />
              <span>Operational Alerts</span>
              <span className="text-[10px] px-1.5 py-0.2 rounded bg-destructive/20 text-destructive border border-destructive/50 font-mono">
                {alerts.length} Active
              </span>
            </button>

            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'analytics'}
              id="tab-analytics"
              onClick={() => {
                setActiveTab('analytics');
                setActiveNav('analytics');
              }}
              className={`flex items-center space-x-2 px-3.5 py-2 rounded-t transition-all border-b-2 font-bold uppercase tracking-wider cursor-pointer ${ activeTab === 'analytics' ? 'border-blue-400 text-blue-400 bg-surface shadow-[0_-2px_10px_rgba(0,212,255,0.15)]' : 'border-transparent text-subtle hover:text-foreground hover:bg-elevated/40' }`}
            >
              <BarChart3 className="w-3.5 h-3.5 text-blue-400" aria-hidden="true" />
              <span>Risk & Source Analytics</span>
            </button>
          </div>

          {/* PRIMARY VIEW: PRIORITIZED QUEUE + TACTICAL MAP */}
          {activeTab === 'queue_map' && (
            <div className="space-y-3">
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5 min-h-[580px] xl:min-h-[660px]">
                {/* Collapsible Incident Feed (Desktop: 4 or 5 cols, or hidden when collapsed) */}
                <div
                  className={`min-h-[460px] flex flex-col order-2 lg:order-1 transition-all duration-300 ${ isFeedCollapsed ? 'hidden' : 'lg:col-span-5 xl:col-span-4' }`}
                >
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

                {/* Tactical Geospatial Map (Dominant Center: 7, 8, or 12 cols) */}
                <section
                  id="map-container"
                  role="region"
                  aria-label="Tactical Geospatial Satellite Map"
                  className={`rounded bg-surface border border-cyber-border flex flex-col overflow-hidden shadow-2xl min-h-[480px] lg:min-h-[600px] xl:min-h-[660px] relative order-1 lg:order-2 transition-all duration-300 ${ isFeedCollapsed ? 'lg:col-span-12' : 'lg:col-span-7 xl:col-span-8' }`}
                >
                  {/* Tactical Map Header Bar */}
                  <div className="px-4 py-2 border-b border-cyber-border flex items-center justify-between bg-void/90 backdrop-blur-md z-10 font-mono">
                    <div className="flex items-center space-x-2.5">
                      <span className="w-2 h-2 rounded-full bg-destructive motion-safe:animate-ping" />
                      <h2 className="text-xs font-bold uppercase tracking-wider text-foreground font-display">
                        Geospatial Remote Sensing Map (VIIRS 375m NRT)
                      </h2>
                    </div>

                    <div className="flex items-center space-x-3 text-[11px]">
                      {/* Collapse/Expand Queue Toggle */}
                      <button
                        type="button"
                        onClick={() => setIsFeedCollapsed(!isFeedCollapsed)}
                        className="hidden lg:flex items-center space-x-1 px-2 py-0.5 rounded bg-elevated hover:bg-surface border border-cyber-border text-subtle hover:text-foreground text-[10px] font-bold uppercase tracking-wider transition-colors cursor-pointer"
                        title={isFeedCollapsed ? 'Expand Incident Queue' : 'Maximize Map Area'}
                      >
                        {isFeedCollapsed ? (
                          <>
                            <ChevronRight className="w-3 h-3 text-blue-400" />
                            <span>Show Feed</span>
                          </>
                        ) : (
                          <>
                            <ChevronLeft className="w-3 h-3 text-blue-400" />
                            <span>Maximize Map</span>
                          </>
                        )}
                      </button>

                      <span className="text-subtle font-mono">
                        {filteredCount} Rendered Hotspots
                      </span>
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

              {/* DOCKED BOTTOM OPERATIONAL TIMELINE / REPLAY CONTROL */}
              <div className="mt-2">
                <ReplayControl
                  isActive={modePreference === 'replay'}
                  onToggleReplay={(enable) => setModePreference(enable ? 'replay' : 'auto')}
                />
              </div>
            </div>
          )}

          {/* SECONDARY VIEW 2: ALERTS DEDICATED FEED */}
          {activeTab === 'alerts' && (
            <div className="max-w-4xl mx-auto space-y-4 py-2">
              <div className="flex items-center justify-between border-b border-cyber-border pb-2">
                <div>
                  <h3 className="text-sm font-bold uppercase text-foreground font-mono">
                    Dispatched Operational Threat Advisories
                  </h3>
                  <p className="text-xs text-subtle mt-0.5">
                    Real-time algorithmic alert triggers generated for high-FRP anomalies near settlements and infrastructure.
                  </p>
                </div>
                <span className="text-xs font-mono text-subtle">
                  Total: {alerts.length} Advisories
                </span>
              </div>
              <AlertsFeed
                alerts={alerts}
                onSelectIncident={(id) => {
                  setActiveTab('queue_map');
                  setActiveNav('command');
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
                <div className="p-4 rounded bg-surface border border-cyber-border shadow-xl space-y-3">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-foreground font-mono">
                    Intelligence Engine Architecture
                  </h3>
                  <p className="text-xs text-subtle leading-relaxed">
                    Thermal anomalies are normalized from near-real-time satellite passes, enriched with OSM critical infrastructure proximities and Open-Meteo fire weather indices, then evaluated by the composite ML risk engine.
                  </p>
                  <div className="p-3 rounded bg-void font-mono text-[11px] text-blue-400 space-y-1 border border-cyber-border/60">
                    <div>Algorithm: Random Forest + IsolationForest</div>
                    <div>Attribution: Feature Weight Scoring</div>
                    <div>Risk Output: Calibrated 0–100 Matrix</div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </main>

        {/* SELECTED INCIDENT: Contextual Slide-Over Dossier Drawer (Right Side) */}
        {drawerOpen && (
          <>
            {/* Backdrop: Semi-transparent to maintain geospatial context */}
            <div
              className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[2px] transition-opacity"
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

        {/* Settings / Config Modal */}
        {settingsModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <div className="w-full max-w-md bg-surface border border-cyber-border rounded p-5 shadow-2xl font-mono space-y-4">
              <div className="flex items-center justify-between border-b border-cyber-border pb-2">
                <div className="flex items-center space-x-2">
                  <Settings className="w-4 h-4 text-cyber-accent" />
                  <h3 className="font-bold text-sm text-foreground uppercase tracking-wider">
                    Operational Environment Config
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setSettingsModalOpen(false)}
                  className="text-subtle hover:text-foreground"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-3 text-xs text-subtle">
                <div>
                  <label className="text-foreground block mb-1 font-bold">TELEMETRY POLLING INTERVAL</label>
                  <div className="p-2 rounded bg-void border border-cyber-border text-blue-400">
                    30 seconds (Live NASA FIRMS / VIIRS NRT Sync)
                  </div>
                </div>

                <div>
                  <label className="text-foreground block mb-1 font-bold">GEODETIC DATUM</label>
                  <div className="p-2 rounded bg-void border border-cyber-border text-foreground">
                    WGS84 / EPSG:4326 (Spherical Mercator EPSG:3857)
                  </div>
                </div>

                <div>
                  <label className="text-foreground block mb-1 font-bold">DATA REPLICAS</label>
                  <div className="p-2 rounded bg-void border border-cyber-border text-cyber-accent">
                    Redundant Cache In-Memory + Supabase Cluster
                  </div>
                </div>
              </div>

              <div className="pt-2 border-t border-cyber-border flex justify-end">
                <button
                  type="button"
                  onClick={() => setSettingsModalOpen(false)}
                  className="px-4 py-1.5 rounded bg-cyber-accent text-void font-bold text-xs uppercase tracking-wider hover:bg-cyber-accent/80 transition-all cursor-pointer shadow-[0_0_8px_rgba(0,255,136,0.3)]"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Footer */}
        <footer className="border-t border-cyber-border/60 py-3 px-6 text-center text-xs text-subtle bg-void/90 font-mono mt-8">
          ThermalIntel Operational Command Center • Remote Sensing & AI Hazard Intelligence
        </footer>
      </div>
    </div>
  );
}
