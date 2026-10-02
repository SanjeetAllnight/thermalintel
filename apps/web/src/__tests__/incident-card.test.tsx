import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { IncidentCard } from '../components/incidents/IncidentCard';
import { Hotspot } from '../types/api';

describe('IncidentCard Component', () => {
  const mockHotspot: Hotspot = {
    id: 'VIIRS-TEST-001',
    latitude: 38.7421,
    longitude: -122.8105,
    brightness: 352.4,
    scan: 0.38,
    track: 0.36,
    acq_date: '2026-10-01',
    acq_time: '0845',
    satellite: 'Suomi-NPP',
    instrument: 'VIIRS',
    confidence: 'high',
    version: '2.0NRT',
    bright_t31: 298.4,
    frp: 142.8,
    daynight: 'N',
    source_type: 'wildfire',
    risk_score: 92.5,
    risk_level: 'critical',
    is_anomaly: true,
    cluster_id: 'CL-01',
    cluster_size: 3,
    nearest_place: 'Geysers Basin, CA',
    last_updated: '2026-10-01T08:50:00Z',
  };

  it('renders critical incident with text label, icon, typography, and status', () => {
    render(
      <IncidentCard
        hotspot={mockHotspot}
        isSelected={false}
        onSelect={() => {}}
      />
    );

    // Text label for severity
    expect(screen.getByText('CRITICAL')).toBeDefined();
    // Incident ID
    expect(screen.getByText('VIIRS-TEST-001')).toBeDefined();
    // Operational Status
    expect(screen.getByText('ACTIVE')).toBeDefined();
    // Important change indicator
    expect(screen.getByText(/Statistical Outlier|Extreme FRP/)).toBeDefined();
    // Location
    expect(screen.getByText('Geysers Basin, CA')).toBeDefined();
    // FRP value
    expect(screen.getByText('142.8 MW')).toBeDefined();
  });

  it('supports keyboard accessibility via Enter and Space keys', () => {
    const onSelect = vi.fn();
    render(
      <IncidentCard
        hotspot={mockHotspot}
        isSelected={false}
        onSelect={onSelect}
      />
    );

    const card = screen.getByRole('button');
    expect(card.getAttribute('tabindex')).toBe('0');
    expect(card.getAttribute('aria-label')).toContain('VIIRS-TEST-001');

    // Trigger Enter key
    fireEvent.keyDown(card, { key: 'Enter', code: 'Enter' });
    expect(onSelect).toHaveBeenCalledWith('VIIRS-TEST-001');

    // Trigger Space key
    fireEvent.keyDown(card, { key: ' ', code: 'Space' });
    expect(onSelect).toHaveBeenCalledTimes(2);
  });

  it('indicates selected state with aria-pressed attribute', () => {
    const { rerender } = render(
      <IncidentCard
        hotspot={mockHotspot}
        isSelected={false}
        onSelect={() => {}}
      />
    );
    expect(screen.getByRole('button').getAttribute('aria-pressed')).toBe('false');

    rerender(
      <IncidentCard
        hotspot={mockHotspot}
        isSelected={true}
        onSelect={() => {}}
      />
    );
    expect(screen.getByRole('button').getAttribute('aria-pressed')).toBe('true');
  });
});
