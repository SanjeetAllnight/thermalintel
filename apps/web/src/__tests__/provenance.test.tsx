import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ProvenanceBadge } from '../components/system/ProvenanceBadge';
import { ProvenanceCard } from '../components/system/ProvenanceCard';
import { ProvenanceRecord } from '../types/provenance';

describe('Provenance UI Components', () => {
  const sampleProvenance: ProvenanceRecord = {
    provider: 'NASA FIRMS',
    product: 'VIIRS_SNPP_NRT',
    observed_at_utc: '2026-10-01T08:45:00Z',
    fetched_at_utc: '2026-10-01T08:50:00Z',
    freshness_state: 'fresh',
    ttl_seconds: 900,
    reference: 'SHA256:TEST_REF_123',
  };

  it('renders ProvenanceBadge with provider and freshness state', () => {
    render(<ProvenanceBadge provenance={sampleProvenance} />);
    expect(screen.getByText('NASA FIRMS')).toBeDefined();
    expect(screen.getByText('FRESH')).toBeDefined();
  });

  it('renders ProvenanceCard collapsed by default and expands on click', () => {
    render(
      <ProvenanceCard
        domainName="Satellite Remote Sensing"
        provenance={sampleProvenance}
        defaultExpanded={false}
      />
    );

    expect(screen.getByText('Satellite Remote Sensing Provenance')).toBeDefined();
    expect(screen.queryByText(/SHA256:TEST_REF_123/)).toBeNull();

    // Click to expand
    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByText(/SHA256:TEST_REF_123/)).toBeDefined();
    expect(screen.getByText('TTL: 900s')).toBeDefined();
  });

  it('renders cached and stale states in ProvenanceCard', () => {
    const cachedProvenance: ProvenanceRecord = {
      ...sampleProvenance,
      freshness_state: 'cached',
    };
    render(
      <ProvenanceCard
        domainName="Geospatial Context"
        provenance={cachedProvenance}
        defaultExpanded={true}
      />
    );

    expect(screen.getByText('CACHED')).toBeDefined();
  });
});
