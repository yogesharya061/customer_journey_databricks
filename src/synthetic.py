"""Deterministic, fictional source events. Standard library only; all timestamps UTC."""
from datetime import datetime, timedelta
import json
from pathlib import Path

AS_OF = datetime(2026, 10, 8, 0, 0, 0)
SNAPSHOT = 'demo_20261008'
SCHEMAS = {
    'customers': 'customer_id STRING, region STRING, segment STRING',
    'activation_events': 'event_id STRING, customer_id STRING, event_ts TIMESTAMP, plan_id STRING',
    'campaign_eligibility': 'event_id STRING, campaign_id STRING, eligible BOOLEAN, rule_version STRING',
    'processing_runs': 'run_id STRING, event_id STRING, processed_ts TIMESTAMP, status STRING, error_code STRING',
    'message_attempts': 'message_id STRING, event_id STRING, campaign_id STRING, sent_ts TIMESTAMP, provider_status STRING',
    'delivery_receipts': 'receipt_id STRING, message_id STRING, delivered_ts TIMESTAMP, delivery_status STRING',
}
KEYS = dict(zip(SCHEMAS, ['customer_id', 'event_id', None, 'run_id', 'message_id', 'receipt_id']))

def generate():
    tables = {name: [] for name in SCHEMAS}
    truth = []
    for i in range(1, 10041):
        customer, event = f'C{i:05}', f'E{i:05}'
        ts = datetime(2026, 10, 1) + timedelta(seconds=(i * 53) % (7 * 86400))
        outcome, cause = 'ON_TIME', 'NOT_APPLICABLE'
        if 9501 <= i <= 9700:
            outcome, cause = 'LATE', 'UNKNOWN'
        elif 9701 <= i <= 9880:
            outcome, cause = 'NO_CONFIRMED_DELIVERY', 'VALIDATION_FAILURE'
        elif 9881 <= i <= 9970:
            outcome, cause = 'NO_CONFIRMED_DELIVERY', 'PROVIDER_REJECTION'
        elif 9971 <= i <= 10000:
            outcome, cause = 'NO_CONFIRMED_DELIVERY', 'UNKNOWN'
        elif 10001 <= i <= 10020:
            ts = AS_OF - timedelta(minutes=5)
            outcome, cause = 'PENDING', 'NOT_APPLICABLE'
        elif i > 10020:
            outcome, cause = 'INELIGIBLE', 'NOT_APPLICABLE'
        tables['customers'].append(dict(customer_id=customer, region=['North','South','East','West'][(i-1)%4], segment='PREPAID'))
        tables['activation_events'].append(dict(event_id=event, customer_id=customer, event_ts=ts, plan_id='PLAN_499'))
        tables['campaign_eligibility'].append(dict(event_id=event, campaign_id='WELCOME', eligible=outcome!='INELIGIBLE', rule_version='v1'))
        truth.append(dict(opportunity_id=f'{event}:WELCOME', customer_id=customer, outcome=outcome, expected_cause=cause))
        if outcome in ('PENDING','INELIGIBLE'):
            continue
        # First 100 recover from a failure; must not be counted as missed.
        if i <= 100:
            tables['processing_runs'].append(dict(run_id=f'R{i:05}_0', event_id=event, processed_ts=ts+timedelta(minutes=1), status='FAILED', error_code='TEMPORARY_ERROR'))
        failed = cause == 'VALIDATION_FAILURE'
        tables['processing_runs'].append(dict(run_id=f'R{i:05}_1', event_id=event, processed_ts=ts+timedelta(minutes=2), status='FAILED' if failed else 'SUCCESS', error_code='MISSING_PHONE' if failed else None))
        if failed:
            continue
        message = f'M{i:05}_1'
        tables['message_attempts'].append(dict(message_id=message, event_id=event, campaign_id='WELCOME', sent_ts=ts+timedelta(minutes=3), provider_status='REJECTED' if cause=='PROVIDER_REJECTION' else 'ACCEPTED'))
        if outcome in ('ON_TIME','LATE'):
            delay = 30 if outcome=='LATE' else (15 if i==9500 else 5)
            receipt = dict(receipt_id=f'D{i:05}_1', message_id=message, delivered_ts=ts+timedelta(minutes=delay), delivery_status='DELIVERED')
            tables['delivery_receipts'].append(receipt)
            if i<=25:
                # Distinct callback ID for the same delivery; earliest delivery wins.
                tables['delivery_receipts'].append({**receipt, 'receipt_id': f'D{i:05}_2'})
    # Exact source duplicates exercise Silver de-duplication.
    for name in tables:
        tables[name].append(dict(tables[name][0]))
    return tables, truth

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='data/generated')
    args = parser.parse_args()
    target = Path(args.output)
    target.mkdir(parents=True, exist_ok=True)
    tables, truth = generate()
    for name, rows in {**tables, 'expected_outcomes': truth}.items():
        with (target / f'{name}.jsonl').open('w') as handle:
            for row in rows:
                handle.write(json.dumps(row, default=lambda x: x.isoformat()) + '\n')
    print({name: len(rows) for name, rows in tables.items()})
