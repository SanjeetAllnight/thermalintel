# Multi-Agent Development Playbook & Governance

## 1. Operating Architecture: 5-Agent Parallel Execution
To produce a verified prototype under tight deadlines, the project executes across five isolated git worktrees. The root directory is the **Integration Workspace**.

See [docs/FIVE_AGENT_OPERATING_MODEL.md](file:///home/sanjeet/.gemini/antigravity-ide/scratch/thermalintel/docs/FIVE_AGENT_OPERATING_MODEL.md) for full phase-by-phase deliverables.

| Phase & Agent | Git Branch | Isolated Worktree | Boundary Ownership |
|---|---|---|---|
| **Phase 1: Data Engine** | `phase-1-data` | `../thermalintel-agent1-data` | `services/api/ingestion/`<br>`services/api/repositories/`<br>`services/api/data/`<br>`data/sample/`<br>`data/cache/`<br>`scripts/data/` |
| **Phase 2: Enrichment** | `phase-2-enrichment` | `../thermalintel-agent2-enrichment` | `services/api/enrichment/`<br>`services/api/geospatial/`<br>`services/api/weather/`<br>`services/api/history/` |
| **Phase 3: Intelligence** | `phase-3-intelligence` | `../thermalintel-agent3-intelligence` | `services/intelligence/` |
| **Phase 4: Incident & Alert** | `phase-4-incidents` | `../thermalintel-agent4-incidents` | `services/api/incidents/`<br>`services/api/alerts/`<br>`services/api/summary/` |
| **Phase 5: Command Center UI** | `phase-5-ui` | `../thermalintel-agent5-ui` | `apps/web/` |

---

## 2. Frozen Contract Rule
The API contract defined in `docs/API_CONTRACT.md`, implemented in `services/api/schemas/`, and typed in `apps/web/src/types/api.ts` is **FROZEN**.

1. **No Field Deletions**: Existing fields must not be removed or renamed.
2. **No Signature Changes**: Path names (`/api/hotspots`, `/api/summary`, etc.) and HTTP methods (`GET`, `POST`) are immutable.
3. **No Uncoordinated Types**: Any emergency additive field must be documented and updated in both Python Pydantic models and TypeScript interfaces simultaneously.

---

## 3. Strict Boundary Rules
- **No Cross-Modification**: No agent may create, edit, or delete files belonging to another agent.
- **Standalone Implementations**: Agents must create modular service classes within their designated directories.
- **Merge Authority**: Merging into `main` is handled exclusively by the Integration Workspace.

---

## 4. Commands to Access Worktrees
```bash
# Agent 1 (Data Engine):
cd /home/sanjeet/.gemini/antigravity-ide/scratch/thermalintel-agent1-data

# Agent 2 (Geo/Environment Enrichment):
cd /home/sanjeet/.gemini/antigravity-ide/scratch/thermalintel-agent2-enrichment

# Agent 3 (Intelligence Engine):
cd /home/sanjeet/.gemini/antigravity-ide/scratch/thermalintel-agent3-intelligence

# Agent 4 (Incident + Alert Engine):
cd /home/sanjeet/.gemini/antigravity-ide/scratch/thermalintel-agent4-incidents

# Agent 5 (Command Center UI):
cd /home/sanjeet/.gemini/antigravity-ide/scratch/thermalintel-agent5-ui
```
