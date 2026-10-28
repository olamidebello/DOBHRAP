"""Bounded scheduled public-opportunity retrieval; no bids or AI requests sent."""
import app
import contracting
import contract_details
if __name__=='__main__':
 app.init()
 contract_details.process(app)
 contracting.process(app,limit=3)
