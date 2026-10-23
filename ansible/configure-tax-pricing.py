"""Apply the authorized launch pricing to the active catalog; never call AI or payments."""
import json
import os
import sys


def apply(c, user):
    import tax_analyst_billing as billing
    before = billing.pricing(c, 'GET', {}, user)
    r = billing.RECOMMENDED
    result = billing.pricing(c, 'POST', {
        'price_cents': r['price_cents'], 'active': bool(before['product']['active']),
        'expected_price_cents': before['product']['amount'],
        'expected_active': bool(before['product']['active']),
        'credit_rates': r['rates'], 'expected_rates_revision': before['credit_policy']['revision'],
        'name': r['name'], 'description': r['description'],
    }, user)
    c.commit()
    return {'price_cents': result['product']['amount'], 'currency': 'USD',
            'rates': result['credit_policy']['rates'], 'usage': result['usage_summary'],
            'purchase_availability_preserved': True, 'existing_orders_preserved': True}


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run as root on the hosting server')
    sys.path.insert(0, '/opt/dobhrap/current/ansible')
    from active_runtime import load_active
    app = load_active('oob-business.service')
    import tax_analyst_billing as billing
    if not hasattr(billing, 'RECOMMENDED'):
        raise RuntimeError('Deploy the updated application with ansible/repair-oob.yml first')
    with app.connect() as c:
        row = c.execute("SELECT id,role FROM users WHERE role='super_admin' ORDER BY id LIMIT 1").fetchone()
        if not row:
            raise RuntimeError('Create or recover a super administrator before applying pricing')
        print(json.dumps(apply(c, dict(row))))


if __name__ == '__main__':
    main()
