"""Synthetic verified orders for isolated tests; never calls a payment gateway."""
import uuid
import app

def grant(owner=1,tenant=1,count=5,environment='live',state='fulfilled'):
 orders=[]
 with app.connect() as c:
  for _ in range(count):
   oid=str(uuid.uuid4());orders.append(oid)
   c.execute('INSERT INTO market_orders(id,tenant_id,owner,product_id,name,service_code,amount,currency,gateway,environment,request_key,state,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(oid,tenant,owner,'tax-analyst-session','Synthetic session','tax_analyst_session',500,'USD','stripe',environment,str(uuid.uuid4()),state,1))
   c.execute('INSERT INTO market_services(order_id,tenant_id,service_code,name,environment,status,activated) VALUES(?,?,?,?,?,?,?)',(oid,tenant,'tax_analyst_session','Synthetic session',environment,'active' if environment=='live' else 'test_active',1))
 return orders
