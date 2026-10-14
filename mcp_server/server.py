"""Read-only MCP service for synthetic data. App identity, NOT per-user row security."""
import os
import re
import time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem
from mcp.server.fastmcp import FastMCP

CATALOG = os.environ.get('CJ_CATALOG', 'workspace')
if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', CATALOG):
    raise ValueError('CJ_CATALOG must be a simple catalog identifier')
WAREHOUSE = os.environ.get('DATABRICKS_WAREHOUSE_ID', '')
SNAPSHOT = 'demo_20261008'
mcp = FastMCP('customer-journey', host='0.0.0.0',
              port=int(os.environ.get('DATABRICKS_APP_PORT', '8000')),
              stateless_http=True, json_response=True)

def query(statement, parameters=None):
    if not WAREHOUSE:
        raise ValueError('Set DATABRICKS_WAREHOUSE_ID')
    client = WorkspaceClient()
    params = [StatementParameterListItem(name=k, value=str(v), type='STRING')
              for k,v in (parameters or {}).items()]
    result = client.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE, statement=statement, parameters=params,
        wait_timeout='10s', row_limit=201)
    deadline = time.monotonic() + 60
    while result.status.state.value in ('PENDING','RUNNING'):
        if time.monotonic() >= deadline:
            client.statement_execution.cancel_execution(result.statement_id)
            raise TimeoutError('Warehouse query exceeded 60 seconds')
        time.sleep(1)
        result = client.statement_execution.get_statement(result.statement_id)
    if result.status.state.value != 'SUCCEEDED':
        # Details remain in workspace query history; do not leak internals to caller.
        raise RuntimeError(f'Query failed; inspect statement {result.statement_id}')
    columns = [c.name for c in result.manifest.schema.columns]
    rows = result.result.data_array or []
    truncated = bool(result.manifest.truncated) or len(rows)>200 or bool(result.result.next_chunk_index)
    return {'snapshot_id': SNAPSHOT, 'statement_id':result.statement_id,
            'rows':[dict(zip(columns,r)) for r in rows[:200]], 'truncated':truncated}

@mcp.tool()
def health() -> dict:
    """Check process health; does not test SQL authentication."""
    return {'status':'healthy','snapshot_id':SNAPSHOT}

@mcp.tool()
def get_customer_journey(customer_id: str) -> dict:
    """Return observed edges for a synthetic customer, bounded to this snapshot and 200 rows."""
    if not re.fullmatch(r'C\d{5}', customer_id):
        raise ValueError('Expected a synthetic customer ID such as C09701')
    sql = f'''WITH event_nodes AS (
      SELECT concat('event:',event_id) event_node
      FROM `{CATALOG}`.cj_gold.communication_outcomes
      WHERE customer_id=:customer AND snapshot_id=:snapshot
    ), runs_messages AS (
      SELECT e.dst_id FROM `{CATALOG}`.cj_graph.edges e
      JOIN event_nodes v ON e.src_id=v.event_node
      WHERE e.snapshot_id=:snapshot
    )
    SELECT src_id,relationship,dst_id,evidence_table,evidence_id,observed_at
    FROM `{CATALOG}`.cj_graph.edges
    WHERE snapshot_id=:snapshot AND (
      src_id=concat('customer:',:customer)
      OR src_id IN (SELECT event_node FROM event_nodes)
      OR src_id IN (SELECT dst_id FROM runs_messages))
    ORDER BY observed_at,src_id,dst_id LIMIT 201'''
    return query(sql, {'customer':customer_id,'snapshot':SNAPSHOT})

@mcp.tool()
def explain_communication(opportunity_id: str) -> dict:
    """Return outcome, conservative finding and record IDs; UNKNOWN means evidence is insufficient."""
    if not re.fullmatch(r'E\d{5}:WELCOME', opportunity_id):
        raise ValueError('Expected E09701:WELCOME')
    return query(f'''SELECT * FROM `{CATALOG}`.cj_gold.investigation
      WHERE opportunity_id=:opportunity AND snapshot_id=:snapshot LIMIT 201''',
      {'opportunity':opportunity_id,'snapshot':SNAPSHOT})

@mcp.tool()
def summarize_failure_evidence() -> dict:
    """Count all 500 SLA breaches by outcome and evidence finding in the fixed demo snapshot."""
    return query(f'''SELECT outcome,finding,count(*) communication_count
      FROM `{CATALOG}`.cj_gold.investigation
      WHERE snapshot_id=:snapshot AND outcome IN ('LATE','NO_CONFIRMED_DELIVERY')
      GROUP BY outcome,finding ORDER BY outcome,finding LIMIT 201''',{'snapshot':SNAPSHOT})

if __name__ == '__main__':
    mcp.run(transport='streamable-http')
