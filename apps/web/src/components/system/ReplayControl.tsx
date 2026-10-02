'use client';

import React from 'react';
import { Play, Pause, RotateCcw, Clock, AlertCircle } from 'lucide-react';

interface ReplayControlProps {
  isActive: boolean;
  onToggleReplay: (enable: boolean) => void;
  virtualTime?: string;
  onTimeChange?: (timeIso: string) => void;
  className?: string;
}

export const ReplayControl: React.FC<ReplayControlProps> = ({
  isActive,
  onToggleReplay,
  virtualTime = '2026-10-01T08:45:00Z',
  onTimeChange,
  className = '',
}) => {
  return (
    <div
      id="replay-control-bar"
      className={`p-3 rounded-xl border font-mono text-xs transition-all ${
        isActive
          ? 'bg-purple-950/40 border-purple-500/50 shadow-lg shadow-purple-950/30'
          : 'bg-slate-900/80 border-slate-800'
      } ${className}`}
    >
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        {/* Status & Label */}
        <div className="flex items-center space-x-2.5">
          <div
            className={`p-1.5 rounded-lg border ${
              isActive
                ? 'bg-purple-900/60 border-purple-500/60 text-purple-300'
                : 'bg-slate-800 border-slate-700 text-slate-400'
            }`}
          >
            <Clock className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-bold text-white tracking-wide">
                HISTORICAL REPLAY
              </span>
              <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                AGENT G STANDBY
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Virtual time simulation engine interface (backend integration pending)
            </p>
          </div>
        </div>

        {/* Action Button & Slider */}
        <div className="flex items-center space-x-3 w-full sm:w-auto justify-between sm:justify-end">
          <div className="text-right hidden md:block">
            <span className="text-[10px] text-slate-500 block">Virtual Simulation Time</span>
            <span className="text-xs text-purple-300 font-bold">{virtualTime}</span>
          </div>

          <button
            type="button"
            id="btn-toggle-replay-mode"
            onClick={() => onToggleReplay(!isActive)}
            className={`px-3 py-1.5 rounded-lg border text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
              isActive
                ? 'bg-purple-600 hover:bg-purple-500 text-white border-purple-400 shadow-md'
                : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700 hover:text-white'
            }`}
          >
            {isActive ? (
              <>
                <Pause className="w-3.5 h-3.5" />
                <span>Exit Replay</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 text-purple-400" />
                <span>Activate Replay Mode</span>
              </>
            )}
          </button>
        </div>
      </div>

      {isActive && (
        <div className="mt-3 pt-3 border-t border-purple-800/40 space-y-2">
          <div className="flex items-center justify-between text-[11px] text-purple-300">
            <span>Pass: Suomi-NPP (08:45 UTC)</span>
            <span>Pass: NOAA-20 (09:12 UTC)</span>
            <span>Pass: VIIRS NRT (10:15 UTC)</span>
          </div>

          <input
            id="replay-time-slider"
            type="range"
            min="0"
            max="100"
            defaultValue="35"
            disabled
            className="w-full h-1.5 bg-purple-950 rounded-lg appearance-none cursor-not-allowed opacity-70"
            title="Replay timeline scrubber will be activated once Agent G's replay backend is connected."
          />

          <div className="flex items-center space-x-1.5 text-[10px] text-amber-300/80 bg-amber-950/30 p-1.5 rounded border border-amber-800/40">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            <span>
              Replay controls connected to local simulated fixtures. Live backend time-travel will synchronize once Agent G completes Phase 5 replay service.
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export default ReplayControl;
