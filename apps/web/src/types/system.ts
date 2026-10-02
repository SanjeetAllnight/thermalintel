/**
 * System Mode and Source Health Types (Aligned with Requirements 7 & 8)
 */

export type SystemMode = 'LIVE' | 'CACHE' | 'DEMO' | 'REPLAY' | 'SYNTHETIC';

export type SourceStatus =
  | 'LIVE'
  | 'CACHE'
  | 'HEALTHY'
  | 'DEGRADED'
  | 'UNAVAILABLE'
  | 'STANDBY';

export interface SourceHealthItem {
  id: string;
  name: string;
  category: 'satellite' | 'gis' | 'weather' | 'database' | 'ai';
  status: SourceStatus;
  detail?: string;
  lastSync?: string;
}

export interface ReplayState {
  enabled: boolean;
  isSimulated: boolean;
  virtualTimeUtc: string;
  speed: number;
  availableTimeRange?: [string, string];
}
