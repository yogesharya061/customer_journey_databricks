CREATE OR REPLACE VIEW cj_semantic.communication_metrics
WITH METRICS LANGUAGE YAML AS $$
version: 1.1
source: __CATALOG__.cj_gold.communication_outcomes
filter: outcome <> 'PENDING'
dimensions:
  - name: campaign
    expr: campaign_id
  - name: region
    expr: region
  - name: activation_date
    expr: DATE(activation_ts)
  - name: snapshot_id
    expr: snapshot_id
measures:
  - name: expected_communications
    expr: COUNT(*)
  - name: on_time_communications
    expr: SUM(CASE WHEN outcome = 'ON_TIME' THEN 1 ELSE 0 END)
  - name: late_communications
    expr: SUM(CASE WHEN outcome = 'LATE' THEN 1 ELSE 0 END)
  - name: unconfirmed_communications
    expr: SUM(CASE WHEN outcome = 'NO_CONFIRMED_DELIVERY' THEN 1 ELSE 0 END)
  - name: sla_breaches
    expr: SUM(CASE WHEN outcome IN ('LATE', 'NO_CONFIRMED_DELIVERY') THEN 1 ELSE 0 END)
  - name: sla_breach_rate
    expr: SUM(CASE WHEN outcome IN ('LATE', 'NO_CONFIRMED_DELIVERY') THEN 1.0 ELSE 0.0 END) / NULLIF(COUNT(*), 0)
  - name: affected_customers
    expr: COUNT(DISTINCT CASE WHEN outcome IN ('LATE', 'NO_CONFIRMED_DELIVERY') THEN customer_id END)
$$;
