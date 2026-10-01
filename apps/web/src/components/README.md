# ThermalIntel UI Components Guide (for `agent-ui`)

This directory is reserved for `agent-ui` modular React components.

### Recommended Component Breakdown
1. **`Map/`**
   - `ThermalMap.tsx`: Dynamic Leaflet map client component (using `next/dynamic` with `ssr: false`).
   - `HotspotClusterLayer.tsx`: Marker clustering or heat layer based on FRP and risk level.
   - `MapControls.tsx`: Layer toggles (Satellite base, OpenStreetMap, Heatmap layer, Cluster layer).
2. **`Incidents/`**
   - `IncidentList.tsx`: Scrollable list of active incidents with search and filter badges.
   - `IncidentCard.tsx`: Compact incident item with risk severity badge, FRP badge, source badge.
   - `IncidentFilters.tsx`: Filter bar (Risk level: Critical/High/Med/Low; Source: Wildfire/Industrial/Agri; Min FRP slider).
   - `IncidentDetailDrawer.tsx`: Slide-over or modal inspector displaying full `IncidentDetail`:
     - Geospatial proximity (settlement, infrastructure, protected area)
     - Weather gauges (wind speed, wind direction arrow, relative humidity, temp)
     - Historical recurrence timeline
     - Explainable risk factors with progress bars / weights
     - Recommended action banner
3. **`Analytics/`**
   - `RiskDistributionChart.tsx`: Recharts donut or bar chart of risk levels.
   - `SourceBreakdownChart.tsx`: Recharts horizontal bar chart of source types.
   - `FRPDistributionHistogram.tsx`: FRP intensity distribution.
4. **`Alerts/`**
   - `AlertsBanner.tsx`: Ticker / dismissable alert list for critical severity incidents.
   - `AlertModal.tsx`: Urgent response advisory modal.
