import unittest
from collections import Counter
from datetime import timedelta
from src.synthetic import generate, AS_OF

class DataTests(unittest.TestCase):
    def test_outcomes_from_source_evidence(self):
        tables, truth = generate()
        events = {r['event_id']:r for r in tables['activation_events']}
        messages = {r['message_id']:r for r in tables['message_attempts']}
        first = {}
        for receipt in tables['delivery_receipts']:
            if receipt['delivery_status'] != 'DELIVERED' or receipt['delivered_ts']>AS_OF:
                continue
            message = messages[receipt['message_id']]
            key = message['event_id']+':'+message['campaign_id']
            first[key] = min(first.get(key,receipt['delivered_ts']),receipt['delivered_ts'])
        actual = {}
        for decision in tables['campaign_eligibility']:
            if not decision['eligible']: continue
            event = events[decision['event_id']]
            key = event['event_id']+':'+decision['campaign_id']
            deadline = event['event_ts']+timedelta(minutes=15)
            delivery = first.get(key)
            actual[key] = ('ON_TIME' if delivery<=deadline else 'LATE') if delivery else ('PENDING' if deadline>AS_OF else 'NO_CONFIRMED_DELIVERY')
        expected = {r['opportunity_id']:r['outcome'] for r in truth if r['outcome']!='INELIGIBLE'}
        self.assertEqual(actual,expected)
        self.assertEqual(Counter(actual.values()), {'ON_TIME':9500,'LATE':200,'NO_CONFIRMED_DELIVERY':300,'PENDING':20})
        self.assertEqual(actual['E00001:WELCOME'],'ON_TIME')
        self.assertEqual(actual['E09500:WELCOME'],'ON_TIME')

if __name__=='__main__': unittest.main()
