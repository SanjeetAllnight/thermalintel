'use client';

import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import { Hotspot } from '../../types/api';
import { MapLegend } from './MapLegend';
import { Maximize2, Crosshair, Layers, Flame, Eye, EyeOff } from 'lucide-react';
import { getRiskLevelMeta, getSourceMeta } from '../../lib/formatters';

interface ThermalMapProps {
  hotspots: Hotspot[];
  selectedHotspotId: string | null;
  onSelectIncident: (id: string) => void;
  selectedRegion?: string;
}

type BasemapType = 'dark' | 'satellite' | 'topo';

export const ThermalMap: React.FC<ThermalMapProps> = ({
  hotspots,
  selectedHotspotId,
  onSelectIncident,
  selectedRegion,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const markersLayerRef = useRef<L.LayerGroup | null>(null);
  const halosLayerRef = useRef<L.LayerGroup | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);

  const [basemap, setBasemap] = useState<BasemapType>('dark');
  const [showHalos, setShowHalos] = useState<boolean>(true);
  const [mapReady, setMapReady] = useState<boolean>(false);

  // Basemap Tile URLs
  const basemapUrls: Record<BasemapType, { url: string; attribution: string }> = {
    dark: {
      url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
      attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; OpenStreetMap',
    },
    satellite: {
      url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      attribution: '&copy; Esri, Maxar, Earthstar Geographics',
    },
    topo: {
      url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
      attribution: '&copy; OpenTopoMap contributors',
    },
  };

  // Initialize Map
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    // Default center on California / Continental US active region
    const map = L.map(mapContainerRef.current, {
      center: [38.5, -121.5],
      zoom: 6,
      zoomControl: false,
      attributionControl: false,
    });

    // Add Zoom Control at top-right
    L.control
      .zoom({
        position: 'topright',
      })
      .addTo(map);

    // Initial tile layer
    const tileLayer = L.tileLayer(basemapUrls[basemap].url, {
      maxZoom: 19,
      subdomains: 'abcd',
    }).addTo(map);
    tileLayerRef.current = tileLayer;

    // Layers for markers and halos
    const halosLayer = L.layerGroup().addTo(map);
    const markersLayer = L.layerGroup().addTo(map);

    halosLayerRef.current = halosLayer;
    markersLayerRef.current = markersLayer;
    mapInstanceRef.current = map;
    setMapReady(true);

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Update Basemap Tiles
  useEffect(() => {
    if (!mapInstanceRef.current || !tileLayerRef.current) return;
    mapInstanceRef.current.removeLayer(tileLayerRef.current);

    const newTile = L.tileLayer(basemapUrls[basemap].url, {
      maxZoom: 19,
      subdomains: 'abcd',
    }).addTo(mapInstanceRef.current);

    tileLayerRef.current = newTile;
  }, [basemap]);

  // Update Markers & Halos when Hotspots change
  useEffect(() => {
    if (!mapInstanceRef.current || !markersLayerRef.current || !halosLayerRef.current) return;

    markersLayerRef.current.clearLayers();
    halosLayerRef.current.clearLayers();

    if (hotspots.length === 0) return;

    const bounds = L.latLngBounds([]);

    hotspots.forEach((h) => {
      const isSelected = h.id === selectedHotspotId;
      const meta = getRiskLevelMeta(h.risk_level);
      const sourceMeta = getSourceMeta(h.source_type);

      bounds.extend([h.latitude, h.longitude]);

      // 1. Draw Risk Halo Circle
      if (showHalos) {
        const radiusMeters = Math.max(1200, Math.min(8000, h.frp * 45));
        const halo = L.circle([h.latitude, h.longitude], {
          radius: radiusMeters,
          color: meta.fillHex,
          weight: isSelected ? 2 : 1,
          opacity: isSelected ? 0.8 : 0.4,
          fillColor: meta.fillHex,
          fillOpacity: isSelected ? 0.25 : 0.1,
          interactive: false,
        });
        halosLayerRef.current?.addLayer(halo);
      }

      // 2. Custom Marker Icon
      const markerSize = isSelected ? 28 : h.risk_level === 'critical' ? 22 : 18;
      const pulseHtml =
        h.risk_level === 'critical' || isSelected
          ? `<span class="absolute -inset-2 rounded-full ${
              isSelected ? 'bg-cyan-400/40 animate-ping' : 'bg-red-500/40 animate-ping'
            }"></span>`
          : '';

      const icon = L.divIcon({
        className: 'custom-thermal-marker',
        html: `
          <div class="relative flex items-center justify-center cursor-pointer transition-transform hover:scale-125" style="width: ${markerSize}px; height: ${markerSize}px;">
            ${pulseHtml}
            <div class="w-full h-full rounded-full border-2 ${
              isSelected ? 'border-cyan-300 ring-4 ring-cyan-500/50' : 'border-slate-900 shadow-md'
            } flex items-center justify-center font-bold text-[9px] text-white" style="background-color: ${
          meta.fillHex
        };">
              ${isSelected ? '★' : ''}
            </div>
          </div>
        `,
        iconSize: [markerSize, markerSize],
        iconAnchor: [markerSize / 2, markerSize / 2],
      });

      const marker = L.marker([h.latitude, h.longitude], { icon });

      // Interactive Popup
      const popupContent = document.createElement('div');
      popupContent.className = 'p-3 bg-slate-950 text-slate-100 rounded-lg border border-slate-800 font-sans min-w-[210px]';
      popupContent.innerHTML = `
        <div class="flex items-center justify-between gap-2 border-b border-slate-800 pb-1.5 mb-2">
          <span class="text-xs font-mono font-bold text-white">${h.id}</span>
          <span class="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style="background-color: ${meta.fillHex}33; color: ${meta.fillHex}; border: 1px solid ${meta.fillHex}66;">
            ${h.risk_level} (${Math.round(h.risk_score)})
          </span>
        </div>
        <div class="text-[11px] font-semibold text-slate-300 mb-1.5 line-clamp-2">
          ${h.nearest_place || 'Unclassified Territory'}
        </div>
        <div class="grid grid-cols-2 gap-1 text-[10px] text-slate-400 mb-2.5">
          <div>Source: <strong class="text-slate-200 capitalize">${sourceMeta.label}</strong></div>
          <div>FRP: <strong class="text-cyan-400">${h.frp.toFixed(1)} MW</strong></div>
          <div>Confidence: <strong class="text-slate-200 capitalize">${h.confidence}</strong></div>
          <div>Anomaly: <strong class="${h.is_anomaly ? 'text-red-400' : 'text-slate-400'}">${h.is_anomaly ? 'YES (Outlier)' : 'No'}</strong></div>
        </div>
        <button id="btn-inspect-${h.id}" class="w-full py-1.5 px-2 bg-red-600 hover:bg-red-500 active:scale-95 text-white text-xs font-semibold rounded shadow-md transition-all flex items-center justify-center gap-1 cursor-pointer">
          <span>Inspect Dossier</span> &rarr;
        </button>
      `;

      // Attach button click inside popup
      popupContent.querySelector(`#btn-inspect-${h.id}`)?.addEventListener('click', (e) => {
        e.stopPropagation();
        onSelectIncident(h.id);
      });

      marker.bindPopup(popupContent, {
        className: 'dark-leaflet-popup',
        closeButton: false,
        maxWidth: 260,
      });

      marker.on('click', () => {
        onSelectIncident(h.id);
      });

      markersLayerRef.current?.addLayer(marker);
    });

    // Auto-fit bounds on initial load if no specific incident is focused
    if (!selectedHotspotId && bounds.isValid()) {
      mapInstanceRef.current.fitBounds(bounds, {
        padding: [40, 40],
        maxZoom: 10,
      });
    }
  }, [hotspots, showHalos, selectedHotspotId]);

  // Handle Pan / Zoom to Selected Hotspot
  useEffect(() => {
    if (!mapInstanceRef.current || !selectedHotspotId) return;

    const target = hotspots.find((h) => h.id === selectedHotspotId);
    if (target) {
      mapInstanceRef.current.flyTo([target.latitude, target.longitude], 11, {
        duration: 1.2,
      });
    }
  }, [selectedHotspotId, hotspots]);

  // Fit all hotspots
  const handleFitAll = () => {
    if (!mapInstanceRef.current || hotspots.length === 0) return;
    const bounds = L.latLngBounds(hotspots.map((h) => [h.latitude, h.longitude]));
    if (bounds.isValid()) {
      mapInstanceRef.current.fitBounds(bounds, {
        padding: [50, 50],
        maxZoom: 10,
      });
    }
  };

  // Focus current selected hotspot
  const handleFocusSelected = () => {
    if (!mapInstanceRef.current) return;
    const target = hotspots.find((h) => h.id === selectedHotspotId) || hotspots[0];
    if (target) {
      mapInstanceRef.current.flyTo([target.latitude, target.longitude], 11, {
        duration: 1.0,
      });
    }
  };

  return (
    <div className="relative w-full h-full min-h-[480px] bg-slate-950 overflow-hidden select-none">
      {/* Map Surface */}
      <div ref={mapContainerRef} className="w-full h-full min-h-[480px] z-0" />

      {/* Floating Tactical Controls Toolbar (Top Left) */}
      <div className="absolute top-4 left-4 z-[400] flex flex-wrap items-center gap-2">
        {/* Basemap Switcher */}
        <div className="flex items-center rounded-lg bg-slate-950/90 backdrop-blur-md border border-slate-800 p-1 shadow-xl text-xs font-mono">
          <button
            type="button"
            onClick={() => setBasemap('dark')}
            className={`px-2.5 py-1 rounded transition-all ${
              basemap === 'dark' ? 'bg-slate-800 text-white font-bold' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Dark Vector
          </button>
          <button
            type="button"
            onClick={() => setBasemap('satellite')}
            className={`px-2.5 py-1 rounded transition-all ${
              basemap === 'satellite' ? 'bg-slate-800 text-white font-bold' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Satellite
          </button>
          <button
            type="button"
            onClick={() => setBasemap('topo')}
            className={`px-2.5 py-1 rounded transition-all ${
              basemap === 'topo' ? 'bg-slate-800 text-white font-bold' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Topo
          </button>
        </div>

        {/* Toggle Halos */}
        <button
          type="button"
          onClick={() => setShowHalos(!showHalos)}
          className={`flex items-center space-x-1.5 px-2.5 py-1.5 rounded-lg bg-slate-950/90 backdrop-blur-md border text-xs shadow-xl transition-all ${
            showHalos ? 'border-cyan-500/50 text-cyan-300' : 'border-slate-800 text-slate-400 hover:text-slate-200'
          }`}
          title="Toggle Thermal FRP Radiance Halos"
        >
          {showHalos ? <Eye className="w-3.5 h-3.5 text-cyan-400" /> : <EyeOff className="w-3.5 h-3.5" />}
          <span className="hidden sm:inline">FRP Halos</span>
        </button>

        {/* Reset / Fit All */}
        <button
          id="btn-map-fit-all"
          type="button"
          onClick={handleFitAll}
          className="flex items-center space-x-1 px-2.5 py-1.5 rounded-lg bg-slate-950/90 backdrop-blur-md border border-slate-800 hover:border-slate-700 text-slate-300 hover:text-white text-xs shadow-xl transition-all"
          title="Fit view to all active anomalies"
        >
          <Maximize2 className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Fit All</span>
        </button>

        {/* Center Target */}
        {selectedHotspotId && (
          <button
            id="btn-map-focus-target"
            type="button"
            onClick={handleFocusSelected}
            className="flex items-center space-x-1 px-2.5 py-1.5 rounded-lg bg-red-950/80 backdrop-blur-md border border-red-800 text-red-300 hover:text-white text-xs shadow-xl transition-all animate-pulse"
            title="Focus Selected Hotspot"
          >
            <Crosshair className="w-3.5 h-3.5 text-red-400" />
            <span>Target: {selectedHotspotId.split('-').pop()}</span>
          </button>
        )}
      </div>

      {/* Floating Tactical Legend (Bottom Left) */}
      <MapLegend />

      {/* Coordinates / Telemetry HUD Overlay (Bottom Right) */}
      <div className="absolute bottom-3 right-3 z-[400] pointer-events-none hidden sm:flex items-center space-x-3 text-[10px] font-mono text-slate-400 bg-slate-950/80 backdrop-blur px-2.5 py-1 rounded border border-slate-800/80">
        <span>SENSOR: VIIRS 375m NRT</span>
        <span className="text-slate-600">•</span>
        <span>PROJECTION: EPSG:3857</span>
        <span className="text-slate-600">•</span>
        <span className="text-emerald-400">FPS: 60 STABLE</span>
      </div>
    </div>
  );
};

export default ThermalMap;
