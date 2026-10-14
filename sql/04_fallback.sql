-- Explicit fallback if metric views are unavailable. Do not claim this is a metric view.
CREATE OR REPLACE VIEW cj_semantic.communication_kpis AS
SELECT campaign_id, snapshot_id,
 count(*) expected_communications,
 sum(CASE WHEN outcome='ON_TIME' THEN 1 ELSE 0 END) on_time_communications,
 sum(CASE WHEN outcome='LATE' THEN 1 ELSE 0 END) late_communications,
 sum(CASE WHEN outcome='NO_CONFIRMED_DELIVERY' THEN 1 ELSE 0 END) unconfirmed_communications,
 sum(CASE WHEN outcome IN ('LATE','NO_CONFIRMED_DELIVERY') THEN 1 ELSE 0 END) sla_breaches,
 sum(CASE WHEN outcome IN ('LATE','NO_CONFIRMED_DELIVERY') THEN 1.0 ELSE 0.0 END)/NULLIF(count(*),0) sla_breach_rate
FROM cj_gold.communication_outcomes WHERE outcome<>'PENDING'
GROUP BY campaign_id,snapshot_id;
