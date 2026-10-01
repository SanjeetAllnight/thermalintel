# ThermalIntel Web Frontend (`apps/web`)

Owned exclusively by **`agent-ui`**.

## Tech Stack
- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- Leaflet (Dynamic import with `ssr: false`)
- Recharts (Analytics visualization)
- Lucide React (Icons)

## Running Locally
```bash
cd apps/web
npm install
npm run dev
```
The web dashboard will be available at `http://localhost:3000`.

## Key Integration Files
- `src/types/api.ts`: Frozen TypeScript contracts matching backend Pydantic models.
- `src/lib/api-client.ts`: Pre-wired typed API client for all 7 endpoints.
- `src/app/page.tsx`: Foundation dashboard shell with designated target containers.
- `src/components/README.md`: Component layout guide.
