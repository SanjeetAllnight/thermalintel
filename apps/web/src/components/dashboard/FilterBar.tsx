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
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-3 sm:p-4 shadow-md space-y-3">
      {/* Top Filter Row: Search & Quick Chips */}
      <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
        {/* Search Input */}
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            id="filter-search-input"
            type="text"
            placeholder="Search incident ID, nearest place, cluster, or county..."
            value={filters.searchQuery}
            onChange={(e) => update({ searchQuery: e.target.value })}
            className="w-full pl-9 pr-8 py-2 rounded-lg bg-slate-950/80 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-red-500/80 focus:ring-1 focus:ring-red-500/30 font-sans transition-all"
          />
          {filters.searchQuery && (
            <button
              type="button"
              onClick={() => update({ searchQuery: '' })}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 p-0.5"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Severity Chips */}
        <div className="flex items-center space-x-1.5 overflow-x-auto pb-1 md:pb-0 text-xs">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mr-1 hidden lg:inline">
            Severity:
          </span>
          {(['all', 'critical', 'high', 'medium', 'low'] as const).map((level) => {
            const isSelected = filters.riskLevel === level;
            let activeClass = 'bg-slate-800 text-white';
            if (level === 'critical') activeClass = 'bg-red-500 text-white shadow-md shadow-red-500/30';
            if (level === 'high') activeClass = 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/30 font-bold';
            if (level === 'medium') activeClass = 'bg-yellow-500 text-slate-950';
            if (level === 'low') activeClass = 'bg-slate-700 text-slate-200';

            return (
              <button
                key={level}
                id={`filter-severity-${level}`}
                type="button"
                onClick={() => update({ riskLevel: level })}
                className={`px-2.5 py-1 rounded-md text-[11px] uppercase font-bold tracking-wider transition-all whitespace-nowrap ${
                  isSelected
                    ? activeClass
                    : 'bg-slate-950/60 text-slate-400 hover:text-slate-200 border border-slate-800'
                }`}
              >
                {level}
              </button>
            );
          })}
        </div>
      </div>

      {/* Bottom Filter Row: Source Type, Min FRP, Anomaly Toggle, and Clear Button */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800/80 text-xs">
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Classification / Source Selector */}
          <div className="flex items-center space-x-1.5 bg-slate-950/80 border border-slate-800 rounded-lg px-2.5 py-1">
            <Filter className="w-3 h-3 text-slate-400" />
            <span className="text-[11px] text-slate-400">Source:</span>
            <select
              id="filter-source-select"
              value={filters.sourceType}
              onChange={(e) => update({ sourceType: e.target.value as SourceType | 'all' })}
              className="bg-transparent text-slate-200 font-medium focus:outline-none cursor-pointer pr-1 text-xs"
            >
              <option value="all" className="bg-slate-900 text-white">All Sources</option>
              <option value="wildfire" className="bg-slate-900 text-white">🔥 Wildfire / Forest Fire</option>
              <option value="industrial" className="bg-slate-900 text-white">🏭 Industrial / Flare Stack</option>
              <option value="agricultural" className="bg-slate-900 text-white">🌾 Agricultural Burn</option>
              <option value="prescribed_burn" className="bg-slate-900 text-white">🌲 Prescribed Burn</option>
              <option value="urban" className="bg-slate-900 text-white">🏢 Urban / Structure</option>
              <option value="volcanic" className="bg-slate-900 text-white">🌋 Volcanic Caldera</option>
              <option value="unknown" className="bg-slate-900 text-white">❓ Unknown Signature</option>
            </select>
          </div>

          {/* Min FRP Threshold */}
          <div className="flex items-center space-x-1.5 bg-slate-950/80 border border-slate-800 rounded-lg px-2.5 py-1">
            <SlidersHorizontal className="w-3 h-3 text-cyan-400" />
            <span className="text-[11px] text-slate-400">Min FRP:</span>
            <select
              id="filter-min-frp"
              value={filters.minFrp}
              onChange={(e) => update({ minFrp: Number(e.target.value) })}
              className="bg-transparent text-slate-200 font-medium focus:outline-none cursor-pointer pr-1 text-xs"
            >
              <option value={0} className="bg-slate-900 text-white">Any Intensity (≥ 0 MW)</option>
              <option value={25} className="bg-slate-900 text-white">≥ 25 MW</option>
              <option value={50} className="bg-slate-900 text-white">≥ 50 MW (Elevated)</option>
              <option value={100} className="bg-slate-900 text-white">≥ 100 MW (Extreme)</option>
            </select>
          </div>

          {/* Anomaly Only Toggle */}
          <label className="flex items-center space-x-1.5 cursor-pointer bg-slate-950/80 border border-slate-800 rounded-lg px-2.5 py-1 hover:border-slate-700 transition-all select-none">
            <input
              id="filter-anomaly-only"
              type="checkbox"
              checked={filters.anomalyOnly}
              onChange={(e) => update({ anomalyOnly: e.target.checked })}
              className="rounded bg-slate-800 border-slate-700 text-red-500 focus:ring-0 w-3.5 h-3.5 cursor-pointer accent-red-500"
            >
            </input>
            <span className="text-[11px] font-medium text-slate-300 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
              Statistical Anomalies Only
            </span>
          </label>
        </div>

        {/* Status Indicator & Reset */}
        <div className="flex items-center space-x-3 ml-auto">
          <div className="text-[11px] font-mono text-slate-400">
            Showing <strong className="text-white">{filteredCount}</strong> of{' '}
            <span className="text-slate-500">{totalCount}</span> anomalies
          </div>

          {hasActiveFilters && (
            <button
              id="btn-clear-filters"
              type="button"
              onClick={onReset}
              className="flex items-center space-x-1 px-2.5 py-1 rounded bg-slate-800/80 hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-700/60 text-[11px] font-medium transition-all"
            >
              <X className="w-3 h-3" />
              <span>Clear Filters</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default FilterBar;
