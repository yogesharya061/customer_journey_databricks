-- Executed after USE CATALOG in the notebook. Fixed UTC snapshot, current demo only.
CREATE OR REPLACE TABLE cj_gold.communication_outcomes USING DELTA AS
WITH first_delivery AS (
  SELECT m.event_id, m.campaign_id, MIN(r.delivered_ts) AS first_delivered_ts
  FROM cj_silver.message_attempts m
  JOIN cj_silver.delivery_receipts r ON m.message_id = r.message_id
  WHERE r.delivery_status = 'DELIVERED'
    AND r.delivered_ts <= TIMESTAMP '2026-10-08 00:00:00'
    AND m.sent_ts <= TIMESTAMP '2026-10-08 00:00:00'
  GROUP BY m.event_id, m.campaign_id
)
SELECT concat(e.event_id, ':', q.campaign_id) AS opportunity_id,
 e.customer_id, e.event_id, q.campaign_id, c.region, c.segment,
 e.event_ts AS activation_ts, e.event_ts + INTERVAL 15 MINUTES AS deadline_ts,
 d.first_delivered_ts,
 CASE
   WHEN d.first_delivered_ts <= e.event_ts + INTERVAL 15 MINUTES THEN 'ON_TIME'
   WHEN d.first_delivered_ts IS NOT NULL THEN 'LATE'
   WHEN e.event_ts + INTERVAL 15 MINUTES > TIMESTAMP '2026-10-08 00:00:00' THEN 'PENDING'
   ELSE 'NO_CONFIRMED_DELIVERY'
 END AS outcome,
 'demo_20261008' AS snapshot_id,
 TIMESTAMP '2026-10-08 00:00:00' AS analysis_as_of_ts
FROM cj_silver.activation_events e
JOIN cj_silver.customers c ON e.customer_id = c.customer_id
JOIN cj_silver.campaign_eligibility q ON e.event_id = q.event_id AND q.eligible = true
LEFT JOIN first_delivery d ON e.event_id = d.event_id AND q.campaign_id = d.campaign_id
WHERE e.event_ts <= TIMESTAMP '2026-10-08 00:00:00';
