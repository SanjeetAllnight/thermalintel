'use client';

import React, { useState } from 'react';
import { Layers, ChevronDown, ChevronUp, Flame, Factory, Trees, Sprout, Building, Mountain } from 'lucide-react';

export const MapLegend: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="absolute bottom-4 left-4 z-[400] bg-surface/95 backdrop-blur-md rounded p-3 shadow-2xl text-xs max-w-xs transition-all">
      <div
        className="flex items-center justify-between cursor-pointer select-none pb-1"
        onClick={() => setCollapsed(!collapsed)}
      >
        <div className="flex items-center space-x-1.5 font-bold font-mono text-slate-200 text-xs uppercase tracking-wider">
          <Layers className="w-3.5 h-3.5 text-blue-400" />
          <span>Tactical Map Legend</span>
        </div>
        <button type="button" className="text-slate-400 hover:text-white p-0.5 cursor-pointer">
          {collapsed ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>
      </div>

      {!collapsed && (
        <div className="mt-2 space-y-2.5 pt-2 border-t border-subtle">
          {/* Severity Levels with Non-Color Symbols */}
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5 font-mono">
              Severity Tiers (Symbols & Color)
            </div>
            <div className="grid grid-cols-2 gap-1.5 font-mono">
              <div className="flex items-center space-x-1.5">
                <span className="w-4 h-4 rounded-full bg-red-500 text-white font-black text-[9px] flex items-center justify-center border border-white/80 shadow-sm">
                  !
                </span>
                <span className="text-[11px] text-slate-200">Critical (75–100)</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <span className="w-4 h-4 rounded bg-amber-500 text-slate-950 font-black text-[9px] flex items-center justify-center border border-white/60 shadow-sm">
                  ▲
                </span>
                <span className="text-[11px] text-slate-200">High (50–74)</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <span className="w-4 h-4 rounded-sm bg-yellow-500 text-slate-950 font-black text-[9px] flex items-center justify-center border border-slate-900">
                  ■
                </span>
                <span className="text-[11px] text-slate-200">Medium (25–49)</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <span className="w-4 h-4 rounded-full bg-slate-600 text-white font-black text-[9px] flex items-center justify-center border border-slate-800">
                  –
                </span>
                <span className="text-[11px] text-slate-200">Low (0–24)</span>
              </div>
              <div className="flex items-center space-x-1.5 col-span-2 pt-1 border-t border-subtle/60">
                <span className="w-4 h-4 rounded-full bg-blue-400 text-slate-950 font-black text-[10px] flex items-center justify-center border-2 border-white shadow-sm">
                  ✛
                </span>
                <span className="text-[11px] text-blue-400 font-bold">Selected Target Anomaly</span>
              </div>
            </div>
          </div>

          {/* Thermal Source Classifications */}
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5 font-mono">
              Thermal Classifications
            </div>
            <div className="grid grid-cols-2 gap-1.5 text-[11px] text-slate-300 font-sans">
              <div className="flex items-center space-x-1.5">
                <Flame className="w-3 h-3 text-red-400" />
                <span>Wildfire</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <Factory className="w-3 h-3 text-blue-400" />
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
                <Mountain className="w-3 h-3 text-thermal-orange" />
                <span>Volcanic Caldera</span>
              </div>
            </div>
          </div>

          <div className="text-[10px] text-slate-500 font-mono pt-1 border-t border-subtle/60">
            Outer halo radius scales proportionally with Fire Radiative Power (MW).
          </div>
        </div>
      )}
    </div>
  );
};

export default MapLegend;
