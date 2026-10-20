"""Cache pinned-year public IRS resources; never uses current/draft PDF as a final prior-year form."""
import hashlib, json, os, sys, tempfile
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, build_opener, HTTPRedirectHandler

FORMS={'1040':'f1040','1040-schedule-c':'f1040sc','1040-schedule-se':'f1040sse','1040-schedule-1':'f1040s1','1040-schedule-2':'f1040s2','1065':'f1065','1065-k1':'f1065sk1','1120-S':'f1120s','1120-S-k1':'f1120ssk','1120':'f1120'}
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None

def refresh(root):
 root=Path(root);root.mkdir(parents=True,exist_ok=True);result={}
 for year in (2025,2026):
  for form,code in FORMS.items():
   url='https://www.irs.gov/pub/irs-prior/'+code+'--'+str(year)+'.pdf';key=str(year)+'-'+form
   item={'url':url,'checked_at':datetime.now(timezone.utc).isoformat(),'status':'unavailable','official_completion':False}
   try:
    with build_opener(NoRedirect).open(Request(url,headers={'User-Agent':'OOB-Federal-Form-Resources/1.0'}),timeout=15) as response:raw=response.read(5000001)
    if len(raw)>5000000 or not raw.startswith(b'%PDF-'):raise ValueError('Invalid PDF resource')
    # A pinned URL is useful provenance, not proof of finality or correct content.
    path=root/(key+'.pdf');path.write_bytes(raw);path.chmod(0o644)
    item.update(status='downloaded_needs_revision_review',sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),filename=path.name)
   except Exception as error:item['error_type']=type(error).__name__
   result[key]=item
 fd,tmp=tempfile.mkstemp(dir=root,prefix='.status-')
 try:
  with os.fdopen(fd,'w') as out:json.dump(result,out)
  os.chmod(tmp,0o644);os.replace(tmp,root/'status.json')
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 print(json.dumps({'downloaded':sum(r['status']=='downloaded_needs_revision_review' for r in result.values()),'total':len(result),'filing_ready':False,'taxpayer_data_sent':False}))

if __name__=='__main__':refresh(sys.argv[1])
