# Build the Customer Journey POC step by step

This is a personal learning project for Databricks Free Edition using fictional data.
No cloud storage account, Kafka cluster, external graph database, OpenAI API key, Airflow,
or dbt installation is required. Python generates realistic source records directly.
The first version uses batch ingestion to keep the learning path small.

## What you will build

A telecom customer activates a plan and should receive a welcome SMS within 15 minutes.
Business users need to measure missed/late communications and inspect the recorded failure evidence.

- **Delta/medallion:** Bronze source rows, Silver deduplicated records, Gold communication outcomes.
- **Semantic layer:** approved measures in a Unity Catalog metric view.
- **Knowledge graph:** explicit customer/event/run/error/message/receipt nodes and edges, with source IDs.
- **Genie:** natural-language analytics over curated measures and evidence views.
- **MCP:** exposes Genie and three read-only investigation tools to an optional assistant.

The graph records operational relationships. It is not Genie's internal ontology.
A missing delivery receipt does not prove that an SMS was never received.
Evidence association is not universal causal proof.

## 0. Before you start (10 minutes)

1. Open your **Databricks Free Edition** workspace.
2. Open **Catalog** and identify an existing catalog where you can create schemas.
   It may be named `workspace`; use the actual name from your account.
3. Open **SQL Warehouses** and note your serverless warehouse ID from its details page.
4. Confirm you can create a Python notebook and run `print("hello")` on serverless compute.
5. Confirm Genie is visible. The UI may call the curated experience Genie Agents or Genie Spaces.
6. For the optional MCP stage, inspect **Unity Gateway → MCPs** and **Apps**.
   If these are unavailable, complete stages 1–6 first. Missing MCP access is a capability gate,
   not a reason to bypass authentication or claim that the full integration works.

Free Edition is quota-limited and non-commercial. Current documented limits include one 2X-Small
warehouse, five concurrent job tasks, and three Apps with automatic stop after 24 hours.
Use synthetic data only. This guide does not assume account-console access.

## 1. Get the project into Databricks (5 minutes)

Repository: https://github.com/yogesharya061/customer_journey_databricks

**Option A — Git folder:** Workspace → Create → Git folder; enter the repository URL and use `main`.
UI labels can vary. A public repo can also be downloaded without linking a Git account.

**Option B — notebook import:** On GitHub download the two files in `notebooks/`, or download the
repository ZIP and extract it. In Databricks use Workspace → Import and select the `.ipynb` files.
They are self-contained: imports from sibling project directories are not required.

Run them in order:

1. `notebooks/01_build_and_validate.ipynb`
2. `notebooks/02_metric_view.ipynb`

## 2. Generate source data and build the tables (10–20 minutes)

Open notebook 01. In the first code cell set:

```python
CATALOG = "workspace"  # Replace with your writable catalog name.
```

Select serverless compute and run all cells. No `%pip install` is needed.
The notebook sets Spark's session timezone to UTC and creates five `cj_*` schemas.
It overwrites only this POC's named tables. Do not point it at shared production schemas.

### What each cell does

| Stage | Code location | Result |
|---|---|---|
| Setup | First code cell | Catalog selection; five schemas |
| Source generator | Embedded from `src/synthetic.py` | Six lists of fictional source records |
| Bronze/Silver | Next cell | Raw Delta tables; exact duplicate removal; conflicting-key assertion |
| Gold | Embedded `sql/02_gold.sql` | One row per eligible event/campaign |
| Graph | Embedded `sql/03_graph.sql` | Nodes, edges, two-hop failure paths, conservative evidence view |
| Fallback metrics | Embedded `sql/04_fallback.sql` | Ordinary SQL KPI view |
| Validation | Final cells | Expected outcomes and graph integrity checks |

The generator is deterministic. To generate JSONL on your own laptop instead:

```bash
python src/synthetic.py --output data/generated
```

JSONL generation is optional; the notebook creates Spark DataFrames directly with explicit schemas.
`data/generated/` is ignored by Git. All identifiers are fictional; no phone numbers are needed.

