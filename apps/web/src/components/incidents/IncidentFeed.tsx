'use client';

import React from 'react';
import { Hotspot } from '../../types/api';
import { SortField } from '../../hooks/useIncidentFilter';
import { IncidentCard } from './IncidentCard';
import { Flame, ArrowUpDown, FilterX, Radio } from 'lucide-react';

interface IncidentFeedProps {
  hotspots: Hotspot[];
  selectedHotspotId: string | null;
  onSelectIncident: (id: string) => void;
  loading: boolean;
  sortBy: SortField;
  onSortChange: (sort: SortField) => void;
  onResetFilters?: () => void;
}

export const IncidentFeed: React.FC<IncidentFeedProps> = ({
  hotspots,
  selectedHotspotId,
  onSelectIncident,
  loading,
  sortBy,
  onSortChange,
  onResetFilters,
}) => {
  return (
    <section
      id="incident-list-container"
      role="region"
      aria-label="Prioritized Incident Queue"
      className="rounded-xl bg-slate-900/90 border border-slate-800 flex flex-col overflow-hidden shadow-lg h-full"
    >
      {/* Header with Sort and Records Counter */}
      <div className="px-4 py-3 border-b border-slate-800/80 bg-slate-900/95 flex items-center justify-between gap-2">
        <div className="flex items-center space-x-2">
          <Flame className="w-4 h-4 text-red-500" aria-hidden="true" />
          <h2 className="text-sm font-bold text-white tracking-wide uppercase font-mono">
            Incident Queue
          </h2>
          <span
            id="incident-queue-count"
            className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 font-bold"
          >
            {hotspots.length} Active
          </span>
        </div>

        {/* Sort Selector */}
        <div className="flex items-center space-x-1.5 text-xs font-mono">
          <ArrowUpDown className="w-3 h-3 text-slate-400" aria-hidden="true" />
          <label htmlFor="select-incident-sort" className="sr-only">
            Sort Incidents By
          </label>
          <select
            id="select-incident-sort"
            value={sortBy}
            onChange={(e) => onSortChange(e.target.value as SortField)}
            className="bg-slate-950 border border-slate-800 rounded px-2 py-1 text-slate-200 text-[11px] font-medium focus:outline-none focus:ring-1 focus:ring-cyan-400 cursor-pointer"
          >
            <option value="risk">Highest Risk</option>
            <option value="frp">Radiative Power (MW)</option>
            <option value="time">Acquisition Time</option>
            <option value="severity">Severity Tier</option>
          </select>
        </div>
      </div>

      {/* Incident List Body */}
      <div
        className="flex-1 overflow-y-auto p-3 space-y-2.5 max-h-[580px] focus:outline-none"
        tabIndex={0}
        aria-label="Incident Cards List (Use Up/Down arrows to navigate)"
      >
        {loading && hotspots.length === 0 ? (
          <div className="p-8 text-center space-y-3 text-slate-400">
            <Radio className="w-6 h-6 mx-auto animate-pulse text-cyan-400" aria-hidden="true" />
            <div className="text-xs font-semibold text-slate-300">
              Correlating orbital satellite passes...
            </div>
            <p className="text-[11px] text-slate-500 max-w-xs mx-auto">
              Scanning VIIRS 375m radiance telemetry and geospatial infrastructure layers.
            </p>
          </div>
        ) : hotspots.length === 0 ? (
          <div className="p-8 text-center space-y-3" role="status">
            <div className="w-10 h-10 rounded-full bg-slate-800/80 border border-slate-700 mx-auto flex items-center justify-center text-slate-400">
              <FilterX className="w-5 h-5 text-slate-400" aria-hidden="true" />
            </div>
            <div className="text-xs font-semibold text-slate-200">
              No incidents match operational filters
            </div>
            <p className="text-[11px] text-slate-400 max-w-xs mx-auto">
              Adjust minimum FRP threshold, clear search term, or expand severity filter tiers.
            </p>
            {onResetFilters && (
              <button
                type="button"
                id="btn-reset-filters-empty"
                onClick={onResetFilters}
                className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 active:scale-95 text-white rounded-lg text-xs font-semibold transition-all border border-slate-700 cursor-pointer"
              >
                Reset All Filters
              </button>
            )}
          </div>
        ) : (
          hotspots.map((h) => (
            <IncidentCard
              key={h.id}
              hotspot={h}
              isSelected={selectedHotspotId === h.id}
              onSelect={onSelectIncident}
            />
          ))
        )}
      </div>

      {/* Footer Info */}
      <div className="px-4 py-2 border-t border-slate-800/80 bg-slate-950/80 text-[11px] text-slate-500 flex items-center justify-between font-mono">
        <span className="hidden sm:inline">NAVIGATE: ARROW KEYS ↑ / ↓</span>
        <span className="sm:hidden">QUEUE READY</span>
        <span>SELECT TO INSPECT &rarr;</span>
      </div>
    </section>
  );
};

export default IncidentFeed;
