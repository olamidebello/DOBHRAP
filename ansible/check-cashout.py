import json
from active_runtime import load_active
app=load_active('oob-business.service')
with app.connect() as c:
 for table in ('cashout_settings','cashout_funds','cashout_authorizations','cashout_requests'):
  c.execute('SELECT * FROM '+table+' LIMIT 0')
 enabled=bool(c.execute('SELECT enabled FROM cashout_settings WHERE id=1').fetchone()[0])
print(json.dumps({'schema_verified':True,'requests_enabled':enabled,'mode':'manual','transfers_initiated':False,'balances_changed':False}))
