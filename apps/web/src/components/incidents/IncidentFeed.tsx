'use client';

import React, { useState, useMemo } from 'react';
import { Hotspot } from '../../types/api';
import { IncidentCard } from './IncidentCard';
import { Flame, ArrowUpDown, FilterX, Radio } from 'lucide-react';

interface IncidentFeedProps {
  hotspots: Hotspot[];
  selectedHotspotId: string | null;
  onSelectIncident: (id: string) => void;
  loading: boolean;
  onResetFilters?: () => void;
}

type SortField = 'risk' | 'frp' | 'time';

export const IncidentFeed: React.FC<IncidentFeedProps> = ({
  hotspots,
  selectedHotspotId,
  onSelectIncident,
  loading,
  onResetFilters,
}) => {
  const [sortBy, setSortBy] = useState<SortField>('risk');

  // Sorted Hotspots
  const sortedHotspots = useMemo(() => {
    return [...hotspots].sort((a, b) => {
      if (sortBy === 'risk') {
        return b.risk_score - a.risk_score;
      }
      if (sortBy === 'frp') {
        return b.frp - a.frp;
      }
      if (sortBy === 'time') {
        const timeA = `${a.acq_date} ${a.acq_time}`;
        const timeB = `${b.acq_date} ${b.acq_time}`;
        return timeB.localeCompare(timeA);
      }
      return 0;
    });
  }, [hotspots, sortBy]);

  return (
    <section
      id="incident-list-container"
      className="rounded-xl bg-slate-900/90 border border-slate-800 flex flex-col overflow-hidden shadow-lg h-full"
    >
      {/* Header with Sort and Records Counter */}
      <div className="px-4 py-3 border-b border-slate-800/80 bg-slate-900/95 flex items-center justify-between gap-2">
        <div className="flex items-center space-x-2">
          <Flame className="w-4 h-4 text-red-500" />
          <h2 className="text-sm font-bold text-white tracking-wide uppercase font-mono">
            Incident Queue
          </h2>
          <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
            {hotspots.length} Active
          </span>
        </div>

        {/* Sort Selector */}
        <div className="flex items-center space-x-1.5 text-xs">
          <ArrowUpDown className="w-3 h-3 text-slate-400" />
          <select
            id="select-incident-sort"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortField)}
            className="bg-slate-950 border border-slate-800 rounded px-2 py-0.5 text-slate-300 text-[11px] font-medium focus:outline-none cursor-pointer"
          >
            <option value="risk">Sort by Risk Score</option>
            <option value="frp">Sort by Radiative Power (MW)</option>
            <option value="time">Sort by Acquisition Time</option>
          </select>
        </div>
      </div>

      {/* Incident List Body */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5 max-h-[580px]">
        {loading && hotspots.length === 0 ? (
          <div className="p-8 text-center space-y-2 text-slate-500">
            <Radio className="w-6 h-6 mx-auto animate-pulse text-cyan-400" />
            <div className="text-xs font-semibold">Streaming incident telemetry...</div>
          </div>
        ) : hotspots.length === 0 ? (
          <div className="p-8 text-center space-y-3">
            <div className="w-10 h-10 rounded-full bg-slate-800/80 border border-slate-700 mx-auto flex items-center justify-center text-slate-400">
              <FilterX className="w-5 h-5 text-slate-400" />
            </div>
            <div className="text-xs font-semibold text-slate-300">
              No thermal anomalies match criteria
            </div>
            <p className="text-[11px] text-slate-500 max-w-xs mx-auto">
              Try adjusting the minimum FRP threshold, clearing the search query, or selecting all severities.
            </p>
            {onResetFilters && (
              <button
                type="button"
                onClick={onResetFilters}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded text-xs font-medium transition-all"
              >
                Reset All Filters
              </button>
            )}
          </div>
        ) : (
          sortedHotspots.map((h) => (
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
        <span>PRIORITY: HIGHEST COMPOSITE RISK</span>
        <span>SELECT TO INSPECT &rarr;</span>
      </div>
    </section>
  );
};

export default IncidentFeed;
