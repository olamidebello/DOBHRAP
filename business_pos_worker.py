"""Bounded, idempotent first-party storefront setup. No payments or shopping requests."""
import app,business_pos
if __name__=='__main__':
 app.init();business_pos.process(app)
