'use client';

import React from 'react';
import { SystemMode } from '../../types/system';
import { Radio, Database, Sparkles, History, HardDrive } from 'lucide-react';

interface SystemModeBadgeProps {
  mode: SystemMode;
  cacheAgeSeconds?: number;
  isStale?: boolean;
  degraded?: boolean;
  className?: string;
}

export const SystemModeBadge: React.FC<SystemModeBadgeProps> = ({
  mode,
  cacheAgeSeconds = 0,
  isStale = false,
  degraded = false,
  className = '',
}) => {
  const formatAge = (seconds: number) => {
    if (seconds < 60) return `${seconds}s ago`;
    const mins = Math.floor(seconds / 60);
    return `${mins}m ago`;
  };

  const getModeConfig = () => {
    switch (mode) {
      case 'LIVE':
        return {
          icon: <Radio className="w-3 h-3 text-emerald-400 animate-pulse" />,
          label: 'LIVE STREAM',
          tag: 'NRT VIIRS 375m',
          badgeClass: 'bg-emerald-950/70 border-emerald-500/40 text-emerald-300',
          dotClass: 'bg-emerald-400 animate-ping',
          title: 'Connected to Live NRT Satellite & Environmental Telemetry',
        };
      case 'CACHE':
        return {
          icon: <HardDrive className="w-3 h-3 text-amber-400" />,
          label: `CACHED (${formatAge(cacheAgeSeconds)})`,
          tag: isStale ? 'STALE' : 'VALID',
          badgeClass: isStale
            ? 'bg-rose-950/70 border-rose-500/40 text-rose-300'
            : 'bg-amber-950/70 border-amber-500/40 text-amber-300',
          dotClass: isStale ? 'bg-rose-400' : 'bg-amber-400',
          title: `Cached Telemetry snapshot from ${formatAge(cacheAgeSeconds)}`,
        };
      case 'DEMO':
        return {
          icon: <Database className="w-3 h-3 text-cyan-400" />,
          label: 'DEMO MODE',
          tag: 'DETERMINISTIC',
          badgeClass: 'bg-slate-900 border-cyan-500/30 text-cyan-300',
          dotClass: 'bg-cyan-400',
          title: 'Operating on Deterministic California Fire Complex Dataset',
        };
      case 'REPLAY':
        return {
          icon: <History className="w-3 h-3 text-purple-400" />,
          label: 'REPLAY STANDBY',
          tag: 'HISTORICAL',
          badgeClass: 'bg-purple-950/70 border-purple-500/40 text-purple-300',
          dotClass: 'bg-purple-400',
          title: 'Replay Simulation Mode: Virtual Time Envelope Active',
        };
      case 'SYNTHETIC':
      default:
        return {
          icon: <Sparkles className="w-3 h-3 text-indigo-400" />,
          label: 'SYNTHETIC FIXTURE',
          tag: 'VALIDATION',
          badgeClass: 'bg-indigo-950/70 border-indigo-500/40 text-indigo-300',
          dotClass: 'bg-indigo-400',
          title: 'Synthetic test fixtures generated for unit validation',
        };
    }
  };

  const config = getModeConfig();

  return (
    <div
      id="system-mode-indicator"
      className={`inline-flex items-center space-x-2 px-3 py-1 rounded-lg border font-mono text-xs shadow-sm ${config.badgeClass} ${className}`}
      title={config.title}
      role="status"
      aria-label={`System Telemetry Mode: ${config.label}`}
    >
      <div className="relative flex items-center justify-center">
        {config.icon}
        {mode === 'LIVE' && (
          <span
            className={`absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full ${config.dotClass}`}
          />
        )}
      </div>
      <span className="font-bold tracking-wider">{config.label}</span>
      <span className="text-[9px] uppercase px-1.5 py-0.2 rounded bg-black/40 border border-white/10 text-slate-300 font-semibold">
        {config.tag}
      </span>
      {degraded && (
        <span className="text-[9px] uppercase font-bold text-amber-400 bg-amber-950/80 px-1 py-0.2 rounded border border-amber-800">
          DEGRADED
        </span>
      )}
    </div>
  );
};

export default SystemModeBadge;
