import { describe, it, expect, beforeEach } from 'vitest';
import dataProvider from '../lib/data-provider';

describe('DataProvider Service & Boundary', () => {
  beforeEach(() => {
    dataProvider.setModePreference('demo');
  });

  it('retrieves known incident detail correctly', async () => {
    const detail = await dataProvider.getIncidentDetail('VIIRS-SNPP-20261001-001');
    expect(detail).toBeDefined();
    expect(detail.hotspot.id).toBe('VIIRS-SNPP-20261001-001');
  });

  it('explicitly throws error for unknown incident ID without falling back to mockHotspots[0]', async () => {
    await expect(dataProvider.getIncidentDetail('NON_EXISTENT_ID_9999')).rejects.toThrow(
      /not found in active telemetry registry/i
    );
  });

  it('filters hotspots in-memory by risk level and min_frp in demo mode', async () => {
    const criticalOnly = await dataProvider.getHotspots({ risk_level: 'critical' });
    expect(criticalOnly.items.every((h) => h.risk_level === 'critical')).toBe(true);

    const minFrp50 = await dataProvider.getHotspots({ min_frp: 50 });
    expect(minFrp50.items.every((h) => h.frp >= 50)).toBe(true);
  });

  it('tracks system mode correctly according to mode preferences', () => {
    dataProvider.setModePreference('demo');
    expect(dataProvider.getSystemMode()).toBe('DEMO');

    dataProvider.setModePreference('replay');
    expect(dataProvider.getSystemMode()).toBe('REPLAY');
  });

  it('throttles rapid consecutive refresh calls', async () => {
    const first = await dataProvider.refreshData();
    expect(first.status).toBe('success');

    const rapidSecond = await dataProvider.refreshData();
    expect(rapidSecond.status).toBe('throttled');
  });

  it('provides compact source health without fabricating status', () => {
    const sources = dataProvider.getSourceHealthList(null);
    expect(sources.length).toBeGreaterThan(0);
    const firms = sources.find((s) => s.id === 'nasa-firms');
    expect(firms).toBeDefined();
    expect(['LIVE', 'CACHE']).toContain(firms?.status);
  });
});
