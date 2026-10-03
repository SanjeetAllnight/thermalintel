'use client';

import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import { Hotspot } from '../../types/api';
import { MapLegend } from './MapLegend';
import { Maximize2, Crosshair, Layers, Flame, Eye, EyeOff, Navigation, Radio } from 'lucide-react';
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
  const [cursorCoords, setCursorCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [currentZoom, setCurrentZoom] = useState<number>(6);

  // Basemap Tile URLs
  const cartoApiKey = process.env.NEXT_PUBLIC_CARTO_API_KEY ?? '';
  const cartoBaseUrl = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';
  const cartoDarkUrl = cartoApiKey
    ? `${cartoBaseUrl}?key=${cartoApiKey}`
    : cartoBaseUrl;

  const basemapUrls: Record<BasemapType, { url: string; attribution: string }> = {
    dark: {
      url: cartoDarkUrl,
      attribution:
        '&copy; <a href="https://carto.com/" target="_blank" rel="noopener">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
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

    // Event listeners for telemetry overlay
    map.on('mousemove', (e: L.LeafletMouseEvent) => {
      setCursorCoords({ lat: e.latlng.lat, lng: e.latlng.lng });
    });
    map.on('zoomend', () => {
      setCurrentZoom(map.getZoom());
    });

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
          opacity: isSelected ? 0.9 : 0.4,
          fillColor: meta.fillHex,
          fillOpacity: isSelected ? 0.3 : 0.12,
          interactive: false,
        });
        halosLayerRef.current?.addLayer(halo);
      }

      // 2. Custom Marker Icon with distinct severity symbols and high contrast
      const markerSize = isSelected ? 32 : h.risk_level === 'critical' ? 26 : 20;
      const pulseHtml =
        h.risk_level === 'critical' || isSelected
          ? `<span class="absolute -inset-2 rounded-full ${
              isSelected ? 'bg-cyber-cyan/50 motion-safe:animate-ping' : 'bg-red-500/40 motion-safe:animate-ping'
            }"></span>`
          : '';

      // Non-color symbol inside marker
      let symbol = '●';
      let shapeClass = 'rounded-full';
      if (h.risk_level === 'critical') {
        symbol = '!';
        shapeClass = 'rounded-full border-2 border-white ring-2 ring-red-600 shadow-[0_0_10px_rgba(255,51,102,0.8)]';
      } else if (h.risk_level === 'high') {
        symbol = '▲';
        shapeClass = 'rounded-md border border-white/80 shadow-[0_0_8px_rgba(255,107,0,0.6)]';
      } else if (h.risk_level === 'medium') {
        symbol = '■';
        shapeClass = 'rounded-sm border border-slate-900';
      } else {
        symbol = '–';
        shapeClass = 'rounded-full border border-slate-900';
      }

      if (isSelected) {
        symbol = '✛';
        shapeClass = 'rounded-full border-2 border-cyber-cyan ring-4 ring-cyber-cyan/60 shadow-[0_0_16px_rgba(0,212,255,0.9)]';
      }

      const icon = L.divIcon({
        className: 'custom-thermal-marker',
        html: `
          <div class="relative flex items-center justify-center cursor-pointer transition-transform hover:scale-125 select-none" style="width: ${markerSize}px; height: ${markerSize}px;">
            ${pulseHtml}
            <div class="w-full h-full ${shapeClass} flex items-center justify-center font-black font-mono text-[10px] text-white" style="background-color: ${
          isSelected ? '#00d4ff' : meta.fillHex
        };">
              ${symbol}
            </div>
          </div>
        `,
        iconSize: [markerSize, markerSize],
        iconAnchor: [markerSize / 2, markerSize / 2],
      });

      const marker = L.marker([h.latitude, h.longitude], { icon });

      // Interactive Popup
      const popupContent = document.createElement('div');
      popupContent.className = 'p-3 bg-void text-foreground rounded border border-cyber-border font-mono min-w-[220px] shadow-2xl';
      popupContent.innerHTML = `
        <div class="flex items-center justify-between gap-2 border-b border-cyber-border pb-1.5 mb-2">
          <span class="text-xs font-bold text-cyber-cyan">${h.id}</span>
          <span class="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded tracking-wider" style="background-color: ${meta.fillHex}33; color: ${meta.fillHex}; border: 1px solid ${meta.fillHex}66;">
            ${h.risk_level} (${Math.round(h.risk_score)})
          </span>
        </div>
        <div class="text-[11px] font-sans font-semibold text-slate-200 mb-1.5 line-clamp-2">
          ${h.nearest_place || 'Unclassified Territory'}
        </div>
        <div class="grid grid-cols-2 gap-1 text-[10px] text-subtle mb-2.5">
          <div>Source: <strong class="text-foreground capitalize">${sourceMeta.label}</strong></div>
          <div>FRP: <strong class="text-thermal-DEFAULT font-bold">${h.frp.toFixed(1)} MW</strong></div>
          <div>Confidence: <strong class="text-foreground capitalize">${h.confidence}</strong></div>
          <div>Anomaly: <strong class="${h.is_anomaly ? 'text-destructive' : 'text-subtle'}">${h.is_anomaly ? 'YES (Outlier)' : 'No'}</strong></div>
        </div>
        <button id="btn-inspect-${h.id}" class="w-full py-1.5 px-2 bg-thermal-DEFAULT hover:bg-thermal-bright active:scale-95 text-void font-bold text-xs rounded uppercase tracking-wider shadow-md transition-all flex items-center justify-center gap-1 cursor-pointer">
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
        maxWidth: 270,
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
    <div className="relative w-full h-full min-h-[480px] bg-void overflow-hidden select-none">
      {/* Map Surface */}
      <div ref={mapContainerRef} className="w-full h-full min-h-[480px] z-0" />

      {/* Floating Tactical Controls Toolbar (Top Left) */}
      <div className="absolute top-4 left-4 z-[400] flex flex-wrap items-center gap-2">
        {/* Basemap Switcher */}
        <div className="flex items-center cyber-chamfer-xs bg-void/90 backdrop-blur-md border border-cyber-border p-1 shadow-2xl text-xs font-mono">
          <button
            type="button"
            onClick={() => setBasemap('dark')}
            className={`px-2.5 py-1 rounded transition-all uppercase tracking-wider ${
              basemap === 'dark'
                ? 'bg-elevated text-cyber-cyan font-bold border border-cyber-cyan/40 shadow-[0_0_8px_rgba(0,212,255,0.2)]'
                : 'text-subtle hover:text-foreground'
            }`}
          >
            Dark Vector
          </button>
          <button
            type="button"
            onClick={() => setBasemap('satellite')}
            className={`px-2.5 py-1 rounded transition-all uppercase tracking-wider ${
              basemap === 'satellite'
                ? 'bg-elevated text-cyber-cyan font-bold border border-cyber-cyan/40 shadow-[0_0_8px_rgba(0,212,255,0.2)]'
                : 'text-subtle hover:text-foreground'
            }`}
          >
            Satellite
          </button>
          <button
            type="button"
            onClick={() => setBasemap('topo')}
            className={`px-2.5 py-1 rounded transition-all uppercase tracking-wider ${
              basemap === 'topo'
                ? 'bg-elevated text-cyber-cyan font-bold border border-cyber-cyan/40 shadow-[0_0_8px_rgba(0,212,255,0.2)]'
                : 'text-subtle hover:text-foreground'
            }`}
          >
            Topo
          </button>
        </div>

        {/* Toggle Halos */}
        <button
          type="button"
          onClick={() => setShowHalos(!showHalos)}
          className={`flex items-center space-x-1.5 px-2.5 py-1.5 cyber-chamfer-xs bg-void/90 backdrop-blur-md border text-xs shadow-xl transition-all font-mono uppercase tracking-wider ${
            showHalos
              ? 'border-thermal-DEFAULT/60 text-thermal-bright shadow-[0_0_8px_rgba(255,107,0,0.2)]'
              : 'border-cyber-border text-subtle hover:text-foreground'
          }`}
          title="Toggle Thermal FRP Radiance Halos"
        >
          {showHalos ? <Eye className="w-3.5 h-3.5 text-thermal-DEFAULT" /> : <EyeOff className="w-3.5 h-3.5" />}
          <span className="hidden sm:inline">FRP Halos</span>
        </button>

        {/* Reset / Fit All */}
        <button
          id="btn-map-fit-all"
          type="button"
          onClick={handleFitAll}
          className="flex items-center space-x-1 px-2.5 py-1.5 cyber-chamfer-xs bg-void/90 backdrop-blur-md border border-cyber-border hover:border-cyber-cyan/50 text-subtle hover:text-foreground text-xs font-mono uppercase tracking-wider shadow-xl transition-all"
          title="Fit view to all active anomalies"
        >
          <Maximize2 className="w-3.5 h-3.5 text-cyber-cyan" />
          <span className="hidden sm:inline">Fit All</span>
        </button>

        {/* Center Target */}
        {selectedHotspotId && (
          <button
            id="btn-map-focus-target"
            type="button"
            onClick={handleFocusSelected}
            className="flex items-center space-x-1.5 px-2.5 py-1.5 cyber-chamfer-xs bg-destructive/20 backdrop-blur-md border border-destructive/60 text-destructive hover:text-white text-xs font-mono uppercase tracking-wider shadow-[0_0_10px_rgba(255,51,102,0.4)] transition-all animate-pulse"
            title="Focus Selected Hotspot"
          >
            <Crosshair className="w-3.5 h-3.5 text-destructive" />
            <span>Target: {selectedHotspotId.split('-').pop()}</span>
          </button>
        )}
      </div>

      {/* Floating Tactical Legend (Bottom Left) */}
      <MapLegend />

      {/* Coordinates / Telemetry HUD Overlay (Bottom Right) */}
      <div className="absolute bottom-3 right-3 z-[400] pointer-events-none hidden sm:flex items-center space-x-3 text-[10px] font-mono text-subtle bg-void/90 backdrop-blur-md px-3 py-1.5 rounded border border-cyber-border/80 shadow-2xl">
        <div className="flex items-center space-x-1.5">
          <Navigation className="w-3 h-3 text-cyber-cyan" />
          <span>
            {cursorCoords
              ? `LAT: ${cursorCoords.lat.toFixed(4)}° | LON: ${cursorCoords.lng.toFixed(4)}°`
              : 'CURSOR: STANDBY'}
          </span>
        </div>
        <span className="text-cyber-border">•</span>
        <span>ZOOM: {currentZoom.toFixed(1)}x</span>
        <span className="text-cyber-border">•</span>
        <span>SENSOR: VIIRS 375m</span>
        <span className="text-cyber-border">•</span>
        <span className="text-cyber-accent font-bold">GRID: EPSG:3857</span>
      </div>
    </div>
  );
};

export default ThermalMap;
