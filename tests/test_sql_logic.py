"""Optional DuckDB cross-check of portable relational logic; not a Databricks runtime test."""
import unittest
from pathlib import Path
import json
import re
from src.synthetic import generate, SCHEMAS
try:
    import duckdb
except ImportError:
    duckdb = None

@unittest.skipUnless(duckdb, 'Install duckdb for SQL cross-check')
class SqlLogicTests(unittest.TestCase):
    def test_gold_graph_and_evidence(self):
        db = duckdb.connect()
        for schema in ['cj_silver','cj_gold','cj_graph','cj_semantic']:
            db.execute(f'CREATE SCHEMA {schema}')
        tables, truth = generate()
        for name, rows in tables.items():
            db.execute(f'CREATE TABLE cj_silver.{name} ({SCHEMAS[name].replace("STRING","VARCHAR")})')
            columns = [part.strip().split()[0] for part in SCHEMAS[name].split(',')]
            unique = list({json.dumps(r,default=str,sort_keys=True):r for r in rows}.values())
            db.executemany(f'INSERT INTO cj_silver.{name} VALUES ({",".join("?" for _ in columns)})',[[r[c] for c in columns] for r in unique])
        root = Path(__file__).resolve().parents[1]
        for name in ['02_gold.sql','03_graph.sql','04_fallback.sql']:
            sql=(root/'sql'/name).read_text()
            sql=sql.replace(' USING DELTA','').replace('INTERVAL 15 MINUTES',"INTERVAL '15 MINUTES'")
            sql=sql.replace("split(node_id, ':')[0]", "split(node_id, ':')[1]")
            db.execute(sql)
        actual=dict(db.execute('SELECT opportunity_id,outcome FROM cj_gold.communication_outcomes').fetchall())
        expected={r['opportunity_id']:r['outcome'] for r in truth if r['outcome']!='INELIGIBLE'}
        self.assertEqual(actual,expected)
        findings=dict(db.execute('SELECT opportunity_id,finding FROM cj_gold.investigation').fetchall())
        self.assertEqual(findings,{r['opportunity_id']:r['expected_cause'] for r in truth if r['outcome']!='INELIGIBLE'})
        self.assertEqual(db.execute('SELECT COUNT(*) FROM cj_gold.investigation').fetchone()[0],10020)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM cj_graph.failure_paths').fetchone()[0],280)
        self.assertEqual(db.execute('SELECT expected_communications,sla_breaches,sla_breach_rate FROM cj_semantic.communication_kpis').fetchone(),(10000,500,0.05))
        db.close()
