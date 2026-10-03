'use client';

import React, { useState, useEffect } from 'react';
import { HealthResponse, DataMode } from '../../types/api';
import { SystemMode, SourceHealthItem } from '../../types/system';
import { AppDataMode } from '../../lib/data-provider';
import { SystemModeBadge } from '../system/SystemModeBadge';
import { SourceHealthCard } from '../system/SourceHealthCard';
import { RefreshCw, Radio, Satellite, Flame, Activity, X, Clock, Terminal } from 'lucide-react';

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
  const [currentTimeUtc, setCurrentTimeUtc] = useState<string>('');

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setCurrentTimeUtc(
        now.toISOString().replace('T', ' ').substring(0, 19) + ' UTC'
      );
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header
      id="operational-header"
      className="border-b border-subtle bg-void/95 backdrop-blur-md px-3 sm:px-5 py-2 sticky top-0 z-40 flex flex-wrap items-center justify-between gap-3 shadow-2xl relative"
    >
      {/* Brand & Mission Title */}
      <div className="flex items-center space-x-3">
        <div className="relative flex items-center justify-center w-8 h-8 rounded-lg bg-thermal-orange">
          <Flame className="w-4 h-4 text-white" aria-hidden="true" />
          <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-emerald-400 border-2 border-void" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-sm sm:text-base font-black tracking-wider uppercase text-white font-mono" data-text="ThermalIntel">
              <span>Thermal</span><span className="text-thermal-orange">Intel</span>
            </span>
            <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-surface text-cyan-300 font-bold tracking-wider">
              OPERATIONAL COMMAND
            </span>
          </div>
          <div className="flex items-center space-x-2 text-[10px] font-mono text-slate-400">
            <span className="hidden md:inline">VIIRS 375m NRT • EPSG:3857</span>
            {currentTimeUtc && (
              <>
                <span className="text-slate-600 hidden md:inline">•</span>
                <span className="text-blue-400 flex items-center gap-1 font-bold">
                  <Clock className="w-3 h-3" />
                  {currentTimeUtc}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Center Controls: Monitoring Region Selector */}
      <div className="hidden lg:flex items-center space-x-2 px-3 py-1 rounded bg-surface/90 text-xs font-mono">
        <Satellite className="w-3.5 h-3.5 text-blue-400" aria-hidden="true" />
        <label htmlFor="select-monitoring-region" className="text-slate-400 font-medium text-[11px] uppercase tracking-wider">
          Zone:
        </label>
        <select
          id="select-monitoring-region"
          value={selectedRegion}
          onChange={(e) => onRegionChange(e.target.value)}
          className="bg-transparent text-slate-200 font-semibold focus:outline-none cursor-pointer pr-1 text-xs"
        >
          <option value="all" className="bg-surface text-white">All Continental Passes (US/Global)</option>
          <option value="california" className="bg-surface text-white">California Fire Complex (Sonoma/Angeles)</option>
          <option value="gulf_industrial" className="bg-surface text-white">Gulf Coast Industrial Corridors (TX)</option>
          <option value="pacific_nw" className="bg-surface text-white">Pacific NW Managed Parcels (OR/WA)</option>
          <option value="hawaii" className="bg-surface text-white">Hawaii Volcanic Rift (Kīlauea)</option>
        </select>
      </div>

      {/* Right Controls: Telemetry Mode, System Health & Sync Action */}
      <div className="flex items-center space-x-2 sm:space-x-2.5">
        {/* System Mode Preference Switcher (Auto / Demo / Replay) */}
        <div className="flex items-center rounded bg-surface p-0.5 text-xs font-mono">
          <button
            type="button"
            id="btn-mode-auto"
            onClick={() => onModeChange('auto')}
            title="Auto-detect API or fallback to local demo data"
            className={`flex items-center space-x-1.5 px-2 py-0.5 rounded transition-all ${ modePreference === 'auto' ? 'bg-elevated text-blue-400 shadow-sm font-bold border border-blue-400/30' : 'text-slate-400 hover:text-slate-200' }`}
          >
            <Radio className="w-3 h-3 text-blue-400" aria-hidden="true" />
            <span className="text-[10px] uppercase">Auto</span>
          </button>
          <button
            type="button"
            id="btn-mode-demo"
            onClick={() => onModeChange('demo')}
            title="Force deterministic local demo simulation"
            className={`flex items-center space-x-1 px-2 py-0.5 rounded transition-all ${ modePreference === 'demo' ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm font-bold' : 'text-slate-400 hover:text-slate-200' }`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
            <span className="text-[10px] uppercase">Demo</span>
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
          className={`flex items-center space-x-1.5 px-2.5 py-1 rounded bg-surface hover:bg-elevated border text-xs font-mono transition-colors cursor-pointer ${ showHealthModal ? 'border-blue-400 text-blue-400 shadow-sm' : 'border-subtle text-slate-300' }`}
          title="Inspect Telemetry Ingestion Source Health"
          aria-expanded={showHealthModal}
        >
          <Activity className="w-3.5 h-3.5 text-blue-400" />
          <span className="hidden sm:inline text-[11px] uppercase tracking-wider">Sources</span>
        </button>

        {/* Sync Telemetry Button */}
        <button
          id="btn-sync-refresh"
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          className="flex items-center space-x-1.5 px-3 py-1 text-xs font-bold font-mono rounded bg-thermal-orange hover:bg-orange-500 active:scale-95 disabled:opacity-50 text-white transition-all shadow-sm cursor-pointer"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          <span className="hidden sm:inline uppercase tracking-wider">
            {refreshing ? 'Syncing...' : 'Sync Telemetry'}
          </span>
          <span className="sm:hidden uppercase">{refreshing ? '...' : 'Sync'}</span>
        </button>
      </div>

      {/* Source Health Modal Dropdown */}
      {showHealthModal && (
        <div className="absolute top-full right-4 mt-2 z-50 w-80 sm:w-96 shadow-2xl">
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowHealthModal(false)}
              className="absolute top-3 right-3 text-slate-400 hover:text-white p-1 z-10 cursor-pointer"
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

