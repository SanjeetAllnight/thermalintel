'use client';

import React from 'react';
import { SummaryResponse } from '../../types/api';
import { Flame, AlertTriangle, ShieldAlert, Zap, Bell } from 'lucide-react';

interface KpiStripProps {
  summary: SummaryResponse | null;
  activeFilterCount?: number;
  totalHotspotsCount?: number;
  activeAlertsCount?: number;
  loading?: boolean;
}

export const KpiStrip: React.FC<KpiStripProps> = ({
  summary,
  activeFilterCount,
  totalHotspotsCount,
  activeAlertsCount,
  loading = false,
}) => {
  const totalHotspots = totalHotspotsCount ?? summary?.total_active_hotspots ?? 0;
  const criticalCount = summary?.critical_risk_count ?? 0;
  const highCount = summary?.high_risk_count ?? 0;
  const meanFrp = summary?.average_frp ? `${summary.average_frp.toFixed(1)} MW` : '—';
  const peakFrp = summary?.max_frp ? `${summary.max_frp.toFixed(1)} MW` : '—';
  const alertsCount = activeAlertsCount ?? summary?.active_alerts_count ?? 0;

  return (
    <section id="kpi-summary-cards" className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 sm:gap-3 select-none">
      {/* 1. Total Active Anomalies */}
      <div className="p-2.5 sm:p-3 rounded bg-surface/90 border border-border-color shadow-lg flex flex-col justify-between relative overflow-hidden group hover:border-thermal-orange/60 transition-all cyber-chamfer-xs">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400">Active Hotspots</span>
          <div className="w-6 h-6 rounded bg-elevated border border-border-color flex items-center justify-center text-slate-300">
            <Flame className="w-3.5 h-3.5 text-thermal-orange" />
          </div>
        </div>
        <div className="mt-1 flex items-baseline space-x-2">
          <span className="text-xl sm:text-2xl font-black text-white font-mono tracking-tight">
            {loading ? '—' : totalHotspots}
          </span>
          {activeFilterCount !== undefined && activeFilterCount !== totalHotspots && (
            <span className="text-[10px] font-mono text-cyber-cyan">
              ({activeFilterCount} filtered)
            </span>
          )}
        </div>
        <div className="text-[10px] text-slate-500 mt-1 flex items-center justify-between font-mono">
          <span>VIIRS NRT</span>
          <span className="text-slate-400">Suomi/NOAA-20</span>
        </div>
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-thermal-orange to-transparent opacity-80" />
      </div>

      {/* 2. Critical Risk Events */}
      <div className="p-2.5 sm:p-3 rounded bg-surface/90 border border-red-900/50 shadow-lg shadow-red-950/20 flex flex-col justify-between relative overflow-hidden group hover:border-red-500/80 transition-all cyber-chamfer-xs">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-mono uppercase tracking-wider text-red-400 font-bold">Critical Priority</span>
          <div className="w-6 h-6 rounded bg-red-950/80 border border-red-800/80 flex items-center justify-center text-red-400">
            <ShieldAlert className="w-3.5 h-3.5 text-red-400" />
          </div>
        </div>
        <div className="mt-1 flex items-baseline space-x-2">
          <span className="text-xl sm:text-2xl font-black text-red-500 font-mono tracking-tight">
            {loading ? '—' : criticalCount}
          </span>
          <span className="text-[9px] font-mono font-bold uppercase px-1.5 py-0.2 rounded bg-red-500/20 text-red-400 border border-red-500/40">
            Score ≥ 75
          </span>
        </div>
        <div className="text-[10px] text-slate-500 mt-1 flex items-center justify-between font-mono">
          <span>Immediate Threat</span>
          <span className="text-red-400 font-bold">DEFENSE ALERT</span>
        </div>
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-red-600 via-red-500 to-red-600 shadow-[0_0_8px_#ef4444]" />
      </div>

      {/* 3. High Risk Events */}
      <div className="p-2.5 sm:p-3 rounded bg-surface/90 border border-amber-900/50 shadow-lg shadow-amber-950/20 flex flex-col justify-between relative overflow-hidden group hover:border-amber-500/80 transition-all cyber-chamfer-xs">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-mono uppercase tracking-wider text-amber-400 font-bold">High Risk Hotspots</span>
          <div className="w-6 h-6 rounded bg-amber-950/80 border border-amber-800/80 flex items-center justify-center text-amber-400">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
          </div>
        </div>
        <div className="mt-1 flex items-baseline space-x-2">
          <span className="text-xl sm:text-2xl font-black text-amber-400 font-mono tracking-tight">
            {loading ? '—' : highCount}
          </span>
          <span className="text-[9px] font-mono font-bold uppercase px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
            Score 50–74
          </span>
        </div>
        <div className="text-[10px] text-slate-500 mt-1 flex items-center justify-between font-mono">
          <span>Escalation Watch</span>
          <span className="text-amber-400 font-bold">SURVEILLANCE</span>
        </div>
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-amber-600 via-amber-500 to-amber-600 shadow-[0_0_8px_#f59e0b]" />
      </div>

      {/* 4. Mean Radiative Power (MW) */}
      <div className="p-2.5 sm:p-3 rounded bg-surface/90 border border-border-color shadow-lg flex flex-col justify-between relative overflow-hidden group hover:border-cyber-cyan/60 transition-all cyber-chamfer-xs">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-mono uppercase tracking-wider text-cyber-cyan font-semibold">Mean Radiative Power</span>
          <div className="w-6 h-6 rounded bg-cyan-950/80 border border-cyan-800/60 flex items-center justify-center text-cyber-cyan">
            <Zap className="w-3.5 h-3.5 text-cyber-cyan" />
          </div>
        </div>
        <div className="mt-1 flex items-baseline space-x-2">
          <span className="text-xl sm:text-2xl font-black text-cyber-cyan font-mono tracking-tight">
            {loading ? '—' : meanFrp}
          </span>
        </div>
        <div className="text-[10px] text-slate-500 mt-1 flex items-center justify-between font-mono">
          <span>Peak: <strong className="text-slate-300">{peakFrp}</strong></span>
          <span className="text-slate-400">Convective FRP</span>
        </div>
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-cyber-cyan to-transparent opacity-80" />
      </div>

      {/* 5. Active Alerts */}
      <div className="p-2.5 sm:p-3 rounded bg-surface/90 border border-rose-900/50 shadow-lg shadow-rose-950/20 col-span-2 sm:col-span-1 flex flex-col justify-between relative overflow-hidden group hover:border-rose-500/80 transition-all cyber-chamfer-xs">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-mono uppercase tracking-wider text-rose-400 font-bold">Operational Alerts</span>
          <div className="w-6 h-6 rounded bg-rose-950/80 border border-rose-800/80 flex items-center justify-center text-rose-400">
            <Bell className="w-3.5 h-3.5 text-rose-400" />
          </div>
        </div>
        <div className="mt-1 flex items-baseline space-x-2">
          <span className="text-xl sm:text-2xl font-black text-rose-400 font-mono tracking-tight">
            {loading ? '—' : alertsCount}
          </span>
          <span className="text-[9px] font-mono font-bold uppercase px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40">
            Pending Dispatch
          </span>
        </div>
        <div className="text-[10px] text-slate-500 mt-1 flex items-center justify-between font-mono">
          <span>Unacknowledged</span>
          <span className="text-rose-400 font-bold">ADVISORY</span>
        </div>
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-rose-600 via-rose-500 to-rose-600 shadow-[0_0_8px_#f43f5e]" />
      </div>
    </section>
  );
};

export default KpiStrip;
