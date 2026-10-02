'use client';

import React, { useState } from 'react';
import { HealthResponse, DataMode } from '../../types/api';
import { SystemMode, SourceHealthItem } from '../../types/system';
import { AppDataMode } from '../../lib/data-provider';
import { SystemModeBadge } from '../system/SystemModeBadge';
import { SourceHealthCard } from '../system/SourceHealthCard';
import { RefreshCw, Radio, Satellite, ShieldCheck, Flame, Activity, X } from 'lucide-react';

interface HeaderProps {
  health: HealthResponse | null;
  dataMode: DataMode;
  systemMode: SystemMode;
  modePreference: AppDataMode;
  sourceHealthList: SourceHealthItem[];
  cacheAgeSeconds?: number;
  isStale?: boolean;
  onModeChange: (mode: AppDataMode) => void;
  onRefresh: () => void;
  refreshing: boolean;
  selectedRegion: string;
  onRegionChange: (region: string) => void;
  lastUpdated?: string;
}

export const Header: React.FC<HeaderProps> = ({
  health,
  dataMode,
  systemMode,
  modePreference,
  sourceHealthList,
  cacheAgeSeconds = 0,
  isStale = false,
  onModeChange,
  onRefresh,
  refreshing,
  selectedRegion,
  onRegionChange,
  lastUpdated,
}) => {
  const [showHealthModal, setShowHealthModal] = useState(false);

  return (
    <header className="border-b border-slate-800/80 bg-slate-950/95 backdrop-blur-md px-4 lg:px-6 py-2.5 sticky top-0 z-40 flex flex-wrap items-center justify-between gap-3 shadow-lg shadow-black/40">
      {/* Brand & Mission Title */}
      <div className="flex items-center space-x-3.5">
        <div className="relative flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-br from-amber-500 via-orange-600 to-red-600 shadow-md shadow-red-500/25 border border-red-400/30">
          <Flame className="w-5 h-5 text-white" aria-hidden="true" />
          <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-emerald-400 border-2 border-slate-950 motion-safe:animate-ping" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-base font-black tracking-wider uppercase text-white font-mono">
              Thermal<span className="text-red-500">Intel</span>
            </span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800/90 text-slate-300 border border-slate-700/80 font-bold">
              OPERATIONAL COMMAND
            </span>
          </div>
          <p className="text-[11px] text-slate-400 hidden sm:block">
            Satellite Thermal Radiance & Geospatial Risk Decision-Support System
          </p>
        </div>
      </div>

      {/* Center Controls: Monitoring Region Selector */}
      <div className="hidden xl:flex items-center space-x-2 px-3 py-1 rounded-lg bg-slate-900/90 border border-slate-800 text-xs font-mono">
        <Satellite className="w-3.5 h-3.5 text-cyan-400" aria-hidden="true" />
        <label htmlFor="select-monitoring-region" className="text-slate-400 font-medium">
          Monitoring Zone:
        </label>
        <select
          id="select-monitoring-region"
          value={selectedRegion}
          onChange={(e) => onRegionChange(e.target.value)}
          className="bg-transparent text-slate-200 font-semibold focus:outline-none cursor-pointer pr-1"
        >
          <option value="all" className="bg-slate-900 text-white">All Active Continental Passes (US/Global)</option>
          <option value="california" className="bg-slate-900 text-white">California Fire Complex (Sonoma/Angeles)</option>
          <option value="gulf_industrial" className="bg-slate-900 text-white">Gulf Coast Industrial Corridors (TX)</option>
          <option value="pacific_nw" className="bg-slate-900 text-white">Pacific Northwest & Managed Parcels (OR/WA)</option>
          <option value="hawaii" className="bg-slate-900 text-white">Hawaii Volcanic Rift (Kīlauea)</option>
        </select>
      </div>

      {/* Right Controls: Telemetry Mode, System Health & Sync Action */}
      <div className="flex items-center space-x-2.5 sm:space-x-3">
        {/* System Mode Preference Switcher (Auto / Demo / Replay) */}
        <div className="flex items-center rounded-lg bg-slate-900 p-0.5 border border-slate-800 text-xs font-mono">
          <button
            type="button"
            id="btn-mode-auto"
            onClick={() => onModeChange('auto')}
            title="Auto-detect API or fallback to local demo data"
            className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-md transition-all ${
              modePreference === 'auto'
                ? 'bg-slate-800 text-white shadow-sm font-bold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Radio className="w-3 h-3 text-cyan-400" aria-hidden="true" />
            <span className="text-[11px]">Auto</span>
          </button>
          <button
            type="button"
            id="btn-mode-demo"
            onClick={() => onModeChange('demo')}
            title="Force deterministic local demo simulation"
            className={`flex items-center space-x-1 px-2.5 py-1 rounded-md transition-all ${
              modePreference === 'demo'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm font-bold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
            <span className="text-[11px]">Demo</span>
          </button>
        </div>

        {/* Persistent System Mode Indicator Badge (Requirement 7) */}
        <SystemModeBadge
          mode={systemMode}
          cacheAgeSeconds={cacheAgeSeconds}
          isStale={isStale}
        />

        {/* Source Health Button Trigger (Requirement 8) */}
        <button
          type="button"
          id="btn-source-health-modal"
          onClick={() => setShowHealthModal(!showHealthModal)}
          className="flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs text-slate-300 font-mono transition-colors"
          title="Inspect Telemetry Ingestion Source Health"
          aria-expanded={showHealthModal}
        >
          <Activity className="w-3.5 h-3.5 text-cyan-400" />
          <span className="hidden md:inline">Sources</span>
        </button>

        {/* Sync Telemetry Button */}
        <button
          id="btn-sync-refresh"
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          className="flex items-center space-x-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-500 hover:to-rose-500 active:scale-95 disabled:opacity-50 text-white transition-all shadow-md shadow-red-600/25 border border-red-500/40 cursor-pointer"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          <span className="hidden sm:inline">{refreshing ? 'Syncing...' : 'Sync Telemetry'}</span>
          <span className="sm:hidden">{refreshing ? '...' : 'Sync'}</span>
        </button>
      </div>

      {/* Source Health Modal Dropdown */}
      {showHealthModal && (
        <div className="absolute top-full right-4 mt-2 z-50 w-80 sm:w-96 shadow-2xl">
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowHealthModal(false)}
              className="absolute top-3 right-3 text-slate-400 hover:text-white p-1 z-10"
              aria-label="Close Source Health Panel"
            >
              <X className="w-4 h-4" />
            </button>
            <SourceHealthCard sources={sourceHealthList} />
          </div>
        </div>
      )}
    </header>
  );
};

export default Header;