### Expected source characteristics

- 10,040 customers/events: 10,000 mature eligible, 20 pending eligible, 20 ineligible.
- 100 initial processing failures followed by successful retries and on-time delivery.
- 25 additional callbacks with distinct receipt IDs for the same successful delivery.
- One exact duplicate row appended to each raw source table.
- One successful delivery exactly at the 15-minute boundary.
- Fixed cutoff: **2026-10-08 00:00:00 UTC**; snapshot: **demo_20261008**.

Do not replace the cutoff with `current_timestamp()` when following the demo: it changes pending outcomes.
To create a different snapshot, update the generator, SQL cutoffs, MCP snapshot, and tests together.
The test-only `cj_bronze.expected_outcomes` table is never an analytics or graph input.

### Expected checks

Notebook 01 must print:

```text
PASS: all outcome, evidence, retry, duplicate, graph and KPI checks
```

| Metric | Expected |
|---|---:|
| Gold rows including pending | 10,020 |
| Mature eligible communications | 10,000 |
| On time | 9,500 |
| Late | 200 |
| No confirmed delivery | 300 |
| Pending (excluded from SLA denominator) | 20 |
| SLA breaches | 500 |
| SLA breach rate | 0.05 = 5% |
| Raw graph failure paths | 280 |

The 280 paths comprise 100 recovered failures plus 180 unrecovered validation failures.
A graph error count is therefore **not** the missed-message count.

### Inspect the resulting data

In a SQL editor, replace the catalog and run:

```sql
USE CATALOG workspace;
SELECT outcome, COUNT(*) FROM cj_gold.communication_outcomes GROUP BY outcome;
SELECT outcome, finding, COUNT(*)
FROM cj_gold.investigation
WHERE outcome IN ('LATE','NO_CONFIRMED_DELIVERY')
GROUP BY outcome, finding;
```

Expected breach findings: late/UNKNOWN 200, unconfirmed/VALIDATION_FAILURE 180,
unconfirmed/PROVIDER_REJECTION 90, unconfirmed/UNKNOWN 30.
Late deliveries have no injected cause evidence, so their cause stays unknown.

## 3. Create the semantic layer (5 minutes)

Open notebook 02 and use the same `CATALOG`. Run all cells.
It creates `<catalog>.cj_semantic.communication_metrics` using metric-view YAML 1.1.
It then executes a query using `MEASURE(...)`; expected output is WELCOME / 10000 / 500 / 0.05.

Definitions:

- Expected communication: one eligible event/campaign pair whose deadline has passed.
- On time: first successful delivery at or before activation + 15 minutes.
- Late: first successful delivery after the deadline, observed by the cutoff.
- Unconfirmed: no successful delivery observed by the cutoff and deadline has passed.
- Pending: no delivery yet and deadline has not passed.
- SLA breach: late or unconfirmed; pending is excluded.
- Affected customers: distinct customers having a breach (not always equal to communication count).

If metric-view creation fails, read the error. Correct catalog privileges or SQL errors normally.
Only if the feature is unavailable, use `cj_semantic.communication_kpis` from notebook 01.
That is an ordinary SQL semantic fallback, **not** a Unity Catalog metric view.
Record this difference in your demo. Fallback has campaign totals, not all metric-view dimensions.

## 4. Create and test Genie (10–20 minutes)

### A. Metrics Genie Agent/Space

1. Open Genie and create a new curated Agent/Space named `Customer Communication Metrics`.
2. Select your SQL warehouse.
3. Add `<catalog>.cj_semantic.communication_metrics`.
   If metric views are unavailable, select `communication_kpis` instead.
4. Add descriptions and paste the instructions in `docs/GENIE_INSTRUCTIONS.md`.
5. Save and ask the benchmark questions in `docs/BENCHMARKS.md`.
6. Inspect the generated SQL and result—not only the prose answer.

