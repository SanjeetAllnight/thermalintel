'use client';

import React from 'react';
import { Hotspot } from '../../types/api';
import { getRiskLevelMeta, getSourceMeta, formatFrp, formatRelativeTime } from '../../lib/formatters';
import { Flame, Clock, MapPin, Zap, AlertTriangle } from 'lucide-react';

interface IncidentCardProps {
  hotspot: Hotspot;
  isSelected: boolean;
  onSelect: (id: string) => void;
}

export const IncidentCard: React.FC<IncidentCardProps> = ({
  hotspot,
  isSelected,
  onSelect,
}) => {
  const meta = getRiskLevelMeta(hotspot.risk_level);
  const sourceMeta = getSourceMeta(hotspot.source_type);
  const relativeTime = formatRelativeTime(`${hotspot.acq_date}T${hotspot.acq_time.slice(0, 2)}:${hotspot.acq_time.slice(2, 4)}:00Z`);

  return (
    <div
      id={`incident-card-${hotspot.id}`}
      onClick={() => onSelect(hotspot.id)}
      className={`p-3.5 rounded-xl border transition-all cursor-pointer relative overflow-hidden group select-none ${
        isSelected
          ? 'bg-slate-900 border-red-500 shadow-lg shadow-red-500/10 ring-1 ring-red-500/50'
          : 'bg-slate-900/60 border-slate-800/90 hover:bg-slate-900/90 hover:border-slate-700'
      }`}
    >
      {/* Top Header: ID & Risk Badge */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center space-x-2">
          <span className="text-xs font-mono font-bold text-white tracking-tight">
            {hotspot.id}
          </span>
          {hotspot.is_anomaly && (
            <span
              className="text-[9px] font-mono font-bold px-1.5 py-0.2 rounded bg-rose-950 text-rose-300 border border-rose-800"
              title="Statistical Anomaly: Radiance exceeds 3-sigma historical baseline"
            >
              ANOMALY
            </span>
          )}
        </div>

        <span
          className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-md flex items-center gap-1 ${meta.badgeBg}`}
        >
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{ backgroundColor: meta.fillHex }}
          />
          {hotspot.risk_level} ({Math.round(hotspot.risk_score)})
        </span>
      </div>

      {/* Location / Nearest Place */}
      <div className="mt-2 flex items-start space-x-1.5">
        <MapPin className="w-3.5 h-3.5 text-slate-400 mt-0.5 shrink-0" />
        <div className="text-xs font-semibold text-slate-200 line-clamp-1">
          {hotspot.nearest_place || 'Unclassified Territory'}
        </div>
      </div>

      {/* Source Classification Tag & FRP Metrics */}
      <div className="mt-2.5 pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs">
        <div className="flex items-center space-x-1.5">
          <span className="text-sm">{sourceMeta.icon}</span>
          <span className="text-[11px] font-medium text-slate-300 capitalize">
            {sourceMeta.label}
          </span>
        </div>

        <div className="flex items-center space-x-3 text-[11px]">
          <div className="flex items-center space-x-1 text-cyan-400 font-mono font-bold">
            <Zap className="w-3 h-3 text-cyan-400" />
            <span>{formatFrp(hotspot.frp)}</span>
          </div>

          <div className="flex items-center space-x-1 text-slate-400 text-[10px] font-mono">
            <Clock className="w-3 h-3 text-slate-500" />
            <span>{relativeTime}</span>
          </div>
        </div>
      </div>

      {/* Selected Indicator Edge */}
      {isSelected && (
        <div className="absolute top-0 left-0 bottom-0 w-1 bg-red-500" />
      )}
    </div>
  );
};

export default IncidentCard;
