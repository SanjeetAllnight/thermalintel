'use client';

import React, { useState } from 'react';
import { Alert } from '../../types/api';
import { getAlertSeverityMeta, formatTimestamp } from '../../lib/formatters';
import { Bell, ShieldAlert, CheckCircle2, MapPin, ArrowRight, Tag } from 'lucide-react';

interface AlertsFeedProps {
  alerts: Alert[];
  onSelectIncident: (hotspotId: string) => void;
}

export const AlertsFeed: React.FC<AlertsFeedProps> = ({
  alerts,
  onSelectIncident,
}) => {
  const [acknowledgedMap, setAcknowledgedMap] = useState<Record<string, boolean>>({});

  const toggleAcknowledge = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setAcknowledgedMap((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  return (
    <div className="space-y-3">
      {alerts.length === 0 ? (
        <div className="p-8 text-center bg-slate-900/60 rounded-xl border border-slate-800 text-slate-500 text-xs">
          <Bell className="w-6 h-6 mx-auto mb-2 text-slate-600" />
          No operational alerts currently dispatched.
        </div>
      ) : (
        alerts.map((alert) => {
          const isAck = acknowledgedMap[alert.id] ?? alert.is_acknowledged;
          const meta = getAlertSeverityMeta(alert.severity);

          return (
            <div
              key={alert.id}
              className={`p-4 rounded-xl border transition-all ${ isAck ? 'bg-slate-900/40 border-slate-800 opacity-60' : 'bg-slate-900 border-slate-800 shadow-md hover:border-slate-700' } ${meta.borderLeft} border-l-4`}
            >
              {/* Alert Header */}
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <span
                      className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${meta.badgeBg}`}
                    >
                      {alert.severity}
                    </span>
                    <span className="text-xs font-mono font-bold text-slate-300">
                      {alert.id}
                    </span>
                    <span className="text-[11px] font-mono text-slate-500">
                      • {formatTimestamp(alert.timestamp)}
                    </span>
                  </div>
                  <h4 className="text-sm font-bold text-white leading-snug">
                    {alert.title}
                  </h4>
                </div>

                {/* Acknowledge Toggle */}
                <button
                  type="button"
                  onClick={(e) => toggleAcknowledge(alert.id, e)}
                  className={`text-[11px] font-medium px-2.5 py-1 rounded-md border flex items-center gap-1 transition-all ${ isAck ? 'bg-emerald-950 text-emerald-400 border-emerald-800' : 'bg-slate-800 text-slate-300 border-slate-700 hover:text-white' }`}
                  title="Acknowledge Alert"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>{isAck ? 'Acknowledged' : 'Acknowledge'}</span>
                </button>
              </div>

              {/* Message */}
              <p className="text-xs text-slate-300 mt-2 leading-relaxed">
                {alert.message}
              </p>

              {/* Recommended Action */}
              {alert.recommended_action && (
                <div className="mt-2.5 p-2.5 rounded-lg bg-red-950/30 border border-red-900/40 text-xs text-red-300 flex items-start space-x-2">
                  <ShieldAlert className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
                  <div>
                    <strong className="uppercase text-[10px] font-mono tracking-wider text-red-400 block">
                      Dispatched Mitigation Order:
                    </strong>
                    <span className="text-slate-200 mt-0.5 block font-medium">
                      {alert.recommended_action}
                    </span>
                  </div>
                </div>
              )}

              {/* Location & Tags Footer */}
              <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex items-center space-x-1.5 text-slate-400">
                  <MapPin className="w-3.5 h-3.5 text-slate-500" />
                  <span className="text-slate-300 font-medium">{alert.location_name}</span>
                </div>

                <div className="flex items-center space-x-2">
                  {/* Tags */}
                  <div className="hidden sm:flex items-center space-x-1 text-[10px]">
                    {(alert.tags || []).slice(0, 3).map((tag, idx) => (
                      <span
                        key={idx}
                        className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 font-mono"
                      >
                        #{tag}
                      </span>
                    ))}
                  </div>

                  {/* Jump to Hotspot */}
                  <button
                    type="button"
                    onClick={() => onSelectIncident(alert.hotspot_id)}
                    className="flex items-center space-x-1 text-xs font-bold text-red-400 hover:text-red-300 transition-colors"
                  >
                    <span>View Hotspot ({alert.hotspot_id.split('-').pop()})</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          );
        })
      )}
    </div>
  );
};

export default AlertsFeed;
