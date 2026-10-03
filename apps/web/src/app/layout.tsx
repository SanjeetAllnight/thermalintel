import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'ThermalIntel — Satellite Thermal Anomaly Intelligence',
  description: 'AI-assisted geospatial detection, classification, and explainable risk scoring of satellite thermal anomalies.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700;800&family=Orbitron:wght@600;700;800;900&display=swap"
        />
        <link
          rel="stylesheet"
          href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
          integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
          crossOrigin=""
        />
      </head>
      <body className="min-h-screen bg-void text-slate-100 antialiased font-sans selection:bg-thermal-orange selection:text-white overflow-x-hidden">
        {children}
      </body>
    </html>
  );
}
