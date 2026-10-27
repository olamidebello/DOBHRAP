"""Bounded scheduled public-opportunity retrieval; no bids or AI requests sent."""
import app
import contracting
if __name__=='__main__':
 app.init()
 contracting.process(app,limit=3)
