import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SystemModeBadge } from '../components/system/SystemModeBadge';
import { SourceHealthCard } from '../components/system/SourceHealthCard';
import { SourceHealthItem } from '../types/system';

describe('System Mode & Source Health UI', () => {
  it('renders LIVE state with streaming indicator', () => {
    render(<SystemModeBadge mode="LIVE" />);
    expect(screen.getByText('LIVE STREAM')).toBeDefined();
    expect(screen.getByText('NRT VIIRS 375m')).toBeDefined();
  });

  it('renders CACHE state with cache age and stale warning', () => {
    render(<SystemModeBadge mode="CACHE" cacheAgeSeconds={120} isStale={false} />);
    expect(screen.getByText('CACHED (2m ago)')).toBeDefined();
    expect(screen.getByText('VALID')).toBeDefined();
  });

  it('renders CACHE state with STALE tag when stale', () => {
    render(<SystemModeBadge mode="CACHE" cacheAgeSeconds={350} isStale={true} />);
    expect(screen.getByText('CACHED (5m ago)')).toBeDefined();
    expect(screen.getByText('STALE')).toBeDefined();
  });

  it('renders DEMO state without claiming live status', () => {
    render(<SystemModeBadge mode="DEMO" />);
    expect(screen.getByText('DEMO MODE')).toBeDefined();
    expect(screen.getByText('DETERMINISTIC')).toBeDefined();
    expect(screen.queryByText('LIVE STREAM')).toBeNull();
  });

  it('renders REPLAY state with historical tag', () => {
    render(<SystemModeBadge mode="REPLAY" />);
    expect(screen.getByText('REPLAY STANDBY')).toBeDefined();
    expect(screen.getByText('HISTORICAL')).toBeDefined();
  });

  it('renders degraded flag when degraded is true', () => {
    render(<SystemModeBadge mode="LIVE" degraded={true} />);
    expect(screen.getByText('DEGRADED')).toBeDefined();
  });

  it('renders SourceHealthCard with expected provider status rows', () => {
    const sampleSources: SourceHealthItem[] = [
      { id: 'firms', name: 'NASA FIRMS', category: 'satellite', status: 'LIVE' },
      { id: 'osm', name: 'OSM Overpass', category: 'gis', status: 'CACHE' },
      { id: 'meteo', name: 'Open-Meteo', category: 'weather', status: 'LIVE' },
      { id: 'db', name: 'Database', category: 'database', status: 'HEALTHY' },
    ];

    render(<SourceHealthCard sources={sampleSources} />);
    expect(screen.getByText('NASA FIRMS')).toBeDefined();
    expect(screen.getByText('OSM Overpass')).toBeDefined();
    expect(screen.getByText('Open-Meteo')).toBeDefined();
    expect(screen.getByText('Database')).toBeDefined();
    expect(screen.getByText('HEALTHY')).toBeDefined();
  });
});
