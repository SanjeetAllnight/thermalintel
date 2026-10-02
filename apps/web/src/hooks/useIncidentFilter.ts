'use client';

import { useState, useMemo, useCallback } from 'react';
import { Hotspot, RiskLevel, SourceType } from '../types/api';

export interface FilterState {
  searchQuery: string;
  riskLevel: RiskLevel | 'all';
  sourceType: SourceType | 'all';
  minFrp: number;
  anomalyOnly: boolean;
  minConfidence: string;
}

export type SortField = 'risk' | 'frp' | 'time' | 'severity';

export const initialFilters: FilterState = {
  searchQuery: '',
  riskLevel: 'all',
  sourceType: 'all',
  minFrp: 0,
  anomalyOnly: false,
  minConfidence: 'all',
};

export function useIncidentFilter(allHotspots: Hotspot[]) {
  const [filters, setFilters] = useState<FilterState>(initialFilters);
  const [selectedRegion, setSelectedRegion] = useState<string>('all');
  const [sortBy, setSortBy] = useState<SortField>('risk');

  // 1. Regional Filter
  const regionalHotspots = useMemo(() => {
    if (selectedRegion === 'all') return allHotspots;
    if (selectedRegion === 'california') {
      return allHotspots.filter(
        (h) =>
          h.nearest_place?.includes('CA') ||
          (h.latitude >= 32.5 &&
            h.latitude <= 42.0 &&
            h.longitude >= -124.5 &&
            h.longitude <= -114.0)
      );
    }
    if (selectedRegion === 'gulf_industrial') {
      return allHotspots.filter(
        (h) =>
          h.nearest_place?.includes('TX') ||
          (h.latitude >= 25.0 &&
            h.latitude <= 32.0 &&
            h.longitude >= -98.0 &&
            h.longitude <= -88.0)
      );
    }
    if (selectedRegion === 'pacific_nw') {
      return allHotspots.filter(
        (h) => h.nearest_place?.includes('OR') || h.nearest_place?.includes('WA')
      );
    }
    if (selectedRegion === 'hawaii') {
      return allHotspots.filter(
        (h) =>
          h.nearest_place?.includes('HI') ||
          (h.latitude >= 18.0 &&
            h.latitude <= 23.0 &&
            h.longitude >= -161.0 &&
            h.longitude <= -154.0)
      );
    }
    return allHotspots;
  }, [allHotspots, selectedRegion]);

  // 2. Multi-axis Filters
  const filteredHotspots = useMemo(() => {
    const list = regionalHotspots.filter((h) => {
      // Search query
      if (filters.searchQuery.trim()) {
        const query = filters.searchQuery.toLowerCase();
        const matchId = h.id.toLowerCase().includes(query);
        const matchPlace = (h.nearest_place || '').toLowerCase().includes(query);
        const matchCluster = (h.cluster_id || '').toLowerCase().includes(query);
        if (!matchId && !matchPlace && !matchCluster) return false;
      }

      // Risk level
      if (
        filters.riskLevel !== 'all' &&
        h.risk_level.toLowerCase() !== filters.riskLevel.toLowerCase()
      ) {
        return false;
      }

      // Source type
      if (
        filters.sourceType !== 'all' &&
        h.source_type.toLowerCase() !== filters.sourceType.toLowerCase()
      ) {
        return false;
      }

      // Min FRP
      if (filters.minFrp > 0 && h.frp < filters.minFrp) {
        return false;
      }

      // Anomaly only
      if (filters.anomalyOnly && !h.is_anomaly) {
        return false;
      }

      // Min confidence
      if (filters.minConfidence !== 'all') {
        if (filters.minConfidence === 'high' && h.confidence !== 'high') {
          return false;
        }
      }

      return true;
    });

    // 3. Sorting
    return list.sort((a, b) => {
      if (sortBy === 'risk') {
        return b.risk_score - a.risk_score;
      }
      if (sortBy === 'frp') {
        return b.frp - a.frp;
      }
      if (sortBy === 'time') {
        const timeA = `${a.acq_date} ${a.acq_time}`;
        const timeB = `${b.acq_date} ${b.acq_time}`;
        return timeB.localeCompare(timeA);
      }
      if (sortBy === 'severity') {
        const ranks: Record<string, number> = {
          critical: 4,
          high: 3,
          medium: 2,
          low: 1,
        };
        return (ranks[b.risk_level] || 0) - (ranks[a.risk_level] || 0);
      }
      return 0;
    });
  }, [regionalHotspots, filters, sortBy]);

  const updateFilters = useCallback((partial: Partial<FilterState>) => {
    setFilters((prev) => ({ ...prev, ...partial }));
  }, []);

  const resetFilters = useCallback(() => {
    setFilters(initialFilters);
  }, []);

  return {
    filters,
    selectedRegion,
    sortBy,
    filteredHotspots,
    totalCount: regionalHotspots.length,
    filteredCount: filteredHotspots.length,
    setFilters: updateFilters,
    resetFilters,
    setSelectedRegion,
    setSortBy,
  };
}

export default useIncidentFilter;
