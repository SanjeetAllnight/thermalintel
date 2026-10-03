'use client';

import React, { useState } from 'react';
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  RotateCcw,
  Clock,
  Radio,
  Sliders,
  CheckCircle2,
  AlertTriangle,
  Layers,
} from 'lucide-react';

interface ReplayControlProps {
  isActive: boolean;
  onToggleReplay: (enable: boolean) => void;
  virtualTime?: string;
  onTimeChange?: (timeIso: string) => void;
  className?: string;
}

interface TimelineMarker {
  time: string;
  label: string;
  source: string;
  phase: string;
  positionPercent: number;
}

const TIMELINE_MARKERS: TimelineMarker[] = [
  { time: '07:30 UTC', label: 'MODIS Aqua Baseline', source: 'AQUA', phase: 'Detection', positionPercent: 12 },
  { time: '08:45 UTC', label: 'Suomi-NPP VIIRS I-Band Pass', source: 'SNPP', phase: 'Observation', positionPercent: 38 },
  { time: '09:12 UTC', label: 'NOAA-20 VIIRS Cluster Pass', source: 'NOAA-20', phase: 'Enrichment', positionPercent: 62 },
  { time: '09:40 UTC', label: 'OSM Infrastructure & Weather Matrix', source: 'GEO-ENRICH', phase: 'Assessment', positionPercent: 78 },
  { time: '10:15 UTC', label: 'NOAA-21 High-FRP Alert Triangulation', source: 'NOAA-21', phase: 'Alert', positionPercent: 92 },
];

