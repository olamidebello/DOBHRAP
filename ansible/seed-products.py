#!/usr/bin/env python3
"""Seed editable offers locally without reading or exposing provider credentials."""
import argparse,json,sqlite3,sys
p=argparse.ArgumentParser();p.add_argument('--source',default='/opt/dobhrap/current');p.add_argument('--db',default='/var/lib/dobhrap/dobhrap.db');p.add_argument('--preparation-price',default='49.00');p.add_argument('--amendment-price',default='79.00');p.add_argument('--publish',action='store_true');p.add_argument('--overwrite',action='store_true');args=p.parse_args()
sys.path.insert(0,args.source)
import marketplace
import database
with database.connect(args.db) as c:
 c.row_factory=sqlite3.Row;marketplace.initialize(c);result=marketplace.seed_tax_products(c,args.preparation_price,args.amendment_price,args.publish,args.overwrite)
print(json.dumps(result))
