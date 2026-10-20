"""Refresh fixed public IRS references. Never sends taxpayer information."""
import hashlib, json, os, re, sys, tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from tax_analysis_report import REFERENCES

class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None

class Text(HTMLParser):
 def __init__(self):super().__init__();self.parts=[];self.ignore=0
 def handle_starttag(self,tag,attrs):
  if tag in ('script','style'):self.ignore+=1
 def handle_endtag(self,tag):
  if tag in ('script','style'):self.ignore=max(0,self.ignore-1)
 def handle_data(self,data):
  if not self.ignore and data.strip():self.parts.append(data.strip())

def refresh(dest):
 result={}
 for key,ref in REFERENCES.items():
  try:
   with build_opener(NoRedirect).open(Request(ref['url'],headers={'User-Agent':'OOB-Tax-Reference-Check/1.0'}),timeout=25) as response:
    raw=response.read(3000001)
    if len(raw)>3000000:raise ValueError('Reference exceeds size limit')
   parser=Text();parser.feed(raw.decode('utf-8',errors='replace'));text=' '.join(parser.parts)
   if 'Internal Revenue Service' not in text:raise ValueError('Unexpected reference page')
   # Small excerpts for human review, not a tax-law execution engine.
   excerpts=[]
   for match in re.finditer(r'ordinary and necessary|personal expenses|business meal|qualified expenses|business use|gross receipts|taxable interest|qualified dividends',text,re.I):
    excerpt=text[max(0,match.start()-100):match.end()+450]
    if excerpt not in excerpts:excerpts.append(excerpt)
    if len(excerpts)>=5:break
   result[key]={'url':ref['url'],'checked_at':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(raw).hexdigest(),'status':'available','excerpts':excerpts}
  except Exception as error:result[key]={'url':ref['url'],'status':'unavailable','error_type':type(error).__name__,'excerpts':[]}
 dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(dir=dest.parent,prefix='.irs-reference-')
 try:
  with os.fdopen(fd,'w') as output:json.dump(result,output)
  os.chmod(tmp,0o644);os.replace(tmp,dest)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 print(json.dumps({'available':sum(r['status']=='available' for r in result.values()),'total':len(result),'taxpayer_data_sent':False}))
 if not any(r['status']=='available' for r in result.values()):raise SystemExit(1)

if __name__=='__main__':refresh(sys.argv[1])
