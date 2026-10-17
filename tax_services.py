"""Tax-only account permissions and verified, year-specific payment access."""
import re
import advanced as a

def initialize(c):
 if 'service_mode' not in {r[1] for r in c.execute('PRAGMA table_info(tenants)')}:
  c.execute("ALTER TABLE tenants ADD COLUMN service_mode TEXT NOT NULL DEFAULT 'business'")

def paid(c,tenant_id,owner,y):
 return bool(c.execute("SELECT 1 FROM market_services s JOIN market_orders o ON o.id=s.order_id WHERE s.tenant_id=? AND o.owner=? AND s.service_code=? AND ((s.environment='live' AND o.environment='live') OR (s.environment='coupon' AND o.environment='coupon' AND o.gateway='coupon' AND EXISTS(SELECT 1 FROM coupon_redemptions r WHERE r.order_id=o.id AND r.owner=o.owner AND r.tenant_id=o.tenant_id))) AND s.status='active' AND s.work_state!='suspended' AND o.state='fulfilled'",(tenant_id,owner,'tax_preparation_'+str(y))).fetchone())

def status(c,tenant_id,user):
 years=[y for y in range(2000,2101) if paid(c,tenant_id,user['id'],y)]
 return {'paid_years':years,'payment_required':True,'filing_available':False,'notice':'Verified live payment or an accepted service coupon for a tax-year preparation service is required before building or exporting preparation. Payment does not enable IRS e-filing; a completed filing engine and authorized integration are not available in this interview.'}

def enforce(c,path,method,body,tenant,user):
 if tenant['service_mode']!='tax_only':return
 allowed=path=='/api/me' or path=='/api/tax-services/status' or path=='/api/coupons/redeem' or path.startswith(('/api/tax-prep/','/api/tax-analyst/','/api/support/')) or path in ('/api/market/status','/api/market/products','/api/market/orders','/api/market/services','/api/market/checkout','/api/market/verify')
 if not allowed:raise a.ServiceError('This account provides tax services only',403)
 if path in ('/api/market/checkout','/api/coupons/redeem'):
  product=c.execute('SELECT service_code FROM market_products WHERE id=? AND active=1',(body.get('product_id'),)).fetchone()
  if not product or not re.fullmatch(r'tax_preparation_\d{4}',product['service_code']):raise a.ServiceError('Choose a tax preparation service for this account',403)
 gated=method=='POST' and (path in ('/api/tax-prep/create','/api/tax-prep/export','/api/tax-analyst/compile') or (path=='/api/tax-prep/save' and body.get('reviewed') is True))
 if gated:
  y=body.get('year') if path=='/api/tax-analyst/compile' else 2026
  if type(y) is not int or not 2000<=y<=2100:raise a.ServiceError('Choose a valid tax year')
  if not paid(c,tenant['id'],user['id'],y):raise a.ServiceError('Payment required: pay or redeem a service coupon for tax preparation for '+str(y)+' and verify payment before building or exporting.',402)
