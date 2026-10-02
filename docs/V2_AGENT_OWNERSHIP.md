# ThermalIntel V2 Multi-Agent Ownership & File Boundaries

**Document Version:** 1.0.0  
**Status:** **ACTIVE & ENFORCED**  
**Base Commit:** `1e24976` (`feat(v2): establish domain contracts and database foundation`)  
**Main Integration Branch:** `v2`  
**Main Workspace:** `/home/sanjeet/.gemini/antigravity-ide/scratch/thermalintel`  
**Date:** October 2026  

---

## 1. Overview

To prevent race conditions, merge conflicts, and architectural drift during Phase 2–5 parallel development, strict physical and directory ownership boundaries are established. Seven specialized feature agents operate concurrently in isolated Git worktrees, coordinated solely by the **Main Integration Agent**.

---

## 2. Agent Worktrees & Ownership Matrix

| Agent | Branch | Worktree Directory | Primary Owned Paths | Forbidden Paths |
| :--- | :--- | :--- | :--- | :--- |
| **Agent A: Data Foundation** | `v2-data-foundation` | `.../thermalintel-agent-data-v2` | `services/api/ingestion/**`<br>`services/api/repositories/**`<br>`tests/test_firms_ingestion.py`<br>`tests/test_normalization.py`<br>`tests/test_repository.py` | `services/intelligence/**`<br>`services/api/incidents/**`<br>`apps/web/**`<br>`services/api/schemas/**` |
| **Agent B: Enrichment** | `v2-enrichment` | `.../thermalintel-agent-enrichment-v2` | `services/api/enrichment/**`<br>`services/api/geospatial/**`<br>`services/api/weather/**`<br>`services/api/history/**`<br>`tests/test_enrichment/**` | `services/api/ingestion/**`<br>`services/intelligence/**`<br>`apps/web/**`<br>`services/api/schemas/**` |
| **Agent C: Intelligence** | `v2-intelligence` | `.../thermalintel-agent-intelligence-v2` | `services/intelligence/**` | `services/api/ingestion/**`<br>`services/api/incidents/**`<br>`apps/web/**`<br>`services/api/schemas/**` |
| **Agent D: Incidents** | `v2-incidents` | `.../thermalintel-agent-incidents-v2` | `services/api/incidents/**`<br>`services/api/incidents/tests/**` | `services/intelligence/**`<br>`services/api/ingestion/**`<br>`apps/web/**`<br>`services/api/schemas/**` |
| **Agent E: Alerts / Ops** | `v2-alerts-ops` | `.../thermalintel-agent-alerts-ops-v2` | `services/api/alerts/**`<br>`services/api/summary/**`<br>`services/api/alerts/tests/**`<br>`services/api/summary/tests/**` | `services/api/incidents/**`<br>`services/intelligence/**`<br>`apps/web/**`<br>`services/api/schemas/**` |
| **Agent F: Frontend** | `v2-frontend` | `.../thermalintel-agent-frontend-v2` | `apps/web/**` | `services/**`<br>`data/**` (backend schemas or logic) |
| **Agent G: Replay / Eval** | `v2-replay-eval` | `.../thermalintel-agent-replay-eval-v2` | `services/replay/**`<br>`scenarios/**`<br>`evaluation/**` | `services/api/schemas/**`<br>`services/intelligence/**` (modifying models) |

*Note: Branch names use hyphenated prefixes (`v2-xxx`) to prevent Git directory/file ref conflicts with the base `v2` branch.*

---

## 3. Shared & Integration-Owned Files

The following files are **INTEGRATION-OWNED** and strictly managed by the Main Integration Agent:

- `services/api/schemas/**` (Canonical V1 and V2 domain schemas)
- `services/api/migrations/**` (SQLite numbered migration scripts and runner)
- `services/api/database.py` (Core database connection and lifespan handlers)
- `services/api/routers/api.py` (Top-level API route dispatch)
- `services/api/security.py` (CORS and mutation API key security gates)
- `docs/V2_CONTRACTS.md` (Frozen contract specification)
- `docs/V2_DATABASE.md` (Frozen database specification)
- `docs/V1_BASELINE.md` (V1 baseline documentation)
- `.env.example`, `.gitignore`, `requirements.txt`

### Contract Change Protocol
If any parallel agent discovers an indispensable requirement for schema modification:
1. **RFC Proposal:** The agent documents the proposed field/model modification in their local worktree.
2. **Review:** The Main Integration Agent evaluates cross-agent impact and backward compatibility.
3. **Canonical Update:** If approved, the Main Integration Agent updates `services/api/schemas/v2/` in the `v2` branch.
4. **Rebase Notification:** The updated contract is rebased/merged into all active parallel agent worktrees.
5. **No Silent Drift:** No agent may unilaterally alter files in `services/api/schemas/` or `services/api/migrations/`.

---

## 4. Detailed Agent Mandates & Boundaries

