'use client';

import React, { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { Hotspot } from '../../types/api';
import { Radar } from 'lucide-react';

interface MapContainerProps {
  hotspots: Hotspot[];
  selectedHotspotId: string | null;
  onSelectIncident: (id: string) => void;
  selectedRegion?: string;
}

const DynamicThermalMap = dynamic(() => import('./ThermalMap'), {
  ssr: false,
});

export const MapContainer: React.FC<MapContainerProps> = (props) => {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <div className="w-full h-full min-h-[480px] flex flex-col items-center justify-center bg-slate-950 text-slate-400 p-8 text-center space-y-3">
        <div className="relative flex items-center justify-center w-16 h-16 rounded-full bg-slate-900 border border-slate-800">
          <Radar className="w-8 h-8 text-cyan-400 animate-spin" />
          <span className="absolute inset-0 rounded-full border border-cyan-500/20 animate-ping" />
        </div>
        <div className="text-sm font-semibold text-slate-200">
          Initializing Geospatial Intelligence Engine...
        </div>
        <p className="text-xs text-slate-500 max-w-sm">
          Binding Leaflet GIS raster projection and satellite orbital pass layers.
        </p>
      </div>
    );
  }

  return <DynamicThermalMap {...props} />;
};

export default MapContainer;
