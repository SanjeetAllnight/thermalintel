import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { IncidentDetailDrawer } from '../components/incidents/IncidentDetailDrawer';
import { IncidentDetail } from '../types/api';

describe('IncidentDetailDrawer Component', () => {
  const sampleIncident: IncidentDetail = {
    hotspot: {
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
      bright_t31: null, // Test explicit missing value handling!
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
    },
    geospatial: {
      land_cover: 'Dense Coniferous Pine Forest',
      nearest_infrastructure: 'State Route 175',
      distance_to_infrastructure_meters: 450.0,
      nearest_settlement: 'Cobb Mountain Community',
      distance_to_settlement_meters: 1200.0,
      is_protected_area: true,
      protected_area_name: 'Demonstration State Forest',
      elevation_meters: 985.0,
      slope_degrees: 28.5,
      fuel_load_estimate: 'Extreme Dry Chaparral',
    },
    weather: {
      temperature_celsius: 29.4,
      relative_humidity_percent: 14.0,
      wind_speed_kmh: 38.5,
      wind_gust_kmh: 58.0,
      wind_direction_degrees: 42.0,
      wind_direction_cardinal: 'NE',
      precipitation_mm: 0.0,
      fire_weather_index: 88.5,
      forecast_summary: 'Red Flag Warning in effect.',
    },
    historical: {
      prior_detections_30d: 1,
      prior_detections_90d: 3,
      is_recurrent_site: false,
      recurrent_pattern: 'none',
      first_detected_date: '2026-09-28',
      detection_frequency_score: 0.12,
    },
    intelligence: {
      hotspot_id: 'VIIRS-TEST-001',
      classification: {
        predicted_source: 'wildfire',
        confidence: 0.96,
        probabilities: { wildfire: 0.96, prescribed_burn: 0.04 },
        feature_importance: null, // Explicitly missing feature_importance case!
      },
      anomaly: {
        is_anomaly: true,
        anomaly_score: 0.94,
        baseline_deviation: 4.8,
        anomaly_rationale: 'FRP of 142.8 MW is 4.8 sigma above historical baseline.',
      },
      risk: {
        risk_score: 92.5,
        risk_level: 'critical',
        frp_component: 94.0,
        weather_component: 96.0,
        proximity_component: 88.0,
        historical_component: 20.0,
        explainable_factors: [
          {
            factor: 'Extreme Fire Radiative Power (142.8 MW)',
            weight: 0.35,
            impact: 'critical',
            description: 'Intense convective thermal energy indicative of rapidly advancing canopy fire.',
          },
        ],
        recommended_action: 'Issue immediate structural defense advisory.',
      },
      model_version: 'v1.0-rf-heuristic',
      evaluated_at: '2026-10-01T08:52:00Z',
    },
    timeline: [
      {
        timestamp: '2026-10-01T08:45:00Z',
        event_type: 'satellite_pass',
        summary: 'Suomi-NPP VIIRS pass detected 142.8 MW anomaly',
      },
    ],
    data_mode: 'demo',
  };

  it('renders the core 4 operational hierarchy sections (WHAT, WHY, HOW CERTAIN, WHAT CHANGED)', () => {
    render(
      <IncidentDetailDrawer
        incident={sampleIncident}
        onClose={() => {}}
      />
    );

    // WHAT
    expect(screen.getByText('VIIRS-TEST-001')).toBeDefined();
    expect(screen.getByText('CRITICAL SEVERITY')).toBeDefined();

    // WHY
    expect(screen.getByText(/WHY THIS WAS FLAGGED/)).toBeDefined();
    expect(screen.getByText(/FRP of 142.8 MW is 4.8 sigma above historical baseline/)).toBeDefined();

    // HOW CERTAIN
    expect(screen.getByText(/HOW CERTAIN/)).toBeDefined();
    expect(screen.getByText('96%')).toBeDefined(); // AI classification confidence

    // WHAT CHANGED
    expect(screen.getByText(/WHAT CHANGED/)).toBeDefined();
  });

  it('gracefully handles missing feature_importance without crashing or errors', () => {
    render(
      <IncidentDetailDrawer
        incident={sampleIncident}
        onClose={() => {}}
      />
    );

    // Should render fallback text rather than empty or crash
    expect(screen.getByText(/Model feature importance weights are unavailable/)).toBeDefined();
  });

  it('renders explicit Unavailable badge for missing bright_t31 value', () => {
    render(
      <IncidentDetailDrawer
        incident={sampleIncident}
        onClose={() => {}}
      />
    );

    expect(screen.getByText('Unavailable')).toBeDefined();
  });

  it('renders explicit Unknown Incident error when an incident is not found', () => {
    const errorState = {
      id: 'UNKNOWN-INC-999',
      message: "Incident with ID 'UNKNOWN-INC-999' not found in active telemetry registry",
      notFound: true,
    };

    render(
      <IncidentDetailDrawer
        incident={null}
        onClose={() => {}}
        error={errorState}
      />
    );

    expect(screen.getByText(/INCIDENT NOT FOUND: UNKNOWN-INC-999/)).toBeDefined();
    expect(screen.getByText(/does not exist in the active telemetry registry/)).toBeDefined();
    // Does NOT silently display mock incident 1
    expect(screen.queryByText('VIIRS-SNPP-20261001-001')).toBeNull();
  });

  it('allows switching deeper data tabs', () => {
    render(
      <IncidentDetailDrawer
        incident={sampleIncident}
        onClose={() => {}}
      />
    );

    // Click Weather tab
    fireEvent.click(screen.getByRole('button', { name: 'Weather' }));
    expect(screen.getByText(/Synoptic Weather Telemetry/)).toBeDefined();

    // Click Geospatial tab
    fireEvent.click(screen.getByRole('button', { name: 'Geospatial' }));
    expect(screen.getByText(/Geospatial & Critical Infrastructure Buffer/)).toBeDefined();

    // Click Provenance tab
    fireEvent.click(screen.getByRole('button', { name: 'Provenance' }));
    expect(screen.getByText(/Complete Data Provenance & Ingestion Audit/)).toBeDefined();
  });
});