### 4.1 Agent A: Data Foundation (`v2-data-foundation`)
- **Primary Ownership:** `services/api/ingestion/**`, `services/api/repositories/**`
- **Scope & Deliverables:**
  - Robust NASA FIRMS ingestion with exponential backoff and timeout handling.
  - Recording `ProviderRun` execution telemetry into database without leaking credentials.
  - Storing raw provider response payloads to disk with `RawPayloadMetadata` tracking.
  - Parsing CSV into canonical `Observation` domain entities.
  - Strict UTC ISO 8601 timestamp handling (`acquisition_time_utc` vs `ingestion_time_utc`).
  - Quarantine mechanism for corrupt, unparseable, or out-of-bounds coordinates.
  - Database upsert operations via `hotspot_repository` (maintaining V1 compatibility).

### 4.2 Agent B: Enrichment (`v2-enrichment`)
- **Primary Ownership:** `services/api/enrichment/**`, `services/api/geospatial/**`, `services/api/weather/**`, `services/api/history/**`
- **Scope & Deliverables:**
  - Contextual enrichment with explicit `Provenance` tracking per source.
  - Geospatial context via OpenStreetMap Overpass (land cover, settlement distance, infrastructure, conservation zones).
  - Atmospheric weather parameters via Open-Meteo (temperature, humidity, wind vector, 24h rain, FWI).
  - Historical 30d/90d recurrence indexing within 1km radius.
  - Explicit unavailable value representation (`status='unavailable'`, `value=None`) without fabricating data.
  - Cache TTL management (`data/cache/`) to prevent rate-limit exhaustion.

### 4.3 Agent C: Intelligence (`v2-intelligence`)
- **Primary Ownership:** `services/intelligence/**`
- **Scope & Deliverables:**
  - Implementation of canonical `Assessment` generation.
  - Clear distinction between provider detection confidence, classification confidence, anomaly score, data quality score, and composite risk score.
  - Feature extraction and explainability factor generation (`RiskFactor`).
  - Input reproducibility: calculating SHA-256 `input_hash` and recording `algorithm_version`.
  - **Ethical Integrity Rule:** The baseline classifier is heuristic and rule-weighted. It must NOT be described as a trained neural or deep learning model unless real offline training and validation benchmarks are executed. Do NOT fabricate posterior probabilities.

### 4.4 Agent D: Incidents (`v2-incidents`)
- **Primary Ownership:** `services/api/incidents/**`
- **Scope & Deliverables:**
  - Correlation of `Observation` records into persistent `Incident` entities.
  - Enforcement of **Stable Identity Rule**: Incident ID remains permanent once minted (`INC-YYYYMMDD-XXXX`).
  - Managing `IncidentObservation` associative mappings (supporting N:M cluster relationships).
  - Generating immutable, append-only `IncidentEvent` timeline transitions (`created`, `observation_added`, `escalated`, `deescalated`, `merged`, `split`, `closed`).
  - Preservation of working clustering logic in `IncidentAggregator` without unnecessary rewrites.

### 4.5 Agent E: Alerts / Operations (`v2-alerts-ops`)
- **Primary Ownership:** `services/api/alerts/**`, `services/api/summary/**`
- **Scope & Deliverables:**
  - Transition-driven alert generation from incident state changes.
  - Deterministic deduplication using `dedupe_key` to suppress notification floods.
  - Alert lifecycle state transitions (`active` $\to$ `acknowledged` $\to$ `resolved`).
  - Summary KPI aggregation (`SummaryResponse`) for real-time operations dashboard.
  - Cooldown timers and acknowledgement persistence.

### 4.6 Agent F: Frontend Command Center (`v2-frontend`)
- **Primary Ownership:** `apps/web/**`
- **Scope & Deliverables:**
  - Command Center UI implementation in Next.js 14 / Tailwind CSS / Leaflet.
  - Incident-first operational workflow (interactive map, KPI telemetry bar, incident dossier modal, alert drawer).
  - Visualizing provenance, source health, and data freshness indicators.
  - Timeline progression display and historical replay controls.
  - Responsive layout, accessible controls (WCAG AA), and robust loading/empty/error states.
  - **Boundary Rule:** The frontend consumes API contracts. It must **never** independently compute authoritative risk scores or classifications.

### 4.7 Agent G: Replay / Evaluation (`v2-replay-eval`)
- **Primary Ownership:** `services/replay/**`, `scenarios/**`, `evaluation/**`
- **Scope & Deliverables:**
  - Virtual/injected clock mechanism allowing temporal step-through.
  - Deterministic replay engine for historical incidents and satellite passes.
  - Curated scenario packs (wildfires, industrial flares, agricultural burns, false positive noise).
  - Automated evaluation harness benchmarking classification precision/recall and risk scoring stability.

---

## 5. Test Ownership & Isolation

- Each agent owns unit and module tests within their primary directory (e.g. `services/intelligence/tests/**`).
- Shared regression suites (`tests/test_api_endpoints.py`, `tests/test_v1_baseline_snapshot.py`, `tests/test_security.py`, `tests/test_v2_migrations.py`, `tests/test_v2_contracts.py`, `tests/test_v2_database.py`) are integration-owned.
- An agent's feature changes MUST NOT break any shared regression test.
