'use client';

import React from 'react';
import { RiskLevel, SourceType } from '../../types/api';
import { Search, Filter, X, SlidersHorizontal, AlertCircle } from 'lucide-react';

export interface FilterState {
  searchQuery: string;
  riskLevel: RiskLevel | 'all';
  sourceType: SourceType | 'all';
  minFrp: number;
  anomalyOnly: boolean;
  minConfidence: string;
}

interface FilterBarProps {
  filters: FilterState;
  onChange: (filters: FilterState) => void;
  onReset: () => void;
  totalCount: number;
  filteredCount: number;
}

export const FilterBar: React.FC<FilterBarProps> = ({
  filters,
  onChange,
  onReset,
  totalCount,
  filteredCount,
}) => {
  const hasActiveFilters =
    filters.searchQuery !== '' ||
    filters.riskLevel !== 'all' ||
    filters.sourceType !== 'all' ||
    filters.minFrp > 0 ||
    filters.anomalyOnly ||
    filters.minConfidence !== 'all';

  const update = (partial: Partial<FilterState>) => {
    onChange({ ...filters, ...partial });
  };

  return (
    <div className="bg-surface/90 border border-border-color rounded p-3 sm:p-3.5 shadow-xl space-y-2.5 cyber-chamfer-xs">
      {/* Top Filter Row: Search & Quick Chips */}
      <div className="flex flex-col md:flex-row gap-2.5 items-stretch md:items-center justify-between">
        {/* Search Input with Terminal '>' prompt styling */}
        <div className="relative flex-1 min-w-[220px]">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-cyber-cyan font-mono font-bold text-xs select-none">
            &gt;
          </span>
          <input
            id="filter-search-input"
            type="text"
            placeholder="Search incident ID, nearest place, cluster, or county..."
            value={filters.searchQuery}
            onChange={(e) => update({ searchQuery: e.target.value })}
            className="w-full pl-7 pr-8 py-1.5 rounded bg-void/90 border border-border-color text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyber-cyan focus:ring-1 focus:ring-cyber-cyan font-mono transition-all cyber-chamfer-xs"
          />
          {filters.searchQuery && (
            <button
              type="button"
              onClick={() => update({ searchQuery: '' })}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white p-0.5 cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Severity Chips */}
        <div className="flex items-center space-x-1.5 overflow-x-auto pb-1 md:pb-0 text-xs">
          <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest mr-1 hidden lg:inline">
            SEVERITY:
          </span>
          {(['all', 'critical', 'high', 'medium', 'low'] as const).map((level) => {
            const isSelected = filters.riskLevel === level;
            let activeClass = 'bg-elevated text-white border-slate-600';
            if (level === 'critical') activeClass = 'bg-red-500 text-white shadow-md shadow-red-500/40 border-red-400';
            if (level === 'high') activeClass = 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/40 font-bold border-amber-400';
            if (level === 'medium') activeClass = 'bg-yellow-500 text-slate-950 font-bold border-yellow-400';
            if (level === 'low') activeClass = 'bg-slate-700 text-slate-200 border-slate-600';

            return (
              <button
                key={level}
                id={`filter-severity-${level}`}
                type="button"
                onClick={() => update({ riskLevel: level })}
                className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase font-bold tracking-wider transition-all whitespace-nowrap cyber-chamfer-xs cursor-pointer ${
                  isSelected
                    ? activeClass
                    : 'bg-void text-slate-400 hover:text-slate-200 border border-border-color'
                }`}
              >
                {level}
              </button>
            );
          })}
        </div>
      </div>

      {/* Bottom Filter Row: Source Type, Min FRP, Anomaly Toggle, and Clear Button */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 pt-2 border-t border-border-color/70 text-xs font-mono">
        <div className="flex flex-wrap items-center gap-2">
          {/* Classification / Source Selector */}
          <div className="flex items-center space-x-1.5 bg-void border border-border-color rounded px-2 py-0.5 cyber-chamfer-xs">
            <Filter className="w-3 h-3 text-cyber-cyan" />
            <span className="text-[10px] text-slate-400 uppercase">Source:</span>
            <select
              id="filter-source-select"
              value={filters.sourceType}
              onChange={(e) => update({ sourceType: e.target.value as SourceType | 'all' })}
              className="bg-transparent text-slate-200 font-medium focus:outline-none cursor-pointer pr-1 text-xs"
            >
              <option value="all" className="bg-surface text-white">All Sources</option>
              <option value="wildfire" className="bg-surface text-white">🔥 Wildfire / Forest Fire</option>
              <option value="industrial" className="bg-surface text-white">🏭 Industrial / Flare Stack</option>
              <option value="agricultural" className="bg-surface text-white">🌾 Agricultural Burn</option>
              <option value="prescribed_burn" className="bg-surface text-white">🌲 Prescribed Burn</option>
              <option value="urban" className="bg-surface text-white">🏢 Urban / Structure</option>
              <option value="volcanic" className="bg-surface text-white">🌋 Volcanic Caldera</option>
              <option value="unknown" className="bg-surface text-white">❓ Unknown Signature</option>
            </select>
          </div>

          {/* Min FRP Threshold */}
          <div className="flex items-center space-x-1.5 bg-void border border-border-color rounded px-2 py-0.5 cyber-chamfer-xs">
            <SlidersHorizontal className="w-3 h-3 text-thermal-orange" />
            <span className="text-[10px] text-slate-400 uppercase">Min FRP:</span>
            <select
              id="filter-min-frp"
              value={filters.minFrp}
              onChange={(e) => update({ minFrp: Number(e.target.value) })}
              className="bg-transparent text-slate-200 font-medium focus:outline-none cursor-pointer pr-1 text-xs"
            >
              <option value={0} className="bg-surface text-white">Any Intensity (≥ 0 MW)</option>
              <option value={25} className="bg-surface text-white">≥ 25 MW</option>
              <option value={50} className="bg-surface text-white">≥ 50 MW (Elevated)</option>
              <option value={100} className="bg-surface text-white">≥ 100 MW (Extreme)</option>
            </select>
          </div>

          {/* Anomaly Only Toggle */}
          <label className="flex items-center space-x-1.5 cursor-pointer bg-void border border-border-color rounded px-2.5 py-0.5 hover:border-border-color/80 transition-all select-none cyber-chamfer-xs">
            <input
              id="filter-anomaly-only"
              type="checkbox"
              checked={filters.anomalyOnly}
              onChange={(e) => update({ anomalyOnly: e.target.checked })}
              className="rounded bg-elevated border-slate-700 text-thermal-orange focus:ring-0 w-3.5 h-3.5 cursor-pointer accent-orange-500"
            />
            <span className="text-[10px] font-semibold text-slate-300 flex items-center gap-1 uppercase">
              <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
              Statistical Anomalies Only
            </span>
          </label>
        </div>

        {/* Status Indicator & Reset */}
        <div className="flex items-center space-x-2.5 ml-auto">
          <div className="text-[10px] font-mono text-slate-400">
            Showing <strong className="text-white">{filteredCount}</strong> /{' '}
            <span className="text-slate-500">{totalCount}</span> anomalies
          </div>

          {hasActiveFilters && (
            <button
              id="btn-clear-filters"
              type="button"
              onClick={onReset}
              className="flex items-center space-x-1 px-2 py-0.5 rounded bg-surface hover:bg-elevated text-slate-300 hover:text-white border border-border-color text-[10px] font-medium transition-all cyber-chamfer-xs cursor-pointer"
            >
              <X className="w-3 h-3" />
              <span>Clear</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default FilterBar;
