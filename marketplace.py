"""Hosted checkout and durable fulfillment of platform service offers.
No card data is collected. Browser redirects never establish payment success.
"""
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError
import advanced as a


def initialize(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS market_products (
      id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL,service_code TEXT NOT NULL,
      amount INTEGER NOT NULL,currency TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS market_orders (
      id TEXT PRIMARY KEY,tenant_id INTEGER NOT NULL,owner INTEGER NOT NULL,product_id TEXT NOT NULL,
      name TEXT NOT NULL,service_code TEXT NOT NULL,amount INTEGER NOT NULL,currency TEXT NOT NULL,
      gateway TEXT NOT NULL,environment TEXT NOT NULL,request_key TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'creating',provider_id TEXT UNIQUE,checkout_url TEXT,
      created INTEGER NOT NULL,next_check INTEGER NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT '',
      UNIQUE(tenant_id,owner,request_key));
    CREATE TABLE IF NOT EXISTS market_events (
      id TEXT PRIMARY KEY,gateway TEXT NOT NULL,order_id TEXT NOT NULL,created INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS market_services (
      order_id TEXT PRIMARY KEY,tenant_id INTEGER NOT NULL,service_code TEXT NOT NULL,
      name TEXT NOT NULL,environment TEXT NOT NULL,status TEXT NOT NULL,
      work_state TEXT NOT NULL DEFAULT 'new',activated INTEGER NOT NULL);
    ''')


def enabled():return os.environ.get('DOBHRAP_ENABLE_MARKETPLACE')=='1'
def environment():
    env=os.environ.get('PAYMENTS_ENV','test')
    if env not in ('test','live'):raise a.ServiceError('Invalid payment environment',503)
    if env=='live' and os.environ.get('DOBHRAP_ENABLE_LIVE_PAYMENTS')!='1':raise a.ServiceError('Live payments are disabled',503)
    return env


def key(gateway):
    if gateway not in ('stripe','paystack'):raise a.ServiceError('Unsupported payment gateway')
    env=environment();secret=os.environ.get(gateway.upper()+'_SECRET_KEY','')
    if not secret.startswith('sk_'+env+'_'):raise a.ServiceError('Configure the selected gateway key for this payment environment',503)
    return secret


def readiness():
    gateways=[]
    for gateway,currency in [('stripe','USD'),('paystack','NGN')]:
        try:key(gateway);configured=enabled()
        except a.ServiceError:configured=False
        gateways.append({'id':gateway,'currency':currency,'configured':configured,
                         'signing_key_configured':bool(os.environ.get('STRIPE_WEBHOOK_SECRET')) if gateway=='stripe' else configured})
    return {'enabled':enabled(),'environment':os.environ.get('PAYMENTS_ENV','test'),'gateways':gateways,
            'notice':'One-time platform service offers. Test purchases create test service records. No recurring billing or reseller payouts.'}


def base_url():
    url=os.environ.get('MARKETPLACE_PUBLIC_URL','https://olamideolatayobello.com').rstrip('/')
    parsed=urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        raise a.ServiceError('Configure the HTTPS marketplace origin',503)
    return url


def provider(gateway,path,payload=None,idempotency=None):
    secret=key(gateway)
    if gateway=='paystack':
        return a.request_json('https://api.paystack.co'+path,payload,{'Authorization':'Bearer '+secret},'POST' if payload is not None else 'GET')
    # Stripe's API accepts form-encoded values; paths are constructed only by this module.
    headers={'Authorization':'Bearer '+secret,'Content-Type':'application/x-www-form-urlencoded','Stripe-Version':'2024-06-20'}
    if idempotency:headers['Idempotency-Key']=idempotency
    req=Request('https://api.stripe.com/v1'+path,data=urlencode(payload).encode() if payload is not None else None,headers=headers)
    try:
        with build_opener(a.NoRedirect).open(req,timeout=30) as response:
            raw=response.read(1_000_001)
            if len(raw)>1_000_000:raise a.ServiceError('Payment provider response too large',502)
            return json.loads(raw)
    except (HTTPError,URLError,TimeoutError,ValueError,OSError):
        raise a.ServiceError('Payment provider unavailable. Reconcile this order before starting another purchase.',502) from None


def checkout_url(value,gateway):
    parsed=urlsplit(str(value))
    if parsed.scheme!='https' or parsed.hostname!=('checkout.stripe.com' if gateway=='stripe' else 'checkout.paystack.com') or parsed.username or parsed.password or parsed.port not in (None,443):
        raise a.ServiceError('Unexpected checkout address',502)
    return value


def checkout(c,body,user,tenant_id):
    if not enabled():raise a.ServiceError('Marketplace checkout is disabled',503)
    gateway=body.get('gateway');key(gateway);env=environment()
    request_key=str(uuid.UUID(str(body.get('request_key',''))))
    product=c.execute('SELECT * FROM market_products WHERE id=? AND active=1',(body.get('product_id'),)).fetchone()
    if not product:raise a.ServiceError('Offer not available',404)
    if product['currency']!=('USD' if gateway=='stripe' else 'NGN'):raise a.ServiceError('Choose a gateway matching the offer currency')
    now=int(time.time());c.execute('BEGIN IMMEDIATE')
    order=c.execute('SELECT * FROM market_orders WHERE tenant_id=? AND owner=? AND request_key=?',(tenant_id,user['id'],request_key)).fetchone()
    if order:
        if order['product_id']!=product['id'] or order['gateway']!=gateway or order['environment']!=env:raise a.ServiceError('Purchase request already belongs to another order',409)
        if order['checkout_url'] and order['state']=='pending':return {'id':order['id'],'url':order['checkout_url']}
        if order['state'] not in ('creating','checkout_error'):return {'id':order['id'],'state':order['state']}
        if order['gateway']=='stripe' and not order['provider_id'] and now-order['created']>23*3600:raise a.ServiceError('Old checkout outcome is uncertain; reconcile the original payment in Stripe before creating another order',409)
        if order['state']=='creating' and order['next_check']>now:raise a.ServiceError('Checkout is being prepared. Check the order before retrying.',409)
    else:
        oid=str(uuid.uuid4())
        c.execute('INSERT INTO market_orders(id,tenant_id,owner,product_id,name,service_code,amount,currency,gateway,environment,request_key,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                  (oid,tenant_id,user['id'],product['id'],product['name'],product['service_code'],product['amount'],product['currency'],gateway,env,request_key,now))
        order=c.execute('SELECT * FROM market_orders WHERE id=?',(oid,)).fetchone()
    c.execute("UPDATE market_orders SET state='creating',next_check=? WHERE id=?",(now+90,order['id']));c.commit()
    try:
        origin=base_url();return_url=origin+'/?market_order='+order['id']
        if gateway=='stripe':
            result=provider('stripe','/checkout/sessions',{'mode':'payment','success_url':return_url,'cancel_url':return_url,
               'client_reference_id':order['id'],'metadata[order_id]':order['id'],
               'line_items[0][price_data][currency]':order['currency'].lower(),
               'line_items[0][price_data][unit_amount]':order['amount'],
               'line_items[0][price_data][product_data][name]':order['name'],'line_items[0][quantity]':1},idempotency=order['id'])
            pid=a.identifier(result['id'],'cs_');url=checkout_url(result['url'],gateway)
        else:
            result=provider('paystack','/transaction/initialize',{'email':user['email'],'reference':order['id'],'amount':order['amount'],
               'currency':order['currency'],'callback_url':return_url,'metadata':{'order_id':order['id']}})
            if result.get('status') is not True:raise a.ServiceError('Checkout was not initialized',502)
            data=result['data'];pid=str(data['reference'])
            if pid!=order['id']:raise a.ServiceError('Provider reference mismatch',502)
            url=checkout_url(data['authorization_url'],gateway)
        c.execute("UPDATE market_orders SET provider_id=?,checkout_url=?,state='pending',error='',next_check=? WHERE id=?",(pid,url,now+60,order['id']))
        a.audit(c,user['id'],'Marketplace checkout created '+order['id'])
        return {'id':order['id'],'url':url}
    except Exception:
        c.rollback();c.execute("UPDATE market_orders SET state='checkout_error',error=?,next_check=? WHERE id=?",('Checkout outcome unconfirmed. Verify this order before retrying.',now+300,order['id']));c.commit()
        raise a.ServiceError('Checkout outcome unconfirmed. Open Orders and verify before retrying.',502) from None


def verify(c,order_id):
    row=c.execute('SELECT * FROM market_orders WHERE id=?',(order_id,)).fetchone()
    if not row:raise a.ServiceError('Order not found',404)
    if row['state'] in ('fulfilled','test_fulfilled','payment_review'):return {'id':row['id'],'state':row['state']}
    if row['environment']!=environment():raise a.ServiceError('Order uses a different payment environment',409)
    if row['gateway']=='stripe':
        if not row['provider_id']:return {'id':row['id'],'state':row['state']}
        data=provider('stripe','/checkout/sessions/'+a.identifier(row['provider_id'],'cs_'))
        paid=data.get('payment_status')=='paid';amount=data.get('amount_total');currency=data.get('currency','').upper()
        matches=(data.get('id')==row['provider_id'] and data.get('client_reference_id')==row['id'] and data.get('metadata',{}).get('order_id')==row['id'] and data.get('livemode') is (row['environment']=='live'))
    else:
        result=provider('paystack','/transaction/verify/'+a.identifier(row['id']))
        data=result.get('data',{});paid=result.get('status') is True and data.get('status')=='success';amount=data.get('amount');currency=data.get('currency','').upper()
        matches=(data.get('reference')==row['id'] and data.get('domain')==row['environment'])
    if not paid:
        c.execute('UPDATE market_orders SET next_check=?,error=? WHERE id=?',(int(time.time())+900,'Payment not confirmed; no service activated.',row['id']))
        return {'id':row['id'],'state':row['state']}
    if not matches or type(amount) is not int or amount!=row['amount'] or currency!=row['currency']:
        raise a.ServiceError('Payment reference, environment, amount or currency mismatch. Manual reconciliation required.',409)
    if not c.in_transaction:c.execute('BEGIN IMMEDIATE')
    tenant=c.execute('SELECT status FROM tenants WHERE id=?',(row['tenant_id'],)).fetchone()
    if not tenant or tenant['status']!='active':raise a.ServiceError('Workspace suspended; paid order awaits fulfillment',409)
    # One central DB transaction atomically records both payment confirmation and the purchased service.
    state='fulfilled' if row['environment']=='live' else 'test_fulfilled'
    c.execute('INSERT OR IGNORE INTO market_services(order_id,tenant_id,service_code,name,environment,status,activated) VALUES(?,?,?,?,?,?,?)',
              (row['id'],row['tenant_id'],row['service_code'],row['name'],row['environment'],'active' if row['environment']=='live' else 'test_active',int(time.time())))
    updated=c.execute("UPDATE market_orders SET state=?,error='',next_check=0 WHERE id=? AND state NOT IN ('fulfilled','test_fulfilled','payment_review')",(state,row['id'])).rowcount
    if updated:a.audit(c,0,'Marketplace payment verified and service activated '+row['id'])
    return {'id':row['id'],'state':state}


def webhook(c,gateway,raw,headers):
    secret=key(gateway)
    if not enabled():raise a.ServiceError('Marketplace disabled',503)
    if gateway=='stripe':
        signing=os.environ.get('STRIPE_WEBHOOK_SECRET','')
        if not signing:raise a.ServiceError('Stripe webhook secret not configured',503)
        parts=[x.split('=',1) for x in headers.get('Stripe-Signature','').split(',') if '=' in x]
        stamp=next((v for k,v in parts if k=='t'),'0')
        try:fresh=abs(int(time.time())-int(stamp))<=300
        except ValueError:fresh=False
        expected=hmac.new(signing.encode(),stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
        if not fresh or not any(k=='v1' and hmac.compare_digest(v,expected) for k,v in parts):raise a.ServiceError('Invalid webhook signature',400)
    else:
        expected=hmac.new(secret.encode(),raw,hashlib.sha512).hexdigest()
        if not hmac.compare_digest(headers.get('x-paystack-signature',''),expected):raise a.ServiceError('Invalid webhook signature',400)
    event=json.loads(raw)
    if not isinstance(event,dict):raise a.ServiceError('Invalid webhook payload')
    if gateway=='stripe':
        if event.get('type') not in ('checkout.session.completed','checkout.session.async_payment_succeeded','checkout.session.expired'):return {'received':True}
        data=event.get('data',{}).get('object',{});oid=data.get('client_reference_id');pid=data.get('id');eid='stripe:'+a.identifier(event.get('id'),'evt_')
        if event.get('livemode') is not (environment()=='live'):raise a.ServiceError('Webhook environment mismatch',400)
    else:
        if event.get('event')!='charge.success':return {'received':True}
        data=event.get('data',{});oid=data.get('reference');pid=oid;eid='paystack:'+hashlib.sha256(raw).hexdigest()
    row=c.execute('SELECT * FROM market_orders WHERE id=? AND gateway=?',(oid,gateway)).fetchone()
    if not row:return {'received':True}  # Other apps may share the merchant account.
    if row['environment']!=environment():raise a.ServiceError('Webhook environment mismatch',400)
    if row['provider_id'] and row['provider_id']!=pid:raise a.ServiceError('Webhook order mismatch',400)
    if not row['provider_id'] and gateway=='stripe':
        c.execute('UPDATE market_orders SET provider_id=? WHERE id=?',(a.identifier(pid,'cs_'),oid))
    inserted=c.execute('INSERT OR IGNORE INTO market_events VALUES(?,?,?,?)',(eid,gateway,oid,int(time.time()))).rowcount
    if inserted and row['state'] not in ('fulfilled','test_fulfilled','payment_review'):
        c.execute('UPDATE market_orders SET next_check=0 WHERE id=?',(oid,))
    return {'received':True}


def dispatch(path,method,body,c,user,tenant_id):
    if not path.startswith('/api/market/'):return None
    route=path[len('/api/market/'):];admin=user['role']=='super_admin'
    if route=='status' and method=='GET':
        state=readiness()
        if admin:
            for gateway in state['gateways']:
                gateway['last_signed_event']=c.execute('SELECT max(created) FROM market_events WHERE gateway=?',(gateway['id'],)).fetchone()[0]
        return state
    if route=='products':
        if method=='GET':return [dict(r) for r in c.execute('SELECT * FROM market_products'+('' if admin else ' WHERE active=1')+' ORDER BY name')]
        if not admin:raise a.ServiceError('Super administrator required',403)
        if body.get('action')=='archive':
            if c.execute('UPDATE market_products SET active=0 WHERE id=?',(body.get('id'),)).rowcount!=1:raise a.ServiceError('Offer not found',404)
            a.audit(c,user['id'],'Marketplace offer archived '+str(body['id']));return {'ok':True}
        name=str(body.get('name','')).strip();description=str(body.get('description','')).strip();code=str(body.get('service_code',''))
        amount=body.get('amount');currency=str(body.get('currency','')).upper()
        if not name or len(name)>120 or len(description)>2000 or not re.fullmatch('[a-z][a-z0-9_]{1,59}',code):raise a.ServiceError('Enter an offer name, description and valid service code')
        if type(amount) is not int or not 50<=amount<=100_000_000 or currency not in ('USD','NGN'):raise a.ServiceError('Price must be 50–100000000 minor units in USD or NGN')
        if not isinstance(body.get('active'),bool):raise a.ServiceError('Choose whether the offer is active')
        pid=body.get('id') or str(uuid.uuid4())
        c.execute('INSERT INTO market_products VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,description=excluded.description,service_code=excluded.service_code,amount=excluded.amount,currency=excluded.currency,active=excluded.active',
                  (pid,name,description,code,amount,currency,int(body['active'])))
        a.audit(c,user['id'],'Marketplace offer saved '+pid);return {'id':pid}
    if route in ('orders','services') and method=='GET':
        table='market_orders' if route=='orders' else 'market_services'
        fields='id,tenant_id,owner,product_id,name,amount,currency,gateway,environment,state,created,error' if route=='orders' else '*'
        return [dict(r) for r in c.execute('SELECT '+fields+' FROM '+table+('' if admin else ' WHERE tenant_id=?')+' ORDER BY rowid DESC LIMIT 500',() if admin else (tenant_id,))]
    if route=='service-action' and method=='POST':
        if not admin:raise a.ServiceError('Super administrator required',403)
        if body.get('work_state') not in ('new','in_progress','completed','suspended'):raise a.ServiceError('Invalid fulfillment state')
        if not c.execute('SELECT 1 FROM market_services WHERE order_id=?',(body.get('order_id'),)).fetchone():raise a.ServiceError('Service not found',404)
        c.execute('UPDATE market_services SET work_state=?,status=CASE WHEN ?=\'suspended\' THEN \'suspended\' ELSE CASE WHEN environment=\'live\' THEN \'active\' ELSE \'test_active\' END END WHERE order_id=?',(body['work_state'],body['work_state'],body.get('order_id')))
        a.audit(c,user['id'],'Marketplace fulfillment updated '+str(body.get('order_id')));return {'ok':True}
    if user['role'] not in ('admin','super_admin'):raise a.ServiceError('Workspace administrator required to purchase',403)
    if route=='checkout' and method=='POST':return checkout(c,body,user,tenant_id)
    if route=='verify' and method=='POST':
        row=c.execute('SELECT tenant_id FROM market_orders WHERE id=?',(body.get('id'),)).fetchone()
        if not row or (not admin and row['tenant_id']!=tenant_id):raise a.ServiceError('Order not found',404)
        return verify(c,body['id'])
    raise a.ServiceError('Marketplace route not found',404)


def run_all():
    import app
    if not enabled():return
    now=int(time.time())
    with app.connect() as c:
        ids=[r['id'] for r in c.execute("SELECT id FROM market_orders WHERE state IN ('pending','checkout_error','creating') AND next_check<=? AND environment=? ORDER BY next_check,created LIMIT 20",(now,environment()))]
    for oid in ids:
        with app.connect() as c:
            # Durable claim; webhook and GUI confirmations are also idempotent.
            claimed=c.execute("UPDATE market_orders SET next_check=? WHERE id=? AND next_check<=? AND state IN ('pending','checkout_error','creating')",(now+300,oid,now)).rowcount;c.commit()
            if not claimed:continue
            try:verify(c,oid)
            except Exception:
                c.rollback();c.execute('UPDATE market_orders SET next_check=?,error=? WHERE id=?',(now+900,'Verification unavailable or mismatched. Reconcile in provider console.',oid))


if __name__=='__main__':
    import fcntl
    import app
    with open(os.path.join(os.path.dirname(app.DB),'marketplace.lock'),'w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit(0)
        app.init();run_all()