export const ReplayControl: React.FC<ReplayControlProps> = ({
  isActive,
  onToggleReplay,
  virtualTime = '2026-10-01T08:45:00Z',
  onTimeChange,
  className = '',
}) => {
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<'1x' | '5x' | '15x'>('1x');
  const [sliderVal, setSliderVal] = useState<number>(38);

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = Number(e.target.value);
    setSliderVal(val);
    if (onTimeChange) {
      // Map percentage to simulated ISO timestamp
      const baseHour = 7 + Math.floor((val / 100) * 4);
      const baseMin = Math.floor(((val % 25) / 25) * 60);
      const simulatedIso = `2026-10-01T${String(baseHour).padStart(2, '0')}:${String(baseMin).padStart(2, '0')}:00Z`;
      onTimeChange(simulatedIso);
    }
  };

  return (
    <div
      id="replay-control-bar"
      className={`cyber-chamfer-xs border transition-all duration-300 font-mono text-xs select-none backdrop-blur-md ${
        isActive
          ? 'bg-void/95 border-cyber-accent/60 shadow-[0_0_20px_rgba(0,255,136,0.15)] ring-1 ring-cyber-accent/30'
          : 'bg-surface/90 border-cyber-border hover:border-cyber-border/80'
      } ${className}`}
    >
      {/* Top Telemetry & Control Bar */}
      <div className="p-3 sm:px-4 flex flex-wrap items-center justify-between gap-3 border-b border-cyber-border/50">
        {/* Left: Mode Badge & Operational Lifecycle Indicator */}
        <div className="flex items-center space-x-3">
          <div
            className={`flex items-center justify-center w-8 h-8 rounded border transition-colors ${
              isActive
                ? 'bg-cyber-accent/10 border-cyber-accent/50 text-cyber-accent animate-pulse shadow-[0_0_8px_rgba(0,255,136,0.3)]'
                : 'bg-elevated border-cyber-border text-subtle'
            }`}
          >
            {isActive ? <Clock className="w-4 h-4" /> : <Radio className="w-4 h-4" />}
          </div>

          <div>
            <div className="flex items-center space-x-2">
              <span className="font-display font-bold text-xs tracking-wider uppercase text-foreground">
                {isActive ? 'TEMPORAL REPLAY SUITE' : 'OPERATIONAL TEMPORAL ENGINE'}
              </span>
              <span
                className={`px-1.5 py-0.5 text-[9px] font-bold rounded uppercase tracking-wider ${
                  isActive
                    ? 'bg-cyber-accent/20 text-cyber-accent border border-cyber-accent/40 shadow-[0_0_6px_rgba(0,255,136,0.2)]'
                    : 'bg-thermal-DEFAULT/20 text-thermal-bright border border-thermal-DEFAULT/40'
                }`}
              >
                {isActive ? 'REPLAY ACTIVE' : 'LIVE TELEMETRY'}
              </span>
            </div>
            <p className="text-[10px] text-subtle hidden sm:block mt-0.5">
              Deterministic pass stepping: Detection → Observation → Enrichment → Assessment → Alert
            </p>
          </div>
        </div>

        {/* Center / Right: Operational Stepper & Virtual Time Display */}
        <div className="flex items-center space-x-2 sm:space-x-3">
          {isActive && (
            <>
              {/* Stepper Buttons */}
              <div className="flex items-center space-x-1 bg-elevated/80 border border-cyber-border rounded p-0.5">
                <button
                  type="button"
                  onClick={() => setSliderVal((prev) => Math.max(0, prev - 10))}
                  className="p-1 text-subtle hover:text-foreground hover:bg-surface rounded transition-colors"
                  title="Step Backward (Previous Satellite Pass)"
                >
                  <SkipBack className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => setIsPlaying(!isPlaying)}
                  className={`p-1 rounded transition-colors ${
                    isPlaying
                      ? 'bg-cyber-accent text-void font-bold shadow-[0_0_8px_rgba(0,255,136,0.4)]'
                      : 'text-cyber-accent hover:bg-surface'
                  }`}
                  title={isPlaying ? 'Pause Playback' : 'Play Timeline'}
                >
                  {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                </button>
                <button
                  type="button"
                  onClick={() => setSliderVal((prev) => Math.min(100, prev + 10))}
                  className="p-1 text-subtle hover:text-foreground hover:bg-surface rounded transition-colors"
                  title="Step Forward (Next Satellite Pass)"
                >
                  <SkipForward className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Speed Multiplier */}
              <div className="hidden md:flex items-center space-x-0.5 bg-elevated/80 border border-cyber-border rounded p-0.5 text-[10px]">
                {(['1x', '5x', '15x'] as const).map((spd) => (
                  <button
                    key={spd}
                    type="button"
                    onClick={() => setPlaybackSpeed(spd)}
                    className={`px-1.5 py-0.5 rounded transition-all ${
                      playbackSpeed === spd
                        ? 'bg-cyber-accent/20 text-cyber-accent font-bold border border-cyber-accent/40'
                        : 'text-subtle hover:text-foreground'
                    }`}
                  >
                    {spd}
                  </button>
                ))}
              </div>

              {/* Virtual Timestamp */}
              <div className="px-2.5 py-1 rounded bg-elevated/90 border border-cyber-border text-right min-w-[130px]">
                <div className="text-[9px] text-subtle uppercase tracking-wider">Virtual Pass Time</div>
                <div className="text-xs font-bold text-cyber-cyan">{virtualTime}</div>
              </div>
            </>
          )}

          {/* Toggle Button */}
          <button
            type="button"
            id="btn-toggle-replay-mode"
            onClick={() => onToggleReplay(!isActive)}
            className={`px-3 py-1.5 rounded text-xs font-bold uppercase tracking-wider transition-all duration-200 flex items-center gap-1.5 cursor-pointer ${
              isActive
                ? 'bg-destructive/20 text-destructive border border-destructive/50 hover:bg-destructive/30 shadow-[0_0_8px_rgba(255,51,102,0.2)]'
                : 'bg-elevated hover:bg-surface text-foreground border border-cyber-border hover:border-cyber-accent/50 hover:text-cyber-accent shadow-sm'
            }`}
          >
            {isActive ? (
              <>
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Return To Live</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 text-cyber-accent" />
                <span>Activate Replay Mode</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Expanded Interactive Replay Track (Visible when replay mode is active) */}
      {isActive && (
        <div className="p-3 sm:px-4 space-y-3 bg-void/50">
          {/* Satellite Pass Markers & Event Track */}
          <div className="relative pt-2 pb-1">
            {/* Timeline Bar Background */}
            <div className="relative w-full h-2 bg-elevated rounded overflow-hidden border border-cyber-border">
              {/* Progress Highlight */}
              <div
                className="h-full bg-gradient-to-r from-thermal-DEFAULT via-cyber-cyan to-cyber-accent transition-all duration-150"
                style={{ width: `${sliderVal}%` }}
              />
            </div>

            {/* Range Input Slider (Overlay) */}
            <input
              id="replay-time-slider"
              type="range"
              min="0"
              max="100"
              value={sliderVal}
              onChange={handleSliderChange}
              className="absolute inset-x-0 top-1 w-full h-4 opacity-0 cursor-pointer z-20"
              aria-label="Historical Replay Timeline Scrubber"
            />

            {/* Satellite Pass Tick Points */}
            <div className="relative w-full h-6 mt-1.5 flex items-center justify-between text-[10px] text-subtle">
              {TIMELINE_MARKERS.map((m) => {
                const isPassed = sliderVal >= m.positionPercent;
                return (
                  <div
                    key={m.source}
                    className="flex flex-col items-center group cursor-pointer"
                    style={{ position: 'absolute', left: `${m.positionPercent}%`, transform: 'translateX(-50%)' }}
                    onClick={() => {
                      setSliderVal(m.positionPercent);
                      if (onTimeChange) {
                        onTimeChange(`2026-10-01T${m.time.split(' ')[0]}:00Z`);
                      }
                    }}
                  >
                    <div
                      className={`w-2 h-2 rounded-full border transition-all ${
                        isPassed
                          ? 'bg-cyber-accent border-cyber-accent shadow-[0_0_6px_rgba(0,255,136,0.6)] scale-110'
                          : 'bg-elevated border-subtle group-hover:border-foreground'
                      }`}
                    />
                    <span
                      className={`text-[9px] mt-1 whitespace-nowrap transition-colors ${
                        isPassed ? 'text-cyber-accent font-bold' : 'text-subtle group-hover:text-foreground'
                      }`}
                    >
                      {m.source} ({m.time.split(' ')[0]})
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Operational Pipeline State Ribbon */}
          <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-cyber-border/40 text-[10px]">
            <div className="flex items-center space-x-2">
              <span className="text-subtle font-semibold">PIPELINE STAGE:</span>
              <div className="flex items-center space-x-1.5">
                {['Detection', 'Observation', 'Enrichment', 'Assessment', 'Alert'].map((stg, i) => {
                  const stageThreshold = (i + 1) * 20;
                  const isCurrent = sliderVal >= stageThreshold - 20 && sliderVal <= stageThreshold;
                  const isDone = sliderVal > stageThreshold;
                  return (
                    <React.Fragment key={stg}>
                      <span
                        className={`px-1.5 py-0.5 rounded text-[9px] uppercase tracking-wider font-bold transition-colors ${
                          isCurrent
                            ? 'bg-cyber-accent/20 text-cyber-accent border border-cyber-accent/60 shadow-[0_0_6px_rgba(0,255,136,0.3)]'
                            : isDone
                            ? 'bg-elevated text-foreground border border-cyber-border'
                            : 'text-subtle/60'
                        }`}
                      >
                        {stg}
                      </span>
                      {i < 4 && <span className="text-subtle/40">→</span>}
                    </React.Fragment>
                  );
                })}
              </div>
            </div>

            <div className="flex items-center space-x-1.5 text-cyber-cyan text-[10px]">
              <span className="w-1.5 h-1.5 rounded-full bg-cyber-cyan animate-pulse" />
              <span>DETERMINISTIC SIMULATION SYNCED</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ReplayControl;
