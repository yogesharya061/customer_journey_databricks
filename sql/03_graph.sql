CREATE OR REPLACE TABLE cj_graph.edges USING DELTA AS
SELECT concat('customer:', customer_id) src_id, 'TRIGGERED' relationship,
 concat('event:', event_id) dst_id, 'activation_events' evidence_table, event_id evidence_id,
 event_ts observed_at, 'demo_20261008' snapshot_id
FROM cj_silver.activation_events WHERE event_ts <= TIMESTAMP '2026-10-08 00:00:00'
UNION ALL
SELECT concat('event:',event_id), 'PROCESSED_BY', concat('run:',run_id),
 'processing_runs',run_id,processed_ts,'demo_20261008'
FROM cj_silver.processing_runs WHERE processed_ts <= TIMESTAMP '2026-10-08 00:00:00'
UNION ALL
SELECT concat('run:',run_id), 'FAILED_WITH', concat('error:',error_code),
 'processing_runs',run_id,processed_ts,'demo_20261008'
FROM cj_silver.processing_runs WHERE status='FAILED' AND processed_ts <= TIMESTAMP '2026-10-08 00:00:00'
UNION ALL
SELECT concat('event:',event_id), 'GENERATED', concat('message:',message_id),
 'message_attempts',message_id,sent_ts,'demo_20261008'
FROM cj_silver.message_attempts WHERE sent_ts <= TIMESTAMP '2026-10-08 00:00:00'
UNION ALL
SELECT concat('message:',message_id), 'HAS_RECEIPT', concat('receipt:',receipt_id),
 'delivery_receipts',receipt_id,delivered_ts,'demo_20261008'
FROM cj_silver.delivery_receipts WHERE delivered_ts <= TIMESTAMP '2026-10-08 00:00:00';

CREATE OR REPLACE TABLE cj_graph.nodes USING DELTA AS
SELECT node_id, split(node_id, ':')[0] node_type, snapshot_id
FROM (
 SELECT src_id node_id, snapshot_id FROM cj_graph.edges
 UNION
 SELECT dst_id node_id, snapshot_id FROM cj_graph.edges
);

-- True two-hop graph traversal, not an LLM inference.
CREATE OR REPLACE VIEW cj_graph.failure_paths AS
SELECT a.src_id event_node, a.dst_id run_node, b.dst_id error_node,
 b.evidence_id, b.observed_at, a.snapshot_id
FROM cj_graph.edges a JOIN cj_graph.edges b
 ON a.dst_id=b.src_id AND a.snapshot_id=b.snapshot_id
WHERE a.relationship='PROCESSED_BY' AND b.relationship='FAILED_WITH';

-- One row per opportunity; later success prevents false failure attribution.
CREATE OR REPLACE VIEW cj_gold.investigation AS
WITH latest_run AS (
 SELECT *, row_number() OVER (PARTITION BY event_id ORDER BY processed_ts DESC, run_id DESC) rn
 FROM cj_silver.processing_runs WHERE processed_ts <= TIMESTAMP '2026-10-08 00:00:00'
), latest_message AS (
 SELECT *, row_number() OVER (PARTITION BY event_id,campaign_id ORDER BY sent_ts DESC,message_id DESC) rn
 FROM cj_silver.message_attempts WHERE sent_ts <= TIMESTAMP '2026-10-08 00:00:00'
)
SELECT o.*, r.run_id latest_run_id, r.status latest_run_status, r.error_code,
 m.message_id latest_message_id, m.provider_status,
 p.error_node, p.evidence_id graph_evidence_id,
 CASE
 WHEN o.outcome IN ('ON_TIME','PENDING') THEN 'NOT_APPLICABLE'
 WHEN o.outcome='NO_CONFIRMED_DELIVERY' AND r.status='FAILED'
      AND p.error_node='error:MISSING_PHONE' AND m.message_id IS NULL THEN 'VALIDATION_FAILURE'
 WHEN o.outcome='NO_CONFIRMED_DELIVERY' AND m.provider_status='REJECTED' THEN 'PROVIDER_REJECTION'
 ELSE 'UNKNOWN' END finding
FROM cj_gold.communication_outcomes o
LEFT JOIN latest_run r ON o.event_id=r.event_id AND r.rn=1
LEFT JOIN latest_message m ON o.event_id=m.event_id AND o.campaign_id=m.campaign_id AND m.rn=1
LEFT JOIN cj_graph.failure_paths p ON p.event_node=concat('event:',o.event_id)
 AND p.evidence_id=r.run_id AND p.snapshot_id=o.snapshot_id;
