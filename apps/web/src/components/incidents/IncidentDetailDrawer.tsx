'use client';

import React, { useEffect } from 'react';
import { IncidentDetail } from '../../types/api';
import { RiskGauge } from './RiskGauge';
import {
  getRiskLevelMeta,
  getSourceMeta,
  formatCoordinates,
  formatDistance,
  formatFrp,
  formatTemp,
  formatTimestamp,
} from '../../lib/formatters';
import {
  X,
  MapPin,
  Wind,
  Droplets,
  Thermometer,
  ShieldAlert,
  Compass,
  History,
  BrainCircuit,
  Building2,
  TreePine,
  Layers,
  ChevronRight,
  ExternalLink,
  Flame,
  CheckCircle2,
  Radio,
} from 'lucide-react';

interface IncidentDetailDrawerProps {
  incident: IncidentDetail | null;
  onClose: () => void;
  loading?: boolean;
}

export const IncidentDetailDrawer: React.FC<IncidentDetailDrawerProps> = ({
  incident,
  onClose,
  loading = false,
}) => {
  // ESC key listener to close drawer
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  if (!incident && !loading) return null;

  const hotspot = incident?.hotspot;
  const geo = incident?.geospatial;
  const weather = incident?.weather;
  const history = incident?.historical;
  const intel = incident?.intelligence;
  const meta = hotspot ? getRiskLevelMeta(hotspot.risk_level) : getRiskLevelMeta('low');
  const sourceMeta = hotspot ? getSourceMeta(hotspot.source_type) : getSourceMeta('unknown');

  return (
    <div
      id="incident-detail-drawer"
      className="fixed inset-y-0 right-0 z-50 w-full max-w-2xl bg-slate-950/98 text-slate-100 border-l border-slate-800 shadow-2xl backdrop-blur-xl flex flex-col transition-all duration-300 ease-in-out"
    >
      {/* Top Fixed Header */}
      <div className="p-4 sm:p-5 border-b border-slate-800 bg-slate-900/90 flex items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-xl bg-slate-800 border border-slate-700 text-lg">
            {sourceMeta.icon}
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-base font-black font-mono text-white tracking-wide">
                {hotspot?.id || 'Loading Dossier...'}
              </span>
              {hotspot?.is_anomaly && (
                <span className="px-1.5 py-0.2 text-[10px] font-mono font-bold bg-rose-950 text-rose-300 border border-rose-800 rounded">
                  ANOMALY
                </span>
              )}
            </div>
            <div className="text-xs text-slate-400 font-medium mt-0.5">
              {hotspot?.nearest_place || 'Analyzing Coordinates...'}
            </div>
          </div>
        </div>

        {/* Action Controls & Close */}
        <div className="flex items-center space-x-2">
          <button
            id="btn-close-drawer"
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-all cursor-pointer"
            title="Close Drawer (ESC)"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Main Drawer Scrollable Dossier Content */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
        {loading || !hotspot ? (
          <div className="p-12 text-center space-y-3 text-slate-400">
            <Radio className="w-8 h-8 mx-auto text-cyan-400 animate-spin" />
            <div className="text-sm font-semibold">Synthesizing Incident Dossier...</div>
            <p className="text-xs text-slate-500">
              Correlating OSM infrastructure, Open-Meteo weather telemetry, and AI explainable factors.
            </p>
          </div>
        ) : (
          <>
            {/* Top Risk & Recommendation Header Card */}
            <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 shadow-md flex flex-col sm:flex-row items-center justify-between gap-4">
              <div className="flex items-center space-x-4">
                <RiskGauge score={hotspot.risk_score} level={hotspot.risk_level} size={84} />
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <span
                      className={`text-xs font-bold uppercase px-2 py-0.5 rounded ${meta.badgeBg}`}
                    >
                      {hotspot.risk_level} SEVERITY
                    </span>
                    <span className="text-xs font-mono text-slate-400">
                      Score: {hotspot.risk_score.toFixed(1)}/100
                    </span>
                  </div>
                  <div className="text-xs text-slate-300">
                    Source: <strong className="capitalize text-white">{sourceMeta.label}</strong> (
                    {Math.round((intel?.classification?.confidence || 0.9) * 100)}% confidence)
                  </div>
                  <div className="text-[11px] text-slate-400 font-mono">
                    Coords: {formatCoordinates(hotspot.latitude, hotspot.longitude)}
                  </div>
                </div>
              </div>

              {/* Status Pill */}
              <div className="text-right sm:border-l sm:border-slate-800 sm:pl-4 w-full sm:w-auto flex sm:flex-col justify-between items-center sm:items-end">
                <span className="text-[11px] text-slate-400 uppercase font-mono">STATUS</span>
                <span className="text-xs font-bold font-mono text-emerald-400 flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                  EVALUATED
                </span>
                <span className="text-[10px] text-slate-500 font-mono mt-1">
                  {formatTimestamp(hotspot.last_updated)}
                </span>
              </div>
            </div>

            {/* Recommended Response Action Callout */}
            {intel?.risk?.recommended_action && (
              <div className="p-4 rounded-xl bg-gradient-to-r from-red-950/40 via-slate-900 to-slate-900 border border-red-500/40 shadow-md">
                <div className="flex items-start space-x-2.5">
                  <ShieldAlert className="w-5 h-5 text-red-400 mt-0.5 shrink-0" />
                  <div>
                    <div className="text-xs font-bold uppercase tracking-wider text-red-400 font-mono">
                      Recommended Operational Action
                    </div>
                    <p className="text-xs text-slate-200 mt-1 font-medium leading-relaxed">
                      {intel.risk.recommended_action}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* SECTION 1: Geospatial Proximity & Infrastructure */}
            <div className="space-y-3">
              <div className="flex items-center space-x-2 border-b border-slate-800 pb-2">
                <MapPin className="w-4 h-4 text-cyan-400" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200 font-mono">
                  Geospatial Proximity & Environmental Context
                </h3>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                {/* Nearest Settlement */}
                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800">
                  <div className="text-[11px] text-slate-400 font-medium">Nearest Human Settlement</div>
                  <div className="text-slate-200 font-semibold mt-1">
                    {geo?.nearest_settlement || 'None within 5km radius'}
                  </div>
                  <div className="text-[11px] text-cyan-400 font-mono mt-0.5">
                    Distance: <strong>{formatDistance(geo?.distance_to_settlement_meters)}</strong>
                  </div>
                </div>

                {/* Nearest Infrastructure */}
                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800">
                  <div className="text-[11px] text-slate-400 font-medium">Critical Infrastructure Corridor</div>
                  <div className="text-slate-200 font-semibold mt-1">
                    {geo?.nearest_infrastructure || 'No critical utility identified'}
                  </div>
                  <div className="text-[11px] text-amber-400 font-mono mt-0.5">
                    Distance: <strong>{formatDistance(geo?.distance_to_infrastructure_meters)}</strong>
                  </div>
                </div>

                {/* Land Cover & Fuel Model */}
                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800">
                  <div className="text-[11px] text-slate-400 font-medium">Land Cover / Fuel Estimate</div>
                  <div className="text-slate-200 font-semibold mt-1">
                    {geo?.land_cover || 'Mixed Vegetation'}
                  </div>
                  <div className="text-[11px] text-slate-400 mt-0.5">
                    Fuel: {geo?.fuel_load_estimate || 'Standard'}
                  </div>
                </div>

                {/* Terrain / Protected Area */}
                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800">
                  <div className="text-[11px] text-slate-400 font-medium">Terrain Topography</div>
                  <div className="text-slate-200 font-semibold mt-1">
                    Elevation: {geo?.elevation_meters ?? 0}m • Slope: {geo?.slope_degrees ?? 0}°
                  </div>
                  <div className="text-[11px] text-emerald-400 mt-0.5">
                    {geo?.is_protected_area
                      ? `Protected: ${geo.protected_area_name || 'Designated Park'}`
                      : 'Unprotected Parcel'}
                  </div>
                </div>
              </div>
            </div>

            {/* SECTION 2: Hyperlocal Fire Weather Telemetry */}
            <div className="space-y-3">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <div className="flex items-center space-x-2">
                  <Wind className="w-4 h-4 text-cyan-400" />
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200 font-mono">
                    Hyperlocal Fire Weather Dials
                  </h3>
                </div>
                {weather?.fire_weather_index != null && (
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-red-950 text-red-300 border border-red-800">
                    FWI: {weather.fire_weather_index.toFixed(1)}
                  </span>
                )}
              </div>

              {/* Weather Telemetry Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                {/* Temp */}
                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 text-center">
                  <Thermometer className="w-4 h-4 text-orange-400 mx-auto mb-1" />
                  <div className="text-base font-bold font-mono text-white">
                    {formatTemp(weather?.temperature_celsius)}
                  </div>
                  <div className="text-[10px] text-slate-400 uppercase">Temperature</div>
                </div>

                {/* Humidity */}
                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 text-center">
                  <Droplets className="w-4 h-4 text-cyan-400 mx-auto mb-1" />
                  <div className="text-base font-bold font-mono text-white">
                    {weather?.relative_humidity_percent ?? 0}%
                  </div>
                  <div className="text-[10px] text-slate-400 uppercase">Rel. Humidity</div>
                </div>

                {/* Wind Speed & Direction with Compass Arrow */}
                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 text-center relative overflow-hidden">
                  <div className="flex items-center justify-center space-x-1 text-teal-400 mb-1">
                    <Compass
                      className="w-4 h-4 transition-transform duration-500"
                      style={{
                        transform: `rotate(${weather?.wind_direction_degrees ?? 0}deg)`,
                      }}
                    />
                    <span className="text-xs font-bold">{weather?.wind_direction_cardinal || 'N'}</span>
                  </div>
                  <div className="text-base font-bold font-mono text-white">
                    {weather?.wind_speed_kmh ?? 0} <span className="text-xs font-normal">km/h</span>
                  </div>
                  <div className="text-[10px] text-slate-400 uppercase">
                    Gust: {weather?.wind_gust_kmh ?? weather?.wind_speed_kmh ?? 0} km/h
                  </div>
                </div>

                {/* Precipitation */}
                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 text-center">
                  <Droplets className="w-4 h-4 text-blue-400 mx-auto mb-1" />
                  <div className="text-base font-bold font-mono text-white">
                    {weather?.precipitation_mm ?? 0} <span className="text-xs font-normal">mm</span>
                  </div>
                  <div className="text-[10px] text-slate-400 uppercase">Precipitation</div>
                </div>
              </div>

              {/* Weather Forecast Summary */}
              {weather?.forecast_summary && (
                <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800/80 text-[11px] text-slate-300 italic flex items-center space-x-2">
                  <span className="text-amber-400 font-bold not-italic">Forecast:</span>
                  <span>{weather.forecast_summary}</span>
                </div>
              )}
            </div>

            {/* SECTION 3: Satellite Telemetry */}
            <div className="space-y-3">
              <div className="flex items-center space-x-2 border-b border-slate-800 pb-2">
                <Radio className="w-4 h-4 text-cyan-400" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200 font-mono">
                  Satellite Radiance Telemetry (VIIRS 375m)
                </h3>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
                <div className="p-2.5 rounded bg-slate-900 border border-slate-800">
                  <div className="text-[10px] text-slate-500">FIRE POWER (FRP)</div>
                  <div className="text-sm font-bold text-cyan-400 mt-0.5">{formatFrp(hotspot.frp)}</div>
                </div>
                <div className="p-2.5 rounded bg-slate-900 border border-slate-800">
                  <div className="text-[10px] text-slate-500">BRIGHTNESS (I-4)</div>
                  <div className="text-sm font-bold text-slate-200 mt-0.5">{hotspot.brightness} K</div>
                </div>
                <div className="p-2.5 rounded bg-slate-900 border border-slate-800">
                  <div className="text-[10px] text-slate-500">SATELLITE / PASS</div>
                  <div className="text-xs font-bold text-slate-200 mt-0.5">
                    {hotspot.satellite} ({hotspot.daynight === 'D' ? 'Day' : 'Night'})
                  </div>
                </div>
                <div className="p-2.5 rounded bg-slate-900 border border-slate-800">
                  <div className="text-[10px] text-slate-500">CONFIDENCE</div>
                  <div className="text-xs font-bold text-emerald-400 capitalize mt-0.5">
                    {hotspot.confidence}
                  </div>
                </div>
              </div>
            </div>

            {/* SECTION 4: Explainable AI Factors (WHY FLAGGED) */}
            <div className="space-y-3">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <div className="flex items-center space-x-2">
                  <BrainCircuit className="w-4 h-4 text-red-500" />
                  <h3 className="text-xs font-bold uppercase tracking-wider text-white font-mono">
                    WHY THIS EVENT WAS FLAGGED (EXPLAINABLE AI)
                  </h3>
                </div>
                <span className="text-[10px] font-mono text-slate-500">
                  Model: {intel?.model_version || 'v1.0-rf-heuristic'}
                </span>
              </div>

              {/* Anomaly Rationale Box */}
              {intel?.anomaly && (
                <div className="p-3 rounded-lg bg-slate-900/90 border border-slate-800 text-xs space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-300">Statistical Anomaly Engine</span>
                    <span className="font-mono text-cyan-400">
                      Deviation: {intel.anomaly.baseline_deviation}σ
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 leading-relaxed">
                    {intel.anomaly.anomaly_rationale}
                  </p>
                </div>
              )}

              {/* Explainable Factor Bars */}
              <div className="space-y-2.5">
                {(intel?.risk?.explainable_factors || []).map((factor, idx) => {
                  const factorMeta = getRiskLevelMeta(factor.impact);
                  const weightPct = Math.round(factor.weight * 100);

                  return (
                    <div
                      key={idx}
                      className="p-3 rounded-lg bg-slate-900 border border-slate-800/90 space-y-1.5"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-white">{factor.factor}</span>
                        <div className="flex items-center space-x-2">
                          <span
                            className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded ${factorMeta.badgeBg}`}
                          >
                            {factor.impact}
                          </span>
                          <span className="text-[11px] font-mono text-slate-400">
                            {weightPct}% weight
                          </span>
                        </div>
                      </div>

                      {/* Weight Progress Bar */}
                      <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-700"
                          style={{
                            width: `${weightPct}%`,
                            backgroundColor: factorMeta.fillHex,
                          }}
                        />
                      </div>

                      <p className="text-[11px] text-slate-400 leading-relaxed">
                        {factor.description}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* SECTION 5: Historical Recurrence & Satellite Pass Timeline */}
            <div className="space-y-3">
              <div className="flex items-center space-x-2 border-b border-slate-800 pb-2">
                <History className="w-4 h-4 text-cyan-400" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200 font-mono">
                  Site History & Pass Timeline
                </h3>
              </div>

              {/* Recurrence Stats */}
              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                <div className="p-2.5 rounded bg-slate-900 border border-slate-800">
                  <div className="text-slate-400 text-[10px]">30-Day Detections</div>
                  <div className="text-base font-bold font-mono text-white mt-0.5">
                    {history?.prior_detections_30d ?? 0}
                  </div>
                </div>
                <div className="p-2.5 rounded bg-slate-900 border border-slate-800">
                  <div className="text-slate-400 text-[10px]">90-Day Persistence</div>
                  <div className="text-base font-bold font-mono text-white mt-0.5">
                    {history?.prior_detections_90d ?? 0}
                  </div>
                </div>
                <div className="p-2.5 rounded bg-slate-900 border border-slate-800">
                  <div className="text-slate-400 text-[10px]">Recurrent Site</div>
                  <div
                    className={`text-base font-bold font-mono mt-0.5 ${
                      history?.is_recurrent_site ? 'text-amber-400' : 'text-slate-300'
                    }`}
                  >
                    {history?.is_recurrent_site ? 'YES' : 'NO'}
                  </div>
                </div>
              </div>

              {/* Timeline Items */}
              <div className="space-y-2 pt-1">
                {(incident.timeline || []).map((t, idx) => (
                  <div
                    key={idx}
                    className="flex items-start space-x-3 text-xs p-2.5 rounded bg-slate-900/60 border border-slate-800/80"
                  >
                    <div className="w-2 h-2 rounded-full bg-cyan-400 mt-1 shrink-0" />
                    <div className="flex-1 space-y-0.5">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-slate-200">{t.summary}</span>
                        <span className="text-[10px] font-mono text-slate-500">
                          {formatTimestamp(t.timestamp)}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default IncidentDetailDrawer;
