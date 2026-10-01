import { RiskLevel, SourceType, AlertSeverity } from '../types/api';

/**
 * Format geographic coordinates to readable latitude/longitude string
 */
export function formatCoordinates(lat?: number, lon?: number): string {
  if (lat === undefined || lon === undefined || lat === null || lon === null) return '—';
  const latDir = lat >= 0 ? 'N' : 'S';
  const lonDir = lon >= 0 ? 'E' : 'W';
  return `${Math.abs(lat).toFixed(4)}°${latDir}, ${Math.abs(lon).toFixed(4)}°${lonDir}`;
}

/**
 * Format distance in meters to readable km or meters
 */
export function formatDistance(meters?: number | null): string {
  if (meters === undefined || meters === null) return 'N/A';
  if (meters >= 1000) {
    return `${(meters / 1000).toFixed(1)} km`;
  }
  return `${Math.round(meters)} m`;
}

/**
 * Format FRP in megawatts
 */
export function formatFrp(frp?: number | null): string {
  if (frp === undefined || frp === null) return '0.0 MW';
  return `${frp.toFixed(1)} MW`;
}

/**
 * Format temperature in Celsius
 */
export function formatTemp(temp?: number | null): string {
  if (temp === undefined || temp === null) return '—';
  return `${temp.toFixed(1)}°C`;
}

/**
 * Format ISO timestamp to readable date/time
 */
export function formatTimestamp(isoString?: string | null): string {
  if (!isoString) return '—';
  try {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return isoString;
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
      timeZoneName: 'short',
    }).format(date);
  } catch {
    return isoString;
  }
}

/**
 * Format time relative to now (e.g. "12m ago")
 */
export function formatRelativeTime(isoString?: string | null): string {
  if (!isoString) return '—';
  try {
    const date = new Date(isoString);
    const now = new Date();
    const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);

    if (diffSec < 60) return 'just now';
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return `${Math.floor(diffSec / 86400)}d ago`;
  } catch {
    return '—';
  }
}

/**
 * Get color tokens for risk level
 */
export function getRiskLevelMeta(level?: RiskLevel | string) {
  const norm = (level || 'low').toLowerCase();
  switch (norm) {
    case 'critical':
      return {
        label: 'CRITICAL',
        badgeBg: 'bg-red-500/20 text-red-400 border border-red-500/40',
        textColor: 'text-red-500',
        borderColor: 'border-red-500',
        bgColor: 'bg-red-500',
        ringColor: 'ring-red-500/30',
        glowClass: 'shadow-red-500/30',
        fillHex: '#ef4444',
      };
    case 'high':
      return {
        label: 'HIGH',
        badgeBg: 'bg-amber-500/20 text-amber-400 border border-amber-500/40',
        textColor: 'text-amber-500',
        borderColor: 'border-amber-500',
        bgColor: 'bg-amber-500',
        ringColor: 'ring-amber-500/30',
        glowClass: 'shadow-amber-500/30',
        fillHex: '#f59e0b',
      };
    case 'medium':
      return {
        label: 'MEDIUM',
        badgeBg: 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/40',
        textColor: 'text-yellow-400',
        borderColor: 'border-yellow-500',
        bgColor: 'bg-yellow-500',
        ringColor: 'ring-yellow-500/30',
        glowClass: 'shadow-yellow-500/30',
        fillHex: '#eab308',
      };
    case 'low':
    default:
      return {
        label: 'LOW',
        badgeBg: 'bg-slate-800 text-slate-400 border border-slate-700',
        textColor: 'text-slate-400',
        borderColor: 'border-slate-700',
        bgColor: 'bg-slate-600',
        ringColor: 'ring-slate-600/30',
        glowClass: 'shadow-slate-500/20',
        fillHex: '#64748b',
      };
  }
}

/**
 * Get human-readable label and icon for source type
 */
export function getSourceMeta(type?: SourceType | string) {
  const norm = (type || 'unknown').toLowerCase();
  switch (norm) {
    case 'wildfire':
      return {
        label: 'Wildfire',
        tagBg: 'bg-red-950/60 text-red-300 border-red-800/80',
        icon: '🔥',
        description: 'Rapidly spreading wildland vegetative fire',
      };
    case 'industrial':
      return {
        label: 'Industrial Facility',
        tagBg: 'bg-cyan-950/60 text-cyan-300 border-cyan-800/80',
        icon: '🏭',
        description: 'Petrochemical refinery or flare stack emission',
      };
    case 'agricultural':
      return {
        label: 'Agricultural Burn',
        tagBg: 'bg-emerald-950/60 text-emerald-300 border-emerald-800/80',
        icon: '🌾',
        description: 'Seasonal field clearing or stubble burning',
      };
    case 'prescribed_burn':
      return {
        label: 'Prescribed Burn',
        tagBg: 'bg-blue-950/60 text-blue-300 border-blue-800/80',
        icon: '🌲',
        description: 'Controlled forest management parcel treatment',
      };
    case 'urban':
      return {
        label: 'Urban / Structure',
        tagBg: 'bg-purple-950/60 text-purple-300 border-purple-800/80',
        icon: '🏢',
        description: 'Commercial or dense urban footprint thermal mass',
      };
    case 'volcanic':
      return {
        label: 'Volcanic Activity',
        tagBg: 'bg-orange-950/60 text-orange-300 border-orange-800/80',
        icon: '🌋',
        description: 'Active crater or caldera lava effusion',
      };
    default:
      return {
        label: 'Unknown Source',
        tagBg: 'bg-slate-900 text-slate-400 border-slate-800',
        icon: '❓',
        description: 'Unclassified thermal radiation signature',
      };
  }
}

/**
 * Get color tokens for Alert severity
 */
export function getAlertSeverityMeta(severity?: AlertSeverity | string) {
  const norm = (severity || 'info').toLowerCase();
  switch (norm) {
    case 'critical':
      return {
        label: 'CRITICAL',
        badgeBg: 'bg-red-500/20 text-red-400 border-red-500/40',
        borderLeft: 'border-l-red-500',
        iconBg: 'bg-red-500/10 text-red-400',
      };
    case 'warning':
      return {
        label: 'WARNING',
        badgeBg: 'bg-amber-500/20 text-amber-400 border-amber-500/40',
        borderLeft: 'border-l-amber-500',
        iconBg: 'bg-amber-500/10 text-amber-400',
      };
    case 'info':
    default:
      return {
        label: 'ADVISORY',
        badgeBg: 'bg-blue-500/20 text-blue-400 border-blue-500/40',
        borderLeft: 'border-l-blue-500',
        iconBg: 'bg-blue-500/10 text-blue-400',
      };
  }
}
