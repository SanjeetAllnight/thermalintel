import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import DashboardPage from '../app/page';
import { NavRail } from '../components/navigation/NavRail';
import { ReplayControl } from '../components/system/ReplayControl';
import { IncidentDetailDrawer } from '../components/incidents/IncidentDetailDrawer';
import { Hotspot, IncidentDetail } from '../types/api';

const mockHotspot: Hotspot = {
  id: 'VIIRS-TEST-UX-001',
  latitude: 38.7521,
  longitude: -122.8124,
  brightness: 365.4,
  scan: 0.32,
  track: 0.35,
  acq_date: '2026-10-01',
  acq_time: '08:45',
  satellite: 'N',
  instrument: 'VIIRS',
  confidence: 'high',
  version: '2.0.0',
  bright_t31: 298.2,
  frp: 185.4,
  daynight: 'D',
  source_type: 'wildfire',
  risk_score: 91.5,
  risk_level: 'critical',
  is_anomaly: true,
  cluster_id: 'CLUSTER-99',
  cluster_size: 14,
  nearest_place: 'Geysers Geothermal Basin, CA',
  last_updated: '2026-10-01T08:50:00Z',
};

const mockIncidentDetail: IncidentDetail = {
  hotspot: mockHotspot,
  geospatial: {
    land_cover: 'Coniferous Pine Forest',
    nearest_infrastructure: 'Geysers Calpine Substation 230kV',
    distance_to_infrastructure_meters: 650,
    nearest_settlement: 'Cloverdale',
    distance_to_settlement_meters: 7200,
    is_protected_area: true,
    protected_area_name: 'Mayacamas Sanctuary',
    elevation_meters: 840,
    slope_degrees: 28,
    fuel_load_estimate: 'High Conifer Timber',
  },
  weather: {
    temperature_celsius: 34.5,
    relative_humidity_percent: 11.2,
    wind_speed_kmh: 38.5,
    wind_gust_kmh: 58.0,
    wind_direction_degrees: 45,
    wind_direction_cardinal: 'NE',
    precipitation_mm: 0.0,
    fire_weather_index: 68.4,
    forecast_summary: 'Severe Fire Weather Red Flag Warning',
  },
  historical: {
    prior_detections_30d: 4,
    prior_detections_90d: 9,
    is_recurrent_site: true,
    recurrent_pattern: 'Active wildfire progression corridor',
    first_detected_date: '2026-09-28',
    detection_frequency_score: 0.78,
  },
  intelligence: {
    hotspot_id: 'VIIRS-TEST-UX-001',
    classification: {
      predicted_source: 'wildfire',
      confidence: 0.965,
      probabilities: {
        wildfire: 0.965,
        industrial: 0.02,
        prescribed_burn: 0.015,
      },
    },
    anomaly: {
      is_anomaly: true,
      anomaly_score: -0.74,
      anomaly_rationale: 'Extreme FRP + High Wind Spread',
      baseline_deviation: 3.85,
    },
    risk: {
      risk_score: 91.5,
      risk_level: 'critical',
      frp_component: 35.0,
      weather_component: 25.0,
      proximity_component: 20.0,
      historical_component: 11.5,
      explainable_factors: [
        {
          factor: 'Thermal Radiative Power (185.4 MW)',
          weight: 0.35,
          impact: 'critical',
          description: 'Intense thermal combustion core detected by VIIRS I-band',
        },
        {
          factor: 'Substation Proximity (650m)',
          weight: 0.25,
          impact: 'critical',
          description: 'Threat to regional electrical transmission infrastructure',
        },
      ],
      recommended_action: 'Dispatch CalFire aerial reconnaissance immediately',
    },
    model_version: '2.4.0-rf-isolation',
    evaluated_at: '2026-10-01T08:52:00Z',
  },
  timeline: [
    {
      timestamp: '2026-10-01T08:45:00Z',
      event_type: 'DETECTION',
      summary: 'VIIRS Suomi-NPP 375m thermal pixel triggered anomaly threshold',
    },
  ],
  data_mode: 'live',
};

