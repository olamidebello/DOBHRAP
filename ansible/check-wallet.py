import json
from active_runtime import load_active
app=load_active('oob-business.service')
with app.connect() as c:
 c.execute('SELECT owner,currency,balance FROM wallet_accounts LIMIT 1').fetchone()
 c.execute('SELECT id FROM wallet_entries LIMIT 1').fetchone()
print(json.dumps({'wallet_schema_verified':True,'balances_changed':False,'purchases_made':False}))
