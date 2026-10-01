'use client';

import React, { useState } from 'react';
import { Layers, ChevronDown, ChevronUp, Flame, Factory, Trees, Sprout, Building, Mountain } from 'lucide-react';

export const MapLegend: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="absolute bottom-4 left-4 z-[400] bg-slate-950/90 backdrop-blur-md border border-slate-800 rounded-xl p-3 shadow-2xl text-xs max-w-xs transition-all">
      <div
        className="flex items-center justify-between cursor-pointer select-none pb-1"
        onClick={() => setCollapsed(!collapsed)}
      >
        <div className="flex items-center space-x-1.5 font-semibold text-slate-200">
          <Layers className="w-3.5 h-3.5 text-cyan-400" />
          <span>Tactical Map Legend</span>
        </div>
        <button type="button" className="text-slate-400 hover:text-white p-0.5">
          {collapsed ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>
      </div>

      {!collapsed && (
        <div className="mt-2.5 space-y-3 pt-2 border-t border-slate-800/80">
          {/* Severity Levels */}
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">
              Risk Severity Tiers
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              <div className="flex items-center space-x-2">
                <span className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500 shadow-sm shadow-red-500/50" />
                </span>
                <span className="text-[11px] text-slate-300 font-medium">Critical (75–100)</span>
              </div>
              <div className="flex items-center space-x-2">
                <span className="inline-flex rounded-full h-3 w-3 bg-amber-500 shadow-sm shadow-amber-500/50" />
                <span className="text-[11px] text-slate-300 font-medium">High (50–74)</span>
              </div>
              <div className="flex items-center space-x-2">
                <span className="inline-flex rounded-full h-3 w-3 bg-yellow-500" />
                <span className="text-[11px] text-slate-300 font-medium">Medium (25–49)</span>
              </div>
              <div className="flex items-center space-x-2">
                <span className="inline-flex rounded-full h-3 w-3 bg-slate-500" />
                <span className="text-[11px] text-slate-300 font-medium">Low (0–24)</span>
              </div>
            </div>
          </div>

          {/* Thermal Source Classifications */}
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">
              Thermal Classifications
            </div>
            <div className="grid grid-cols-2 gap-1.5 text-[11px] text-slate-300">
              <div className="flex items-center space-x-1.5">
                <Flame className="w-3 h-3 text-red-400" />
                <span>Wildfire</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <Factory className="w-3 h-3 text-cyan-400" />
                <span>Industrial Flare</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <Sprout className="w-3 h-3 text-emerald-400" />
                <span>Agricultural</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <Trees className="w-3 h-3 text-blue-400" />
                <span>Prescribed Burn</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <Building className="w-3 h-3 text-purple-400" />
                <span>Urban Anomaly</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <Mountain className="w-3 h-3 text-orange-400" />
                <span>Volcanic Caldera</span>
              </div>
            </div>
          </div>

          <div className="text-[10px] text-slate-500 italic pt-1 border-t border-slate-800/60">
            Outer halo radius scales proportionally with Fire Radiative Power (MW).
          </div>
        </div>
      )}
    </div>
  );
};

export default MapLegend;
