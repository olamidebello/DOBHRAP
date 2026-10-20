"""Verify the actual live backend, without keys, names or document payloads."""
import json
from active_runtime import load_active
app=load_active('oob-business.service')
with app.connect() as c:
 c.execute('SELECT revision FROM tax_analyst_controls WHERE id=1').fetchone()
 offer=c.execute("SELECT amount,currency FROM market_products WHERE id='tax-analyst-session'").fetchone()
 c.execute('SELECT order_id FROM tax_analyst_sessions LIMIT 1').fetchone()
 if not offer or offer['currency']!='USD':raise SystemExit('Analyst session offer is not configured in USD')
 tenants=[r['id'] for r in c.execute('SELECT id FROM tenants')]
for tid in tenants:
 with app.tenant_connect(tid) as c:c.execute('SELECT id FROM tax_filing_cases LIMIT 1').fetchone()
print(json.dumps({'tenant_schemas_verified':len(tenants),'analyst_controls':True,'filing_ready':False,'analyst_session_price_cents':offer['amount']}))
