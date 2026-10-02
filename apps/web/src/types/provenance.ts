/**
 * Provenance Specification Types (Aligned with docs/V2_CONTRACTS.md Section 5)
 */

export type FreshnessState =
  | 'fresh'
  | 'cached'
  | 'stale'
  | 'unavailable'
  | 'synthetic'
  | 'derived';

export interface ProvenanceRecord {
  provider: string; // Originating service (e.g. NASA_FIRMS, OpenStreetMap, Open-Meteo)
  product: string; // Specific dataset/product (e.g. VIIRS_SNPP_NRT, Overpass API, GFS Synoptic)
  observed_at_utc?: string | null;
  fetched_at_utc?: string | null;
  freshness_state: FreshnessState;
  ttl_seconds?: number;
  reference?: string | null;
}