Some workspaces restrict mixing metric views and ordinary views in one curated experience.
Use two Agents/Spaces in this guide to avoid relying on that capability.

### B. Investigation Genie Agent/Space

1. Create another named `Customer Communication Evidence`.
2. Add `<catalog>.cj_gold.investigation` and `<catalog>.cj_graph.failure_paths`.
3. Add the same instructions plus: `Use investigation for counts; failure_paths includes recovered failures.`
4. Ask: `What happened to C09701? Show the source record IDs.`
5. Expected: no confirmed delivery; MISSING_PHONE failure on R09701_1; graph evidence exists.
6. Ask about C00001: it had a temporary processing failure but recovered and delivered on time.

This is a useful core demo even before MCP. Genie queries SQL views; it is not itself executing
arbitrary graph algorithms. The failure_paths view performs an explicit two-hop graph join.

## 5. Schedule the data build (optional, 5 minutes)

1. Jobs & Pipelines → Create Job → name `customer-journey-demo-build`.
2. Add a notebook task pointing to notebook 01 with serverless compute.
3. Optionally add notebook 02 as a second task depending on task 1.
4. Run manually first. Confirm task success and notebook assertions.
5. Keep maximum concurrent runs at one. Avoid a recurring schedule until needed; save your quota.

Reruns replace this demo's snapshot. This is not CDC, incremental ingestion, or atomic multi-table publishing.
Stop the assistant during rebuilds. Production would publish versioned snapshots only after all checks pass.

## 6. Demo the graph without MCP (5 minutes)

```sql
USE CATALOG workspace;
SELECT * FROM cj_graph.failure_paths WHERE event_node='event:E09701';
SELECT * FROM cj_gold.investigation WHERE customer_id='C09701';
```

The path is event:E09701 → run:R09701_1 → error:MISSING_PHONE.
The investigator also checks the latest run, message attempts, and final delivery outcome.
A later successful processing run prevents an old failure from being used as the finding.

Checkpoint: you now have medallion data, a semantic layer, graph traversal, and Genie.
Continue to MCP only after the notebook assertions and Genie benchmark questions pass.

## 7. Prepare your laptop for MCP (10 minutes)

Use Python 3.12. The first runnable assistant is a terminal chat application on your laptop;
the graph MCP service is hosted on Databricks Apps. This avoids a second hosted UI app.
Install the Databricks CLI using the official instructions linked in SOURCES.md.
Authenticate via OAuth—do not put access tokens in source code.

```bash
git clone https://github.com/yogesharya061/customer_journey_databricks.git
cd customer_journey_databricks
python -m venv .venv
```

Activate on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Or macOS/Linux:

```bash
source .venv/bin/activate
```

Then:

```bash
pip install -r agent/requirements.txt
databricks auth login --host https://YOUR_WORKSPACE_HOST --profile DEFAULT
```

`mcp` is constrained to 1.x because these examples use the documented compatible API.
Other integration packages are not a fully locked environment. After a successful workspace smoke test,
save `pip freeze` to a local lock file if you need exact environment reproduction.

## 8. Check the actual Genie MCP endpoint (5–10 minutes)

In Unity Gateway → MCPs copy the URL for `system.ai.genie_one_mcp` if it is available.
Current documented shape:

```text
https://YOUR_WORKSPACE_HOST/ai-gateway/mcp-services/system.ai.genie_one_mcp
```

Run:

```bash
python agent/check_mcp.py --url "YOUR_GENIE_MCP_URL"
```

It should print tool names and JSON input schemas. Use the actual names and schemas to make a read-only
call with `--tool TOOL_NAME --args '{...}'`. Quote JSON appropriately for your shell; or use a Python
terminal. `genie_ask` starts an asynchronous response: poll with the returned conversation/response IDs
until complete, using the polling tool's discovered schema. A start response alone is not a completed answer.

