'use client';

import React from 'react';
import {
  Flame,
  LayoutGrid,
  Bell,
  Activity,
  BarChart3,
  Layers,
  Settings,
  Clock,
  Radio,
  SlidersHorizontal,
} from 'lucide-react';

export type NavView =
  | 'command'
  | 'incidents'
  | 'alerts'
  | 'sources'
  | 'analytics'
  | 'layers'
  | 'settings';

interface NavRailProps {
  activeView: NavView;
  onViewChange: (view: NavView) => void;
  incidentCount?: number;
  alertCount?: number;
  criticalCount?: number;
  isReplayActive?: boolean;
  onToggleReplay?: () => void;
}

export const NavRail: React.FC<NavRailProps> = ({
  activeView,
  onViewChange,
  incidentCount = 0,
  alertCount = 0,
  criticalCount = 0,
  isReplayActive = false,
  onToggleReplay,
}) => {
  const navItems = [
    {
      id: 'command' as NavView,
      label: 'Command Center',
      short: 'Map',
      icon: LayoutGrid,
      badge: null,
    },
    {
      id: 'incidents' as NavView,
      label: 'Incident Queue',
      short: 'Queue',
      icon: Flame,
      badge: incidentCount > 0 ? incidentCount : null,
      badgeColor: criticalCount > 0 ? 'bg-red-500 text-white' : 'bg-slate-800 text-slate-300',
    },
    {
      id: 'alerts' as NavView,
      label: 'Threat Advisories',
      short: 'Alerts',
      icon: Bell,
      badge: alertCount > 0 ? alertCount : null,
      badgeColor: 'bg-rose-500 text-white motion-safe:animate-pulse',
    },
    {
      id: 'sources' as NavView,
      label: 'Telemetry Sources',
      short: 'Sources',
      icon: Activity,
      badge: null,
    },
    {
      id: 'analytics' as NavView,
      label: 'Risk Analytics',
      short: 'Analytics',
      icon: BarChart3,
      badge: null,
    },
    {
      id: 'layers' as NavView,
      label: 'GIS Layers',
      short: 'Layers',
      icon: Layers,
      badge: null,
    },
    {
      id: 'settings' as NavView,
      label: 'Operational Config',
      short: 'Config',
      icon: Settings,
      badge: null,
    },
  ];

  return (
    <nav
      id="operational-nav-rail"
      role="navigation"
      aria-label="Command Center Rail"
      className="w-14 sm:w-16 shrink-0 bg-void/95 border-r border-subtle flex flex-col items-center py-3 z-30 select-none shadow-2xl relative"
    >
      {/* Brand Icon Mark */}
      <div className="mb-4 relative group cursor-pointer" onClick={() => onViewChange('command')}>
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-thermal-orange via-thermal-flame to-red-600 flex items-center justify-center shadow-lg shadow-thermal-orange/30 border border-orange-400/40 transition-transform group-hover:scale-105">
          <Flame className="w-5 h-5 text-white" aria-hidden="true" />
        </div>
        <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-400 border-2 border-void motion-safe:animate-ping" />
      </div>

      {/* Primary Rail Items */}
      <div className="flex-1 w-full flex flex-col items-center space-y-1.5 px-1.5">
        {navItems.map((item) => {
          const isActive = activeView === item.id;
          const IconComponent = item.icon;

          return (
            <button
              key={item.id}
              id={`nav-item-${item.id}`}
              type="button"
              onClick={() => onViewChange(item.id)}
              aria-label={item.label}
              aria-current={isActive ? 'page' : undefined}
              className={`w-full py-2.5 px-1 rounded-lg flex flex-col items-center justify-center transition-all relative group cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 ${ isActive ? 'bg-elevated text-blue-400 shadow-sm border border-blue-400/40 ' : 'text-slate-400 hover:text-slate-200 hover:bg-surface/80 border border-transparent' }`}
            >
              {/* Active Indicator Bar on Left */}
              {isActive && (
                <div
                  className="absolute left-0 top-1 bottom-1 w-0.5 bg-blue-400 shadow-[0_0_8px_#00d4ff]"
                  aria-hidden="true"
                />
              )}

              <div className="relative">
                <IconComponent
                  className={`w-5 h-5 transition-transform group-hover:scale-110 ${ isActive ? 'text-blue-400 filter drop-shadow-[0_0_4px_#00d4ff]' : '' }`}
                  aria-hidden="true"
                />

                {item.badge !== null && (
                  <span
                    className={`absolute -top-1.5 -right-2 text-[9px] font-mono font-black px-1 rounded-full ${ item.badgeColor || 'bg-slate-800 text-slate-300' }`}
                  >
                    {item.badge}
                  </span>
                )}
              </div>

              <span className="text-[9px] font-mono tracking-tighter mt-1 hidden sm:block uppercase">
                {item.short}
              </span>

              {/* Tooltip on Hover */}
              <div
                aria-hidden="true"
                className="absolute left-full ml-2 px-2.5 py-1 rounded bg-slate-900 border border-slate-700 text-white text-xs font-mono whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50 shadow-xl"
              >
                {item.label}
              </div>
            </button>
          );
        })}
      </div>

      {/* Bottom Replay Subsystem Trigger */}
      {onToggleReplay && (
        <div className="w-full px-1.5 pt-2 border-t border-subtle/60 flex flex-col items-center space-y-2">
          <button
            type="button"
            onClick={onToggleReplay}
            id="nav-toggle-replay"
            aria-label={isReplayActive ? 'Exit Replay Mode' : 'Activate Replay Mode'}
            title={isReplayActive ? 'Replay Active (Click to Exit)' : 'Historical Replay Mode'}
            className={`w-full py-2 rounded-lg flex flex-col items-center justify-center transition-all relative group ${ isReplayActive ? 'bg-purple-950/80 text-purple-300 border border-purple-500/60 shadow-[0_0_10px_rgba(168,85,247,0.3)]' : 'text-slate-500 hover:text-slate-300 hover:bg-surface' }`}
          >
            <Clock className={`w-4 h-4 ${isReplayActive ? 'text-purple-400' : ''}`} />
            <span className="text-[8px] font-mono mt-0.5 uppercase">
              {isReplayActive ? 'Replay' : 'Time'}
            </span>

            <div
              aria-hidden="true"
              className="absolute left-full ml-2 px-2.5 py-1 rounded bg-slate-900 border border-slate-700 text-white text-xs font-mono whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50 shadow-xl"
            >
              {isReplayActive ? 'Exit Historical Replay' : 'Enter Historical Replay Mode'}
            </div>
          </button>

          {/* Telemetry Heartbeat Indicator */}
          <div
            className="flex items-center space-x-1 text-[8px] font-mono text-slate-500"
            title="Telemetry Stream: Active"
          >
            <Radio className="w-3 h-3 text-emerald-400 animate-pulse" />
          </div>
        </div>
      )}
    </nav>
  );
};

export default NavRail;
