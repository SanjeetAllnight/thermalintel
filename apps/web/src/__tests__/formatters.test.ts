import { describe, it, expect } from 'vitest';
import {
  formatCoordinates,
  formatDistance,
  formatFrp,
  formatTemp,
  formatTimestamp,
  formatRelativeTime,
  getRiskLevelMeta,
  getSourceMeta,
  getAlertSeverityMeta,
  getIncidentStatus,
  getIncidentStatusMeta,
  getIncidentChangeIndicator,
  getFreshnessMeta,
} from '../lib/formatters';

describe('Formatters & Operational Metas', () => {
  it('formats coordinates correctly', () => {
    expect(formatCoordinates(38.7421, -122.8105)).toBe('38.7421°N, 122.8105°W');
    expect(formatCoordinates(-33.8688, 151.2093)).toBe('33.8688°S, 151.2093°E');
    expect(formatCoordinates(undefined, undefined)).toBe('—');
  });

  it('formats distance in meters and kilometers', () => {
    expect(formatDistance(450)).toBe('450 m');
    expect(formatDistance(1200)).toBe('1.2 km');
    expect(formatDistance(null)).toBe('N/A');
  });

  it('formats fire radiative power (FRP)', () => {
    expect(formatFrp(142.8)).toBe('142.8 MW');
    expect(formatFrp(null)).toBe('0.0 MW');
  });

  it('formats temperature in Celsius', () => {
    expect(formatTemp(29.4)).toBe('29.4°C');
    expect(formatTemp(null)).toBe('—');
  });

  it('formats timestamp and relative time safely', () => {
    const iso = '2026-10-01T08:45:00Z';
    expect(formatTimestamp(iso)).toContain('2026');
    expect(formatRelativeTime(iso)).toBeDefined();
    expect(formatTimestamp(null)).toBe('—');
    expect(formatRelativeTime(null)).toBe('—');
  });

  it('returns distinct metadata for risk levels', () => {
    const critical = getRiskLevelMeta('critical');
    expect(critical.label).toBe('CRITICAL');
    expect(critical.fillHex).toBe('#ef4444');

    const low = getRiskLevelMeta('low');
    expect(low.label).toBe('LOW');
  });

  it('returns appropriate source type metadata', () => {
    const wildfire = getSourceMeta('wildfire');
    expect(wildfire.label).toBe('Wildfire');
    expect(wildfire.icon).toBe('🔥');

    const unknown = getSourceMeta('unknown');
    expect(unknown.label).toBe('Unknown Source');
  });

  it('determines incident status from hotspot risk level or explicit status', () => {
    expect(getIncidentStatus({ risk_level: 'critical', frp: 120 })).toBe('active');
    expect(getIncidentStatus({ risk_level: 'high', frp: 80 })).toBe('monitoring');
    expect(getIncidentStatus({ risk_level: 'low', frp: 10 })).toBe('contained');
    expect(getIncidentStatus({ status: 'resolved', risk_level: 'critical' })).toBe('resolved');
  });

  it('returns incident status metadata with pulse flag', () => {
    const active = getIncidentStatusMeta('active');
    expect(active.label).toBe('ACTIVE');
    expect(active.pulse).toBe(true);

    const contained = getIncidentStatusMeta('contained');
    expect(contained.label).toBe('CONTAINED');
    expect(contained.pulse).toBe(false);
  });

  it('derives important change indicator without color dependence', () => {
    const anomaly = getIncidentChangeIndicator({
      frp: 50,
      is_anomaly: true,
      risk_level: 'high',
      risk_score: 70,
    });
    expect(anomaly.label).toContain('Statistical Outlier');

    const surge = getIncidentChangeIndicator({
      frp: 140,
      is_anomaly: false,
      risk_level: 'critical',
      risk_score: 90,
    });
    expect(surge.label).toContain('Extreme FRP');
  });

  it('returns freshness metadata for all states', () => {
    expect(getFreshnessMeta('fresh').label).toBe('FRESH');
    expect(getFreshnessMeta('cached').label).toBe('CACHED');
    expect(getFreshnessMeta('stale').label).toBe('STALE');
    expect(getFreshnessMeta('derived').label).toBe('DERIVED');
    expect(getFreshnessMeta('synthetic').label).toBe('SYNTHETIC');
    expect(getFreshnessMeta('unavailable').label).toBe('UNAVAILABLE');
  });
});