Ask for measures from the full `<catalog>.cj_semantic.communication_metrics` name and the fixed snapshot.
Genie One is workspace-scoped; creating a curated Genie Space does not automatically bind this MCP to it.
Test whether the returned SQL uses the intended metric view. If not, refine semantic metadata/context.

A 401 is an authentication issue; a 403 is usually authorization; a 404 may indicate an unavailable
endpoint or incorrect URL. Check the workspace MCP UI and current official docs rather than guessing endpoints.
If this capability is unavailable in your Free Edition workspace, stop this stage and record it as blocked.
The core demo remains useful, but it is not a full Genie-through-MCP demonstration.

## 9. Deploy the graph MCP service (15–25 minutes)

1. Open Apps → Create custom app, or Unity Gateway → MCPs → Build a new MCP server.
2. Name it `mcp-customer-journey` (or another unused `mcp-` prefixed name).
3. Add a SQL warehouse resource with resource key **sql-warehouse** and grant **CAN USE**.
4. Find the app's service principal name in the app details.
5. Grant only the required demo access below. Substitute actual catalog and principal.

```sql
GRANT USE CATALOG ON CATALOG workspace TO `APP_SERVICE_PRINCIPAL`;
GRANT USE SCHEMA ON SCHEMA workspace.cj_gold TO `APP_SERVICE_PRINCIPAL`;
GRANT USE SCHEMA ON SCHEMA workspace.cj_graph TO `APP_SERVICE_PRINCIPAL`;
GRANT SELECT ON TABLE workspace.cj_gold.communication_outcomes TO `APP_SERVICE_PRINCIPAL`;
GRANT SELECT ON TABLE workspace.cj_gold.investigation TO `APP_SERVICE_PRINCIPAL`;
GRANT SELECT ON TABLE workspace.cj_graph.edges TO `APP_SERVICE_PRINCIPAL`;
```

The views run under their Databricks view permission semantics; their owner must retain access to
underlying source tables. Do not grant the test truth table to the app.

6. In the repository's `mcp_server/app.yaml`, set CJ_CATALOG to your catalog.
   `DATABRICKS_WAREHOUSE_ID` is resolved from resource key `sql-warehouse`.
7. Copy/sync **the contents of `mcp_server/`** to a workspace folder (server.py, requirements.txt, app.yaml).
   If using a Git folder, update the YAML in your working branch or copy the folder to a separate workspace path.
8. Click Deploy and select that folder as the app source. The app root must contain app.yaml.
9. Wait for Running. Copy the app URL and append `/mcp`.
10. Give your own user CAN USE on the app. Keep it restricted to yourself for this learning demo.

**Identity limitation:** the graph service queries as its app service principal.
Every app caller sees the same authorized synthetic dataset. It does NOT implement end-user row security.
Genie may query as the user, so only use this setup where both identities can access the entire same demo data.
Production needs deliberate on-behalf-of authorization or server-enforced tenant restrictions.

Smoke test from your laptop:

```bash
python agent/check_mcp.py --url "YOUR_GRAPH_APP_URL/mcp" --tool health
python agent/check_mcp.py --url "YOUR_GRAPH_APP_URL/mcp" --tool summarize_failure_evidence
```

The first tests the MCP process; the second tests warehouse authentication, grants, SQL, and data.
Use the printed schema to call `get_customer_journey` with C09701 and `explain_communication` with E09701:WELCOME.
Tool results include statement IDs, evidence rows, snapshot ID, and a truncation flag.
SQL is parameterized; identifiers come from validated configuration. There is no arbitrary-SQL tool.

For a local server test, set CJ_CATALOG and DATABRICKS_WAREHOUSE_ID as environment variables, install
`mcp_server/requirements.txt`, authenticate with the CLI, and run `python mcp_server/server.py`.
The local HTTP service has no application auth; keep it on your own machine and never expose it publicly.
Databricks Apps supplies the hosted authentication boundary.

## 10. Run the combined assistant (10 minutes)

Choose a **tool-calling capable** model endpoint visible in your Databricks workspace.
Do not assume that a particular model is available in Free Edition.
Set these environment variables on your laptop. PowerShell example:

