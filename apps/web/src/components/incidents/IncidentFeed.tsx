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
      className="rounded bg-surface/95 flex flex-col overflow-hidden shadow-2xl h-full"
    >
      {/* Header with Sort and Records Counter */}
      <div className="px-3.5 py-2.5 border-b border-subtle bg-void/90 flex items-center justify-between gap-2">
        <div className="flex items-center space-x-2">
          <Flame className="w-4 h-4 text-thermal-orange" aria-hidden="true" />
          <h2 className="text-xs sm:text-sm font-bold text-white tracking-wider uppercase font-mono">
            Incident Queue
          </h2>
          <span
            id="incident-queue-count"
            className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-elevated text-blue-400 font-bold"
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
            className="bg-surface rounded px-2 py-0.5 text-slate-200 text-[10px] font-medium focus:outline-none focus:ring-1 focus:ring-blue-400 cursor-pointer"
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
        className="flex-1 overflow-y-auto p-2.5 space-y-2 max-h-[580px] focus:outline-none"
        tabIndex={0}
        aria-label="Incident Cards List (Use Up/Down arrows to navigate)"
      >
        {loading && hotspots.length === 0 ? (
          <div className="p-8 text-center space-y-3 text-slate-400">
            <Radio className="w-6 h-6 mx-auto animate-pulse text-blue-400" aria-hidden="true" />
            <div className="text-xs font-semibold text-slate-300 font-mono">
              Correlating orbital satellite passes...
            </div>
            <p className="text-[11px] text-slate-500 max-w-xs mx-auto">
              Scanning VIIRS 375m radiance telemetry and geospatial infrastructure layers.
            </p>
          </div>
        ) : hotspots.length === 0 ? (
          <div className="p-8 text-center space-y-3" role="status">
            <div className="w-10 h-10 rounded bg-elevated mx-auto flex items-center justify-center text-slate-400">
              <FilterX className="w-5 h-5 text-slate-400" aria-hidden="true" />
            </div>
            <div className="text-xs font-semibold text-slate-200 font-mono">
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
                className="px-3.5 py-1.5 bg-elevated hover:bg-surface active:scale-95 text-white rounded text-xs font-semibold transition-all cursor-pointer font-mono uppercase"
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
      <div className="px-3.5 py-1.5 border-t border-subtle bg-void text-[10px] text-slate-500 flex items-center justify-between font-mono">
        <span className="hidden sm:inline">NAVIGATE: ARROW KEYS ↑ / ↓</span>
        <span className="sm:hidden">QUEUE READY</span>
        <span>SELECT TO INSPECT &rarr;</span>
      </div>
    </section>
  );
};

export default IncidentFeed;
