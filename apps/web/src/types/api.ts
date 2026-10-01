/**
 * FROZEN API CONTRACT: TypeScript Types for ThermalIntel
 * Automatically aligned with backend Pydantic models in `services/api/schemas/`
 *
 * DO NOT modify these contracts without cross-agent synchronization.
 */

export type DataMode = 'live' | 'demo';

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export type SourceType =
  | 'wildfire'
  | 'industrial'
  | 'agricultural'
  | 'urban'
  | 'volcanic'
  | 'prescribed_burn'
  | 'unknown';

export type AlertSeverity = 'info' | 'warning' | 'critical';

export interface Coordinates {
  latitude: number;
  longitude: number;
}

export interface RiskFactor {
  factor: string;
  weight: number;
  impact: RiskLevel;
  description: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  data_mode: DataMode;
  timestamp: string;
  services: {
    database: string;
    firms_api: string;
    intelligence_engine: string;
    [key: string]: string;
  };
}

export interface Hotspot {
  id: string;
  latitude: number;
  longitude: number;
  brightness: number;
  scan: number;
  track: number;
  acq_date: string;
  acq_time: string;
  satellite: string;
  instrument: string;
  confidence: string;
  version: string;
  bright_t31?: number | null;
  frp: number;
  daynight: 'D' | 'N';
  source_type: SourceType;
  risk_score: number;
  risk_level: RiskLevel;
  is_anomaly: boolean;
  cluster_id?: string | null;
  cluster_size?: number;
  nearest_place?: string | null;
  last_updated: string;
}

export interface HotspotsResponse {
  items: Hotspot[];
  total: number;
  page: number;
  page_size: number;
  data_mode: DataMode;
  generated_at: string;
}

export interface GeospatialContext {
  land_cover: string;
  nearest_infrastructure?: string | null;
  distance_to_infrastructure_meters?: number | null;
  nearest_settlement?: string | null;
  distance_to_settlement_meters?: number | null;
  is_protected_area: boolean;
  protected_area_name?: string | null;
  elevation_meters?: number | null;
  slope_degrees?: number | null;
  fuel_load_estimate?: string;
}

export interface WeatherContext {
  temperature_celsius: number;
  relative_humidity_percent: number;
  wind_speed_kmh: number;
  wind_gust_kmh?: number | null;
  wind_direction_degrees: number;
  wind_direction_cardinal: string;
  precipitation_mm: number;
  fire_weather_index?: number | null;
  forecast_summary: string;
}

export interface HistoricalContext {
  prior_detections_30d: number;
  prior_detections_90d: number;
  is_recurrent_site: boolean;
  recurrent_pattern?: string;
  first_detected_date?: string | null;
  detection_frequency_score: number;
}

export interface TimelineEvent {
  timestamp: string;
  event_type: string;
  summary: string;
  details?: Record<string, any> | null;
}

export interface ClassificationResult {
  predicted_source: SourceType;
  confidence: number;
  probabilities: Record<string, number>;
  feature_importance?: Record<string, number> | null;
}

export interface AnomalyResult {
  is_anomaly: boolean;
  anomaly_score: number;
  baseline_deviation: number;
  anomaly_rationale: string;
}

export interface RiskAssessment {
  risk_score: number;
  risk_level: RiskLevel;
  frp_component: number;
  weather_component: number;
  proximity_component: number;
  historical_component: number;
  explainable_factors: RiskFactor[];
  recommended_action: string;
}

export interface IntelligenceResult {
  hotspot_id: string;
  classification: ClassificationResult;
  anomaly: AnomalyResult;
  risk: RiskAssessment;
  model_version: string;
  evaluated_at: string;
}

export interface IncidentDetail {
  hotspot: Hotspot;
  geospatial: GeospatialContext;
  weather: WeatherContext;
  historical: HistoricalContext;
  intelligence: IntelligenceResult;
  timeline: TimelineEvent[];
  data_mode: DataMode;
}

export interface SourceBreakdown {
  source_type: SourceType;
  display_name: string;
  count: number;
  percentage: number;
  average_frp: number;
  average_risk: number;
  primary_driver: string;
}

export interface SourcesResponse {
  sources: SourceBreakdown[];
  total_evaluated: number;
  dominant_source: SourceType;
  data_mode: DataMode;
  generated_at: string;
}

export interface SummaryResponse {
  total_active_hotspots: number;
  critical_risk_count: number;
  high_risk_count: number;
  medium_risk_count: number;
  low_risk_count: number;
  active_alerts_count: number;
  average_frp: number;
  max_frp: number;
  average_risk_score: number;
  data_mode: DataMode;
  last_sync_time: string;
  dominant_source: SourceType;
  source_counts: Record<string, number>;
  recent_critical_hotspots: Hotspot[];
}

export interface Alert {
  id: string;
  hotspot_id: string;
  severity: AlertSeverity;
  title: string;
  message: string;
  risk_score: number;
  location_name: string;
  latitude: number;
  longitude: number;
  timestamp: string;
  is_acknowledged: boolean;
  recommended_action: string;
  tags: string[];
}

export interface AlertsResponse {
  items: Alert[];
  total: number;
  unread_count: number;
  generated_at: string;
}

export interface RefreshRequest {
  force_sample?: boolean;
  bbox?: number[];
  days?: number;
}

export interface RefreshResponse {
  status: string;
  message: string;
  ingested_count: number;
  data_mode: DataMode;
  timestamp: string;
  execution_time_seconds: number;
}

export interface HotspotFilterParams {
  risk_level?: RiskLevel;
  source_type?: SourceType;
  min_frp?: number;
  min_confidence?: string;
  is_anomaly?: boolean;
  cluster_id?: string;
  page?: number;
  page_size?: number;
}