```powershell
$env:GENIE_MCP_URL = "https://YOUR_WORKSPACE_HOST/ai-gateway/mcp-services/system.ai.genie_one_mcp"
$env:GRAPH_MCP_URL = "https://YOUR_APP_HOST/mcp"
$env:DATABRICKS_MODEL_ENDPOINT = "YOUR_AVAILABLE_TOOL_CALLING_ENDPOINT"
$env:CJ_METRIC_VIEW = "workspace.cj_semantic.communication_metrics"
python agent/chat.py
```

On macOS/Linux use `export NAME="value"` for each variable, then the same Python command.
The model client uses Databricks authentication; an OpenAI API key is not required.

Ask:

> For WELCOME at snapshot demo_20261008, what is the SLA breach rate and what recorded failure evidence explains the unconfirmed communications?

Expected: 5% total breach rate, 200 late, 300 unconfirmed; of the unconfirmed, 180 validation failures,
90 provider rejections and 30 unknown. The 200 late records also have unknown cause.
The printed trace must show both Genie and graph tool calls. A plausible answer without tool calls is not a pass.

Ask separately:

> Show the customer journey for C00001. Was its processing failure recovered?

Expected: initial TEMPORARY_ERROR, subsequent successful run, successful receipt, ON_TIME.

The assistant is intentionally single-turn per invocation, with a 20-turn tool-call cap.
It is a learning CLI, not a polished multi-user application. It does not resend messages or change data.
If managed Genie MCP is unavailable, do not substitute a fabricated response. Keep stage 10 blocked;
Genie UI plus the independently tested graph MCP is an explicitly partial integration.

## 11. Acceptance checklist

- [ ] Notebook assertions pass, including exact counts, retries, boundary and graph integrity.
- [ ] Metric view returns 10000 / 500 / 0.05 (or fallback explicitly recorded).
- [ ] Genie benchmarks return correct values and source SQL.
- [ ] Both MCP servers list tools and complete a real read-only call.
- [ ] Graph query results contain expected evidence and correct truncation status.
- [ ] Combined assistant uses both servers for the combined question.
- [ ] Unauthorized users cannot use the graph app; no real customer data is present.
- [ ] No passwords, tokens, or secrets are committed.

## Troubleshooting

| Symptom | Action |
|---|---|
| Catalog `workspace` missing | Set CATALOG to the actual writable catalog in both notebooks and CJ_CATALOG in app.yaml |
| Schema creation denied | Use a permitted catalog; do not try to override access controls |
| Quota exhausted | Wait for quota reset; avoid repeated full rebuilds and many model requests |
| Metric YAML unsupported | Check feature/runtime support; use documented ordinary-view fallback |
| Genie says 10,020 expected | It counted pending; correct instructions and inspect chosen view/SQL |
| Genie says 280 failures caused misses | It counted recovered graph paths; use investigation finding/outcome |
| App fails at startup | Check deployment logs, package install, source root, and app.yaml resource key |
| Graph tool gets SQL permission error | Check app service principal warehouse and catalog/schema/object grants |
| App stopped overnight | Restart; Free Edition apps automatically stop after 24 hours |
| Model does not call tools | Choose a tool-capable endpoint and inspect trace; do not call the demo validated |
| Genie endpoint missing | Record Free Edition capability gap; use a supported workspace for full integration |

## Cleanup and production boundaries

Stop the app and pause the job to conserve quota. Keep the Git source.
For data cleanup, remove only the named `cj_*` schemas after reviewing their contents; never drop the catalog.
No destructive cleanup command is executed by this project.

Production extensions: incremental event ingestion, event-time watermarking, versioned snapshot publication,
consent rules, eligibility history, campaign-specific SLAs, realistic multiple attempts/channels, per-user
security, data quality quarantine, tracing/monitoring, bounded graph exploration, and performance testing.
This small demo does not establish production scalability or causal root-cause accuracy.
