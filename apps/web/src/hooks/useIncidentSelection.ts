'use client';

import { useState, useCallback } from 'react';
import { IncidentDetail } from '../types/api';
import dataProvider from '../lib/data-provider';

export interface IncidentDetailError {
  id: string;
  message: string;
  notFound: boolean;
}

export function useIncidentSelection() {
  const [selectedHotspotId, setSelectedHotspotId] = useState<string | null>(null);
  const [selectedIncident, setSelectedIncident] = useState<IncidentDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [detailError, setDetailError] = useState<IncidentDetailError | null>(null);
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);

  const selectIncident = useCallback(async (id: string) => {
    setSelectedHotspotId(id);
    setDrawerOpen(true);
    setLoadingDetail(true);
    setDetailError(null);

    try {
      const detail = await dataProvider.getIncidentDetail(id);
      setSelectedIncident(detail);
      setDetailError(null);
    } catch (err: any) {
      console.warn(`Failed to retrieve incident detail for ID '${id}':`, err);
      setSelectedIncident(null);
      setDetailError({
        id,
        message: err?.message || `Incident '${id}' could not be located in active registry.`,
        notFound: true,
      });
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedHotspotId(null);
    setSelectedIncident(null);
    setDetailError(null);
    setDrawerOpen(false);
  }, []);

  return {
    selectedHotspotId,
    selectedIncident,
    loadingDetail,
    detailError,
    drawerOpen,
    selectIncident,
    closeDrawer,
    clearSelection,
  };
}

export default useIncidentSelection;
