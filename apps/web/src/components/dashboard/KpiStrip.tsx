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
    <section id="kpi-summary-cards" className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
      {/* 1. Total Active Anomalies */}
      <div className="p-3.5 sm:p-4 rounded-xl bg-slate-900/90 border border-slate-800/80 shadow-md shadow-black/20 flex flex-col justify-between relative overflow-hidden group hover:border-slate-700/80 transition-all">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-slate-400">Active Hotspots</span>
          <div className="w-7 h-7 rounded-lg bg-slate-800/80 border border-slate-700/60 flex items-center justify-center text-slate-300">
            <Flame className="w-3.5 h-3.5 text-orange-400" />
          </div>
        </div>
        <div className="mt-2 flex items-baseline space-x-2">
          <span className="text-2xl sm:text-3xl font-black text-white font-mono tracking-tight">
            {loading ? '—' : totalHotspots}
          </span>
          {activeFilterCount !== undefined && activeFilterCount !== totalHotspots && (
            <span className="text-[11px] font-mono text-cyan-400">
              ({activeFilterCount} filtered)
            </span>
          )}
        </div>
        <div className="text-[11px] text-slate-500 mt-1 flex items-center justify-between">
          <span>VIIRS NRT Pixels</span>
          <span className="font-mono text-slate-400">Suomi/NOAA-20</span>
        </div>
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-orange-500/0 via-orange-500/40 to-orange-500/0" />
      </div>

      {/* 2. Critical Risk Events */}
      <div className="p-3.5 sm:p-4 rounded-xl bg-slate-900/90 border border-red-900/40 shadow-md shadow-red-950/20 flex flex-col justify-between relative overflow-hidden group hover:border-red-700/60 transition-all">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-red-400">Critical Priority</span>
          <div className="w-7 h-7 rounded-lg bg-red-950/80 border border-red-800/60 flex items-center justify-center text-red-400">
            <ShieldAlert className="w-3.5 h-3.5 text-red-500" />
          </div>
        </div>
        <div className="mt-2 flex items-baseline space-x-2">
          <span className="text-2xl sm:text-3xl font-black text-red-500 font-mono tracking-tight">
            {loading ? '—' : criticalCount}
          </span>
          <span className="text-[10px] font-bold uppercase px-1.5 py-0.2 rounded bg-red-500/20 text-red-400 border border-red-500/30">
            Score ≥ 75
          </span>
        </div>
        <div className="text-[11px] text-slate-500 mt-1 flex items-center justify-between">
          <span>Immediate Threat</span>
          <span className="text-red-400/80 font-mono">Defense Alert</span>
        </div>
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-red-600 via-red-500 to-red-600" />
      </div>

      {/* 3. High Risk Events */}
      <div className="p-3.5 sm:p-4 rounded-xl bg-slate-900/90 border border-amber-900/40 shadow-md shadow-amber-950/20 flex flex-col justify-between relative overflow-hidden group hover:border-amber-700/60 transition-all">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-amber-400">High Risk Hotspots</span>
          <div className="w-7 h-7 rounded-lg bg-amber-950/80 border border-amber-800/60 flex items-center justify-center text-amber-400">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
          </div>
        </div>
        <div className="mt-2 flex items-baseline space-x-2">
          <span className="text-2xl sm:text-3xl font-black text-amber-400 font-mono tracking-tight">
            {loading ? '—' : highCount}
          </span>
          <span className="text-[10px] font-bold uppercase px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-400 border border-amber-500/30">
            Score 50–74
          </span>
        </div>
        <div className="text-[11px] text-slate-500 mt-1 flex items-center justify-between">
          <span>Escalation Watch</span>
          <span className="text-amber-400/80 font-mono">Surveillance</span>
        </div>
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-amber-600 via-amber-500 to-amber-600" />
      </div>

      {/* 4. Mean Radiative Power (MW) */}
      <div className="p-3.5 sm:p-4 rounded-xl bg-slate-900/90 border border-slate-800/80 shadow-md shadow-black/20 flex flex-col justify-between relative overflow-hidden group hover:border-slate-700/80 transition-all">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-cyan-400">Mean Radiative Power</span>
          <div className="w-7 h-7 rounded-lg bg-cyan-950/80 border border-cyan-800/60 flex items-center justify-center text-cyan-400">
            <Zap className="w-3.5 h-3.5 text-cyan-400" />
          </div>
        </div>
        <div className="mt-2 flex items-baseline space-x-2">
          <span className="text-2xl sm:text-3xl font-black text-cyan-400 font-mono tracking-tight">
            {loading ? '—' : meanFrp}
          </span>
        </div>
        <div className="text-[11px] text-slate-500 mt-1 flex items-center justify-between">
          <span>Peak: <strong className="text-slate-300 font-mono">{peakFrp}</strong></span>
          <span className="text-slate-400 font-mono">Convective FRP</span>
        </div>
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-cyan-500/0 via-cyan-500/40 to-cyan-500/0" />
      </div>

      {/* 5. Active Alerts */}
      <div className="p-3.5 sm:p-4 rounded-xl bg-slate-900/90 border border-rose-900/40 shadow-md shadow-rose-950/20 col-span-2 md:col-span-1 flex flex-col justify-between relative overflow-hidden group hover:border-rose-700/60 transition-all">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-rose-400">Operational Alerts</span>
          <div className="w-7 h-7 rounded-lg bg-rose-950/80 border border-rose-800/60 flex items-center justify-center text-rose-400">
            <Bell className="w-3.5 h-3.5 text-rose-400" />
          </div>
        </div>
        <div className="mt-2 flex items-baseline space-x-2">
          <span className="text-2xl sm:text-3xl font-black text-rose-400 font-mono tracking-tight">
            {loading ? '—' : alertsCount}
          </span>
          <span className="text-[10px] font-bold uppercase px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30">
            Pending Dispatch
          </span>
        </div>
        <div className="text-[11px] text-slate-500 mt-1 flex items-center justify-between">
          <span>Unacknowledged</span>
          <span className="text-rose-400/80 font-mono">Incident Advisory</span>
        </div>
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-rose-600 via-rose-500 to-rose-600" />
      </div>
    </section>
  );
};

export default KpiStrip;
