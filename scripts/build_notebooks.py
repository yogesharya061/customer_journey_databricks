"""Package self-contained notebooks; no workspace-relative Python imports required."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
def code(s): return {'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':s.splitlines(True)}
def md(s): return {'cell_type':'markdown','metadata':{},'source':s.splitlines(True)}
config='''# Set this to an existing writable catalog from Catalog Explorer.
CATALOG = "workspace"
import re
assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", CATALOG)
spark.sql(f"USE CATALOG `{CATALOG}`")
spark.conf.set("spark.sql.session.timeZone", "UTC")
for schema in ["cj_bronze", "cj_silver", "cj_gold", "cj_graph", "cj_semantic"]:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{schema}`")
print("Catalog:", CATALOG)
'''
cells=[md('''# Customer Journey POC — run cells top to bottom
Synthetic learning data only. Requires serverless Python notebook and a writable Unity Catalog catalog.
This notebook overwrites only this project's `cj_*` demo tables. One fixed UTC snapshot;
not a production incremental pipeline. Do not run concurrently with the demo assistant.
Run `02_metric_view.ipynb` after this notebook, then follow `docs/BUILD_GUIDE.md` for Genie/MCP.
'''),md('## 1. Choose catalog and create schemas'),code(config),md('## 2. Generate source records (no installs required)')]
generator=(ROOT/'src/synthetic.py').read_text().split("if __name__ == '__main__':")[0]
cells.append(code(generator))
cells.append(code('''tables, truth = generate()
for name, rows in tables.items():
    df = spark.createDataFrame(rows, SCHEMAS[name])
    df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"cj_bronze.{name}")
    # Exact duplicates only. Real conflicting revisions require event/version ordering.
    silver = df.dropDuplicates()
    key = ["event_id", "campaign_id"] if name == "campaign_eligibility" else [KEYS[name]]
    assert silver.groupBy(*key).count().filter("count > 1").count() == 0, f"Conflicting keys in {name}"
    silver.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"cj_silver.{name}")
    print(name, len(rows), "raw rows")
# Truth is for testing only, never exposed to Genie or investigation logic.
spark.createDataFrame(truth).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("cj_bronze.expected_outcomes")
'''))
for title,file in [('3. Build one row per expected communication','02_gold.sql'),('4. Build graph and evidence view','03_graph.sql'),('5. Create fallback KPI view','04_fallback.sql')]:
    cells.append(md('## '+title))
    # Split known SQL statements at semicolon; no procedural SQL in these files.
    for statement in '\n'.join(line for line in (ROOT/'sql'/file).read_text().splitlines() if not line.lstrip().startswith('--')).split(';'):
        if statement.strip(): cells.append(code('spark.sql('+repr(statement.strip())+')'))
cells += [md('## 6. Verify outcomes, retries, evidence and graph integrity'),code('''from collections import Counter
outcomes = spark.table("cj_gold.communication_outcomes")
actual = {r.opportunity_id:r.outcome for r in outcomes.select("opportunity_id","outcome").collect()}
expected = {r["opportunity_id"]:r["outcome"] for r in truth if r["outcome"] != "INELIGIBLE"}
assert actual == expected
assert outcomes.count() == len(actual) == 10020
assert dict(Counter(actual.values())) == {"ON_TIME":9500,"LATE":200,"NO_CONFIRMED_DELIVERY":300,"PENDING":20}
assert actual["E00001:WELCOME"] == "ON_TIME"  # Recovered failure
assert actual["E09500:WELCOME"] == "ON_TIME"  # Exactly at SLA boundary
investigation = spark.table("cj_gold.investigation")
assert investigation.count() == 10020
findings = {r.opportunity_id:r.finding for r in investigation.select("opportunity_id","finding").collect()}
assert findings == {r["opportunity_id"]:r["expected_cause"] for r in truth if r["outcome"] != "INELIGIBLE"}
assert spark.sql("SELECT COUNT(*) n FROM cj_graph.failure_paths").first().n == 280
assert spark.sql("SELECT COUNT(*) n FROM cj_graph.edges e LEFT ANTI JOIN cj_graph.nodes n ON e.dst_id=n.node_id AND e.snapshot_id=n.snapshot_id").first().n == 0
kpi = spark.table("cj_semantic.communication_kpis").first()
assert kpi.expected_communications == 10000 and kpi.sla_breaches == 500
assert abs(float(kpi.sla_breach_rate)-0.05) < 1e-9
print("PASS: all outcome, evidence, retry, duplicate, graph and KPI checks")
display(spark.table("cj_semantic.communication_kpis"))
'''),md('## 7. Inspect example journey and findings'),code('''display(spark.sql("SELECT * FROM cj_gold.investigation WHERE customer_id IN ('C00001','C09701','C09881','C09971','C10001') ORDER BY customer_id"))
display(spark.sql("SELECT * FROM cj_graph.failure_paths WHERE event_node='event:E09701'"))
''')]
metric=[md('''# Semantic metric view
Run after notebook 01. Select the same catalog. If metric view creation fails due to feature availability,
use the KPI fallback already created by 01 and record that limitation. Do not suppress other SQL errors.
'''),code(config),code('spark.sql('+repr((ROOT/'sql/04_semantic.sql').read_text())+'.replace("__CATALOG__", CATALOG))'),code('''display(spark.sql("""SELECT campaign, MEASURE(expected_communications) expected,
 MEASURE(sla_breaches) breaches, MEASURE(sla_breach_rate) breach_rate
 FROM cj_semantic.communication_metrics GROUP BY campaign"""))
# Expected: WELCOME, 10000, 500, 0.05
''')]
for name,content in [('01_build_and_validate.ipynb',cells),('02_metric_view.ipynb',metric)]:
    notebook={'cells':content,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python','version':'3.12'}},'nbformat':4,'nbformat_minor':5}
    # Stable cell IDs for notebook format 4.5.
    for i,cell in enumerate(notebook['cells']): cell['id']=f'cell-{i:03}'
    serialized=json.dumps(notebook,indent=2)+'\n'
    path=ROOT/'notebooks'/name
    if '--check' in sys.argv:
        assert path.read_text()==serialized, f'Regenerate {name}'
        for cell in content:
            if cell['cell_type']=='code': compile(''.join(cell['source']),name,'exec')
    else: path.write_text(serialized)
