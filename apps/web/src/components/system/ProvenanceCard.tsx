'use client';

import React, { useState } from 'react';
import { ProvenanceRecord } from '../../types/provenance';
import { getFreshnessMeta, formatTimestamp } from '../../lib/formatters';
import { ShieldCheck, ChevronDown, ChevronRight, Clock, Hash, Database, RefreshCw } from 'lucide-react';

interface ProvenanceCardProps {
  provenance: ProvenanceRecord;
  domainName: string;
  defaultExpanded?: boolean;
  className?: string;
}

export const ProvenanceCard: React.FC<ProvenanceCardProps> = ({
  provenance,
  domainName,
  defaultExpanded = false,
  className = '',
}) => {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const meta = getFreshnessMeta(provenance.freshness_state);

  return (
    <div
      className={`rounded-lg bg-slate-950/80 border border-slate-800 text-xs font-mono overflow-hidden transition-all ${className}`}
    >
      {/* Summary Trigger Bar */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full px-3 py-2 flex items-center justify-between hover:bg-slate-900/60 transition-colors text-left"
        aria-expanded={expanded}
      >
        <div className="flex items-center space-x-2">
          <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
          <span className="font-bold text-slate-200">{domainName} Provenance</span>
          <span className="text-[10px] text-slate-400 hidden sm:inline">
            ({provenance.provider})
          </span>
        </div>

        <div className="flex items-center space-x-2">
          <span
            className={`px-1.5 py-0.5 text-[9px] uppercase font-bold rounded flex items-center gap-1 ${meta.badgeBg}`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${meta.dotColor}`} />
            {meta.label}
          </span>
          {expanded ? (
            <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
          )}
        </div>
      </button>

      {/* Expanded Evidence Details */}
      {expanded && (
        <div className="p-3 border-t border-slate-850 bg-slate-900/40 space-y-2 text-[11px] text-slate-300">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div className="flex items-start space-x-1.5">
              <Database className="w-3.5 h-3.5 text-slate-500 mt-0.5 shrink-0" />
              <div>
                <span className="text-slate-500 uppercase text-[10px] block">Provider & Dataset</span>
                <span className="font-semibold text-white">{provenance.provider}</span>
                <span className="text-slate-400 block text-[10px]">{provenance.product}</span>
              </div>
            </div>

            <div className="flex items-start space-x-1.5">
              <Clock className="w-3.5 h-3.5 text-slate-500 mt-0.5 shrink-0" />
              <div>
                <span className="text-slate-500 uppercase text-[10px] block">Observed Time (UTC)</span>
                <span className="text-slate-200">
                  {provenance.observed_at_utc ? formatTimestamp(provenance.observed_at_utc) : 'Derived / Continuous'}
                </span>
              </div>
            </div>

            <div className="flex items-start space-x-1.5">
              <RefreshCw className="w-3.5 h-3.5 text-slate-500 mt-0.5 shrink-0" />
              <div>
                <span className="text-slate-500 uppercase text-[10px] block">Ingested / Fetched Time</span>
                <span className="text-slate-200">
                  {provenance.fetched_at_utc ? formatTimestamp(provenance.fetched_at_utc) : 'At generation'}
                </span>
              </div>
            </div>

            <div className="flex items-start space-x-1.5">
              <Hash className="w-3.5 h-3.5 text-slate-500 mt-0.5 shrink-0" />
              <div>
                <span className="text-slate-500 uppercase text-[10px] block">Cache TTL & Reference</span>
                <span className="text-slate-400">
                  TTL: {provenance.ttl_seconds ? `${provenance.ttl_seconds}s` : 'Standard pass window'}
                </span>
                {provenance.reference && (
                  <span className="text-[10px] text-cyan-400 block truncate max-w-[200px]" title={provenance.reference}>
                    Ref: {provenance.reference}
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProvenanceCard;
