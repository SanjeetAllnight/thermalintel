import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import DashboardPage from '../app/page';

describe('Operational Command Center Smoke Test', () => {
  it('renders command center page with system status, queue, and KPI metrics', async () => {
    render(<DashboardPage />);

    // Brand title & System Mode
    expect(screen.getByText('Thermal')).toBeDefined();
    expect(screen.getByText('OPERATIONAL COMMAND')).toBeDefined();

    // Tabs
    expect(screen.getByRole('tab', { name: /Prioritized Queue & Tactical Map/i })).toBeDefined();
    expect(screen.getByRole('tab', { name: /Operational Alerts/i })).toBeDefined();
    expect(screen.getByRole('tab', { name: /Risk & Source Analytics/i })).toBeDefined();

    // KPI Summary
    expect(screen.getByText('Active Hotspots')).toBeDefined();
    expect(screen.getByText('Critical Priority')).toBeDefined();

    // Filter Bar
    expect(screen.getByPlaceholderText(/Search incident ID/i)).toBeDefined();

    // Wait for telemetry feed to populate
    const card = await screen.findByText('VIIRS-SNPP-20261001-001');
    expect(card).toBeDefined();

    // Click incident card to open detail drawer
    fireEvent.click(card);

    // Verify detail drawer opened with core sections
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeDefined();
      expect(screen.getByText(/WHY THIS WAS FLAGGED/i)).toBeDefined();
      expect(screen.getByText(/HOW CERTAIN/i)).toBeDefined();
      expect(screen.getByText(/WHAT CHANGED/i)).toBeDefined();
    });
  });

  it('allows switching to alerts and analytics tabs', async () => {
    render(<DashboardPage />);

    // Switch to Alerts tab
    fireEvent.click(screen.getByRole('tab', { name: /Operational Alerts/i }));
    await waitFor(() => {
      expect(screen.getByText(/Dispatched Operational Threat Advisories/i)).toBeDefined();
    });

    // Switch to Analytics tab
    fireEvent.click(screen.getByRole('tab', { name: /Risk & Source Analytics/i }));
    await waitFor(() => {
      expect(screen.getByText(/Intelligence Engine Architecture/i)).toBeDefined();
    });
  });
});
