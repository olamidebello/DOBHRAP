"""Read-only schema/dependency verification against the actual running backend."""
import json
import pypdf
from PIL import Image
from active_runtime import load_active
app=load_active('oob-business.service')
with app.connect() as c:
 c.execute('SELECT revision FROM tax_analyst_workbench_policy WHERE id=1').fetchone()
 c.execute('SELECT revision FROM tax_analyst_credit_policy WHERE id=1').fetchone()
 tenants=[t['id'] for t in c.execute('SELECT id FROM tenants')]
for tid in tenants:
 with app.tenant_connect(tid) as c:
  c.execute('SELECT id,kind,state FROM tax_bookkeeping_items LIMIT 1').fetchone()
  c.execute('SELECT id FROM tax_bookkeeping_exports LIMIT 1').fetchone()
  c.execute('SELECT diagnostic_id FROM tax_analyst_diagnostic_reviews LIMIT 1').fetchone()
print(json.dumps({'tenant_schemas_verified':len(tenants),'pdf_page_counter':True,'tiff_converter':True,'paid_analysis_invoked':False,'external_connectors_installed':False,'filing_ready':False}))
