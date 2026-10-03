'use client';

import React from 'react';
import { Hotspot } from '../../types/api';
import {
  getRiskLevelMeta,
  getSourceMeta,
  formatFrp,
  formatRelativeTime,
  formatTimestamp,
  getIncidentStatus,
  getIncidentStatusMeta,
  getIncidentChangeIndicator,
} from '../../lib/formatters';
import {
  ShieldAlert,
  AlertTriangle,
  AlertCircle,
  Info,
  Clock,
  MapPin,
  Zap,
  TrendingUp,
} from 'lucide-react';

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
  const status = getIncidentStatus(hotspot);
  const statusMeta = getIncidentStatusMeta(status);
  const changeIndicator = getIncidentChangeIndicator(hotspot);

  const acquisitionIso = `${hotspot.acq_date}T${hotspot.acq_time.slice(0, 2)}:${hotspot.acq_time.slice(2, 4)}:00Z`;
  const relativeTime = formatRelativeTime(acquisitionIso);
  const exactTime = formatTimestamp(acquisitionIso);

  // Non-color severity icon
  const getSeverityIcon = () => {
    switch (hotspot.risk_level.toLowerCase()) {
      case 'critical':
        return <ShieldAlert className="w-3.5 h-3.5 text-red-400 shrink-0" aria-hidden="true" />;
      case 'high':
        return <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" aria-hidden="true" />;
      case 'medium':
        return <AlertCircle className="w-3.5 h-3.5 text-yellow-400 shrink-0" aria-hidden="true" />;
      case 'low':
      default:
        return <Info className="w-3.5 h-3.5 text-slate-400 shrink-0" aria-hidden="true" />;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelect(hotspot.id);
    }
  };

  return (
    <div
      id={`incident-card-${hotspot.id}`}
      role="button"
      tabIndex={0}
      aria-pressed={isSelected}
      aria-label={`Incident ${hotspot.id}, ${hotspot.risk_level} severity, ${sourceMeta.label}, risk score ${Math.round(hotspot.risk_score)}, status ${statusMeta.label}`}
      onClick={() => onSelect(hotspot.id)}
      onKeyDown={handleKeyDown}
      className={`p-3 rounded border transition-all cursor-pointer relative overflow-hidden group select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-cyan cyber-chamfer-xs ${
        isSelected
          ? 'bg-elevated border-cyber-cyan shadow-[0_0_12px_rgba(0,212,255,0.3)] ring-1 ring-cyber-cyan/50'
          : 'bg-surface/85 border-border-color hover:bg-surface hover:border-slate-600'
      }`}
    >
      {/* Top Header: ID, Severity Badge, and Incident Status */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center space-x-2">
          <span className="text-xs font-mono font-black text-white tracking-wide">
            {hotspot.id}
          </span>
          {/* Operational Status Pill */}
          <span
            className={`text-[9px] font-mono font-bold px-1.5 py-0.5 rounded flex items-center gap-1 cyber-chamfer-xs ${statusMeta.badgeBg}`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${statusMeta.dotColor} ${
                statusMeta.pulse ? 'motion-safe:animate-ping' : ''
              }`}
              aria-hidden="true"
            />
            {statusMeta.label}
          </span>
        </div>

        {/* Severity Badge: Uses Label + Icon + Font-Weight + Color */}
        <span
          className={`text-[10px] font-mono font-extrabold uppercase px-2 py-0.5 rounded flex items-center gap-1.5 tracking-wider cyber-chamfer-xs ${meta.badgeBg}`}
        >
          {getSeverityIcon()}
          <span>{meta.label}</span>
          <span className="opacity-80">({Math.round(hotspot.risk_score)})</span>
        </span>
      </div>

      {/* Location / Nearest Place */}
      <div className="mt-1.5 flex items-start space-x-1.5">
        <MapPin className="w-3.5 h-3.5 text-slate-400 mt-0.5 shrink-0" aria-hidden="true" />
        <div className="text-xs font-semibold text-slate-200 line-clamp-1 font-sans">
          {hotspot.nearest_place || 'Unclassified Geographic Coordinates'}
        </div>
      </div>

      {/* Important Change Indicator */}
      <div className="mt-1.5 flex items-center space-x-1.5">
        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold bg-void text-slate-300 border border-border-color flex items-center gap-1 cyber-chamfer-xs">
          <TrendingUp className="w-3 h-3 text-cyber-cyan shrink-0" aria-hidden="true" />
          <span className="truncate max-w-[240px]">{changeIndicator.label}</span>
        </span>
        {hotspot.is_anomaly && (
          <span className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-rose-950 text-rose-300 border border-rose-800 cyber-chamfer-xs">
            ANOMALY
          </span>
        )}
      </div>

      {/* Source Classification Tag & FRP Metrics */}
      <div className="mt-2 pt-1.5 border-t border-border-color/80 flex items-center justify-between text-xs font-mono">
        <div className="flex items-center space-x-1.5">
          <span className="text-sm" aria-hidden="true">{sourceMeta.icon}</span>
          <span className="text-[11px] font-medium text-slate-300 capitalize font-sans">
            {sourceMeta.label}
          </span>
        </div>

        <div className="flex items-center space-x-3 text-[11px] font-mono">
          <div
            className="flex items-center space-x-1 text-cyber-cyan font-bold"
            title="Fire Radiative Power (MW)"
          >
            <Zap className="w-3 h-3 text-cyber-cyan shrink-0" aria-hidden="true" />
            <span>{formatFrp(hotspot.frp)}</span>
          </div>

          <div
            className="flex items-center space-x-1 text-slate-400 text-[10px]"
            title={`Last satellite detection: ${exactTime}`}
          >
            <Clock className="w-3 h-3 text-slate-500 shrink-0" aria-hidden="true" />
            <span>{relativeTime}</span>
          </div>
        </div>
      </div>

      {/* Selected Indicator Edge */}
      {isSelected && (
        <div className="absolute top-0 left-0 bottom-0 w-1 bg-cyber-cyan shadow-[0_0_8px_#00d4ff]" aria-hidden="true" />
      )}
    </div>
  );
};

export default IncidentCard;
