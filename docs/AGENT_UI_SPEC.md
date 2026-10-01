# Specification for `agent-ui` (Frontend Web Application)

**Ownership Zone**: `apps/web/`  
**Strict Prohibition**: Do NOT touch `services/api/` or `services/intelligence/`!

---

## Mission Objectives
1. Build an interactive **Leaflet Geospatial Map** showing satellite thermal anomalies.
2. Implement **Hotspot Clustering** and color-coded risk markers (Red: Critical, Orange: High, Amber: Medium, Slate: Low).
3. Build the **Incident Feed & Filters** (filter by risk severity, thermal source, minimum FRP, text search).
4. Build the **Incident Detail Drawer** with deep-dive inspection:
   - Geospatial proximity badges (infrastructure, settlement distance, protected areas)
   - Environmental weather dials (wind speed, wind direction arrow, humidity, temperature)
   - Historical satellite pass timeline
   - **Explainable AI Factors card**: visual weights, impact tags, and operational recommendations
5. Build the **Analytics Dashboard** using Recharts (risk distribution donut, thermal source breakdown horizontal bar chart).
6. Render the **Active Alerts banner / feed** with priority badges and mitigation guidance.
7. Support **Live vs. Demo mode indication** in the navigation header with manual sync button.

---

## Pre-Wired Assets Ready to Use
- **TypeScript Types**: `apps/web/src/types/api.ts` (100% frozen and aligned with backend).
- **Typed API Client**: `apps/web/src/lib/api-client.ts` (`apiClient.getHealth()`, `apiClient.getHotspots()`, `apiClient.getHotspotDetail(id)`, `apiClient.getSummary()`, `apiClient.getAlerts()`, `apiClient.getSources()`, `apiClient.refreshData()`).
- **Leaflet CSS**: Pre-loaded in `apps/web/src/app/layout.tsx`.
- **Target Containers**: Pre-defined in `apps/web/src/app/page.tsx` (`#map-container`, `#incident-list-container`, `#incident-detail-drawer`, `#analytics-charts-container`).

---

## Technical Notes & Best Practices
- **Dynamic Leaflet Import**: Next.js App Router requires Leaflet components to be dynamically imported with `ssr: false` to avoid `window is not defined` errors during server rendering:
  ```tsx
  const ThermalMap = dynamic(() => import('@/components/Map/ThermalMap'), {
    ssr: false,
    loading: () => <div className="h-full flex items-center justify-center text-xs text-slate-500">Loading Geospatial Engine...</div>
  });
  ```
- Use Tailwind dark-mode palette (`bg-slate-900`, `border-slate-800`, `text-slate-100`).
- Ensure all interactive elements have unique, descriptive IDs for automated testing.

---

## Acceptance Criteria
- [ ] Clicking a hotspot card or map marker opens the Incident Detail Drawer with full geospatial, weather, and explainable AI factors.
- [ ] Filter controls dynamically filter the hotspot list and map markers without page reload.
- [ ] Recharts graphs visualize source distribution and risk severity accurately.
- [ ] No changes made outside `apps/web/`.
