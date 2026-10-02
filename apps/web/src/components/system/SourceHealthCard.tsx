'use client';

import React from 'react';
import { SourceHealthItem } from '../../types/system';
import { ShieldCheck, Satellite, MapPin, CloudSun, Database, Cpu, HelpCircle } from 'lucide-react';

interface SourceHealthCardProps {
  sources: SourceHealthItem[];
  className?: string;
  isCompact?: boolean;
}

export const SourceHealthCard: React.FC<SourceHealthCardProps> = ({
  sources,
  className = '',
  isCompact = false,
}) => {
  const getCategoryIcon = (category: SourceHealthItem['category']) => {
    switch (category) {
      case 'satellite':
        return <Satellite className="w-3.5 h-3.5 text-cyan-400" />;
      case 'gis':
        return <MapPin className="w-3.5 h-3.5 text-emerald-400" />;
      case 'weather':
        return <CloudSun className="w-3.5 h-3.5 text-amber-400" />;
      case 'database':
        return <Database className="w-3.5 h-3.5 text-purple-400" />;
      case 'ai':
        return <Cpu className="w-3.5 h-3.5 text-rose-400" />;
      default:
        return <HelpCircle className="w-3.5 h-3.5 text-slate-400" />;
    }
  };

  const getStatusBadge = (status: SourceHealthItem['status']) => {
    switch (status) {
      case 'LIVE':
        return (
          <span className="px-1.5 py-0.5 text-[10px] font-mono font-bold rounded bg-emerald-950/80 text-emerald-300 border border-emerald-800 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            LIVE
          </span>
        );
      case 'CACHE':
        return (
          <span className="px-1.5 py-0.5 text-[10px] font-mono font-bold rounded bg-amber-950/80 text-amber-300 border border-amber-800 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
            CACHE
          </span>
        );
      case 'HEALTHY':
        return (
          <span className="px-1.5 py-0.5 text-[10px] font-mono font-bold rounded bg-emerald-950/80 text-emerald-300 border border-emerald-800 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            HEALTHY
          </span>
        );
      case 'DEGRADED':
        return (
          <span className="px-1.5 py-0.5 text-[10px] font-mono font-bold rounded bg-amber-950/80 text-amber-300 border border-amber-800 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
            DEGRADED
          </span>
        );
      case 'STANDBY':
        return (
          <span className="px-1.5 py-0.5 text-[10px] font-mono font-bold rounded bg-purple-950/80 text-purple-300 border border-purple-800">
            STANDBY
          </span>
        );
      case 'UNAVAILABLE':
      default:
        return (
          <span className="px-1.5 py-0.5 text-[10px] font-mono font-bold rounded bg-slate-900 text-slate-400 border border-slate-800">
            UNAVAILABLE
          </span>
        );
    }
  };

  if (isCompact) {
    return (
      <div
        id="compact-source-health"
        className={`flex flex-wrap items-center gap-2 text-xs font-mono ${className}`}
      >
        {sources.map((src) => (
          <div
            key={src.id}
            className="flex items-center space-x-1.5 px-2 py-0.5 rounded bg-slate-900 border border-slate-800"
            title={src.detail || `${src.name}: ${src.status}`}
          >
            {getCategoryIcon(src.category)}
            <span className="text-[11px] text-slate-300">{src.name.split(' ')[0]}</span>
            {getStatusBadge(src.status)}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div
      id="source-health-panel"
      className={`p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 shadow-md space-y-2.5 ${className}`}
    >
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center space-x-2">
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200 font-mono">
            Provider Ingestion & Source Health
          </h3>
        </div>
        <span className="text-[10px] font-mono text-slate-500">Real-time status</span>
      </div>

      <div className="space-y-1.5">
        {sources.map((src) => (
          <div
            key={src.id}
            className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-slate-950/70 border border-slate-850 hover:border-slate-800 transition-colors"
          >
            <div className="flex items-center space-x-2">
              <div className="p-1 rounded bg-slate-900 border border-slate-800">
                {getCategoryIcon(src.category)}
              </div>
              <div>
                <div className="text-xs font-semibold text-slate-200">{src.name}</div>
                {src.detail && (
                  <div className="text-[10px] text-slate-500 font-mono">{src.detail}</div>
                )}
              </div>
            </div>
            <div>{getStatusBadge(src.status)}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default SourceHealthCard;
