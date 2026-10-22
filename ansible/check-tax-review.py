"""Read-only readiness checks using the running service's actual backend."""
import json
from active_runtime import load_active
app=load_active('oob-business.service')
with app.connect() as c:tenants=[r['id'] for r in c.execute('SELECT id FROM tenants')]
for tid in tenants:
 with app.tenant_connect(tid) as c:c.execute('SELECT owner,year,revision FROM tax_analyst_cases LIMIT 1').fetchone()
print(json.dumps({'tenant_review_schemas_verified':len(tenants),'paid_analysis_invoked':False,'filing_ready':False}))
