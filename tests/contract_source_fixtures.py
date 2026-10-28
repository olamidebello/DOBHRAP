"""Synthetic complete source set for tests unrelated to source extraction."""
import hashlib,json,time
import advanced as a
import contract_details

def seed_review(c,tid,owner,nid='a'*32):
 data={'notice':{'noticeId':nid,'title':'Synthetic verified source'},'description':'Synthetic complete solicitation description.','attachments':[],'attachment_count':0,'coverage_complete':True,'warnings':[]}
 c.execute('INSERT OR REPLACE INTO contracting_details VALUES(?,?,?,?,?)',(tid,nid,'ready',a.seal(data),int(time.time())))
 _,prompts=contract_details.chunks(c,tid,nid)
 report={'fingerprint':hashlib.sha256(json.dumps(prompts).encode()).hexdigest(),'sections':{str(i):{'text':'Synthetic reviewed facts [REQUIRED]','request_id':'fixture'} for i in range(len(prompts))},'total':len(prompts),'complete':True}
 c.execute('INSERT OR REPLACE INTO contracting_reports VALUES(?,?,?,?,?)',(owner,tid,nid,a.seal(report),int(time.time())))
