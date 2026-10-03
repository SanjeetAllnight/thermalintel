'use client';

import React, { useState } from 'react';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from 'recharts';
import { SummaryResponse, SourcesResponse, Hotspot } from '../../types/api';
import { BarChart3, PieChart as PieIcon, TrendingUp, Flame, Zap } from 'lucide-react';
import { getRiskLevelMeta, getSourceMeta } from '../../lib/formatters';

interface AnalyticsPanelProps {
  summary: SummaryResponse | null;
  sources: SourcesResponse | null;
  hotspots: Hotspot[];
}

export const AnalyticsPanel: React.FC<AnalyticsPanelProps> = ({
  summary,
  sources,
  hotspots,
}) => {
  const [activeTab, setActiveTab] = useState<'sources' | 'risk' | 'frp'>('sources');

  // Risk Distribution Data for Pie/Donut Chart
  const riskDistributionData = [
    {
      name: 'Critical',
      value: summary?.critical_risk_count ?? hotspots.filter((h) => h.risk_level === 'critical').length,
      color: '#ef4444',
    },
    {
      name: 'High',
      value: summary?.high_risk_count ?? hotspots.filter((h) => h.risk_level === 'high').length,
      color: '#f59e0b',
    },
    {
      name: 'Medium',
      value: summary?.medium_risk_count ?? hotspots.filter((h) => h.risk_level === 'medium').length,
      color: '#eab308',
    },
    {
      name: 'Low',
      value: summary?.low_risk_count ?? hotspots.filter((h) => h.risk_level === 'low').length,
      color: '#64748b',
    },
  ].filter((d) => d.value > 0);

  // Sources Breakdown Data for Bar Chart
  const sourcesData = (sources?.sources || [
    { source_type: 'wildfire', display_name: 'Wildfire', count: 4, average_frp: 97.9 },
    { source_type: 'industrial', display_name: 'Industrial', count: 1, average_frp: 24.3 },
    { source_type: 'agricultural', display_name: 'Agricultural', count: 1, average_frp: 31.8 },
    { source_type: 'prescribed_burn', display_name: 'Prescribed', count: 1, average_frp: 44.0 },
    { source_type: 'urban', display_name: 'Urban', count: 1, average_frp: 12.5 },
    { source_type: 'volcanic', display_name: 'Volcanic', count: 1, average_frp: 165.0 },
  ]).map((s) => ({
    name: s.display_name.split('/')[0].trim(),
    count: s.count,
    avgFrp: Math.round(s.average_frp),
    sourceType: s.source_type,
  }));

  // Top FRP Incidents Histogram Data
  const topFrpData = [...hotspots]
    .sort((a, b) => b.frp - a.frp)
    .slice(0, 6)
    .map((h) => ({
      id: h.id.split('-').slice(1).join('-'),
      frp: h.frp,
      risk: h.risk_score,
      place: h.nearest_place?.split(',')[0] || 'Unknown',
    }));

  return (
    <section
      id="analytics-charts-container"
      className="rounded-xl bg-slate-900/90 border border-slate-800 p-4 sm:p-5 shadow-lg flex flex-col space-y-4"
    >
      {/* Analytics Header with Tab Switcher */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div className="flex items-center space-x-2">
          <BarChart3 className="w-4 h-4 text-cyan-400" />
          <h2 className="text-sm font-bold uppercase tracking-wider text-white font-mono">
            Analytical Intelligence & Distributions
          </h2>
        </div>

        <div className="flex items-center space-x-1 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs font-mono">
          <button
            type="button"
            onClick={() => setActiveTab('sources')}
            className={`px-2.5 py-1 rounded transition-all ${ activeTab === 'sources' ? 'bg-slate-800 text-cyan-400 font-bold shadow' : 'text-slate-400 hover:text-white' }`}
          >
            Sources Breakdown
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('risk')}
            className={`px-2.5 py-1 rounded transition-all ${ activeTab === 'risk' ? 'bg-slate-800 text-red-400 font-bold shadow' : 'text-slate-400 hover:text-white' }`}
          >
            Risk Tiers
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('frp')}
            className={`px-2.5 py-1 rounded transition-all ${ activeTab === 'frp' ? 'bg-slate-800 text-amber-400 font-bold shadow' : 'text-slate-400 hover:text-white' }`}
          >
            Peak FRP (MW)
          </button>
        </div>
      </div>

      {/* Primary Analytics Surface */}
      <div className="min-h-[220px]">
        {activeTab === 'sources' && (
          <div className="space-y-3">
            <div className="text-xs text-slate-400 flex items-center justify-between">
              <span>Classified Source Distribution & Mean Power</span>
              <span className="font-mono text-cyan-400 font-semibold">
                Dominant: {summary?.dominant_source || 'wildfire'}
              </span>
            </div>

            <div className="h-52 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={sourcesData} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                  <XAxis
                    dataKey="name"
                    tick={{ fill: '#94a3b8', fontSize: 10 }}
                    interval={0}
                    angle={-15}
                    textAnchor="end"
                  />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0b0f19',
                      borderColor: '#1e293b',
                      borderRadius: '8px',
                      color: '#f8fafc',
                      fontSize: '11px',
                    }}
                  />
                  <Bar dataKey="count" fill="#3b82f6" name="Incident Count" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="avgFrp" fill="#f97316" name="Avg FRP (MW)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {activeTab === 'risk' && (
          <div className="space-y-3">
            <div className="text-xs text-slate-400 flex items-center justify-between">
              <span>Risk Severity Distribution Tiers</span>
              <span className="font-mono text-red-400 font-semibold">
                Critical + High: {(summary?.critical_risk_count ?? 0) + (summary?.high_risk_count ?? 0)}
              </span>
            </div>

            <div className="h-52 w-full flex items-center justify-center">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={riskDistributionData}
                    cx="50%"
                    cy="50%"
                    innerRadius={55}
                    outerRadius={80}
                    paddingAngle={4}
                    dataKey="value"
                  >
                    {riskDistributionData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0b0f19',
                      borderColor: '#1e293b',
                      borderRadius: '8px',
                      color: '#f8fafc',
                      fontSize: '11px',
                    }}
                  />
                  <Legend
                    verticalAlign="bottom"
                    height={36}
                    formatter={(value) => <span className="text-xs text-slate-300">{value}</span>}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {activeTab === 'frp' && (
          <div className="space-y-3">
            <div className="text-xs text-slate-400 flex items-center justify-between">
              <span>Highest Convective Fire Radiative Power Incidents</span>
              <span className="font-mono text-amber-400 font-semibold">
                Max: {summary?.max_frp || 165.0} MW
              </span>
            </div>

            <div className="h-52 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={topFrpData} layout="vertical" margin={{ top: 5, right: 20, left: 40, bottom: 5 }}>
                  <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 10 }} unit=" MW" />
                  <YAxis dataKey="id" type="category" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0b0f19',
                      borderColor: '#1e293b',
                      borderRadius: '8px',
                      color: '#f8fafc',
                      fontSize: '11px',
                    }}
                    formatter={(val, name, item) => [`${val} MW (${item.payload.place})`, 'FRP Intensity']}
                  />
                  <Bar dataKey="frp" fill="#ef4444" radius={[0, 4, 4, 0]} name="Radiative Power (MW)" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>

      {/* Bottom Summary Bar */}
      <div className="pt-3 border-t border-slate-800/80 grid grid-cols-3 gap-2 text-center text-xs">
        <div className="p-2 rounded bg-slate-950 border border-slate-800">
          <div className="text-[10px] text-slate-500 font-mono">EVALUATED</div>
          <div className="text-xs font-bold text-white mt-0.5 font-mono">
            {sources?.total_evaluated || hotspots.length} Anomalies
          </div>
        </div>
        <div className="p-2 rounded bg-slate-950 border border-slate-800">
          <div className="text-[10px] text-slate-500 font-mono">AVG FRP</div>
          <div className="text-xs font-bold text-cyan-400 mt-0.5 font-mono">
            {summary?.average_frp ? `${summary.average_frp.toFixed(1)} MW` : '—'}
          </div>
        </div>
        <div className="p-2 rounded bg-slate-950 border border-slate-800">
          <div className="text-[10px] text-slate-500 font-mono">AVG RISK</div>
          <div className="text-xs font-bold text-amber-400 mt-0.5 font-mono">
            {summary?.average_risk_score ? `${summary.average_risk_score.toFixed(1)}/100` : '—'}
          </div>
        </div>
      </div>
    </section>
  );
};

export default AnalyticsPanel;