describe('Phase 6 UX / Command Center Architecture Tests', () => {
  it('renders Navigation Rail with operational modes and navigation targets', () => {
    const handleViewChange = vi.fn();
    const handleToggleReplay = vi.fn();

    render(
      <NavRail
        activeView="command"
        onViewChange={handleViewChange}
        incidentCount={42}
        alertCount={3}
        criticalCount={2}
        isReplayActive={false}
        onToggleReplay={handleToggleReplay}
      />
    );

    // Verify rail is rendered with ARIA navigation role
    expect(screen.getByRole('navigation', { name: /Command Center Rail/i })).toBeDefined();

    // Verify navigation buttons
    expect(screen.getByRole('button', { name: 'Command Center' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'Incident Queue' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'Threat Advisories' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'Risk Analytics' })).toBeDefined();

    // Verify badge counts
    expect(screen.getByText('42')).toBeDefined();
    expect(screen.getByText('3')).toBeDefined();

    // Click navigation item
    fireEvent.click(screen.getByLabelText(/Threat Advisories/i));
    expect(handleViewChange).toHaveBeenCalledWith('alerts');

    // Click Replay trigger
    fireEvent.click(screen.getByLabelText(/Activate Replay Mode/i));
    expect(handleToggleReplay).toHaveBeenCalled();
  });

  it('renders 5-Part Explainability Narrative and Separates 5 Confidence/Risk Pillars', () => {
    const handleClose = vi.fn();

    render(
      <IncidentDetailDrawer
        incident={mockIncidentDetail}
        onClose={handleClose}
        loading={false}
        error={null}
      />
    );

    // Dialog is accessible
    expect(screen.getByRole('dialog')).toBeDefined();

    // 1. WHAT HAPPENED
    expect(screen.getByText(/WHAT HAPPENED/i)).toBeDefined();
    expect(screen.getAllByText(/185.4 MW/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/38.7521°N, 122.8124°W/i)).toBeDefined();

    // 2. WHY THE SYSTEM THINKS IT HAPPENED
    expect(screen.getByText(/WHY THE SYSTEM THINKS IT HAPPENED/i)).toBeDefined();
    expect(screen.getByText(/3.85σ Outlier/i)).toBeDefined();
    expect(screen.getByText(/Thermal Radiative Power \(185.4 MW\)/i)).toBeDefined();

    // 3. HOW CONFIDENT THE SYSTEM IS - 5 distinct pillars
    expect(screen.getByText(/HOW CONFIDENT THE SYSTEM IS/i)).toBeDefined();
    expect(screen.getByText(/Satellite Detection Confidence/i)).toBeDefined();
    expect(screen.getByText(/AI Classification Confidence/i)).toBeDefined();
    expect(screen.getByText(/Context Completeness/i)).toBeDefined();
    expect(screen.getByText(/Statistical Anomaly Score/i)).toBeDefined();
    expect(screen.getByText(/Composite Risk Score/i)).toBeDefined();

    // 4. WHAT CHANGED
    expect(screen.getByText(/WHAT CHANGED/i)).toBeDefined();
    expect(screen.getByText(/Active Wildfire Progression Corridor/i)).toBeDefined();

    // 5. WHAT THE SYSTEM DID / RECOMMENDED ACTION
    expect(screen.getByText(/WHAT THE SYSTEM DID/i)).toBeDefined();
    expect(screen.getByText(/Dispatch CalFire aerial reconnaissance immediately/i)).toBeDefined();
  });

  it('renders operational ReplayControl with satellite pass markers and timeline stepping', () => {
    const handleToggle = vi.fn();
    const handleTimeChange = vi.fn();

    render(
      <ReplayControl
        isActive={true}
        onToggleReplay={handleToggle}
        virtualTime="2026-10-01T08:45:00Z"
        onTimeChange={handleTimeChange}
      />
    );

    expect(screen.getByText(/TEMPORAL REPLAY SUITE/i)).toBeDefined();
    expect(screen.getByText(/REPLAY ACTIVE/i)).toBeDefined();
    expect(screen.getByText(/2026-10-01T08:45:00Z/i)).toBeDefined();

    // Satellite pass markers
    expect(screen.getByText(/SNPP/i)).toBeDefined();
    expect(screen.getByText(/NOAA-20/i)).toBeDefined();
    expect(screen.getByText(/NOAA-21/i)).toBeDefined();

    // Stepper buttons
    expect(screen.getByTitle(/Step Backward/i)).toBeDefined();
    expect(screen.getByTitle(/Play Timeline/i)).toBeDefined();
    expect(screen.getByTitle(/Step Forward/i)).toBeDefined();

    // Return to Live button
    const returnBtn = screen.getByRole('button', { name: /Return To Live/i });
    fireEvent.click(returnBtn);
    expect(handleToggle).toHaveBeenCalledWith(false);
  });
});
