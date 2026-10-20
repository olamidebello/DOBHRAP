"""Check existing credentials without displaying them; enable user-consented jobs."""
import json
import os
import sys
import time
import shlex
from pathlib import Path
from active_runtime import load_active


if __name__=='__main__':
    if os.geteuid()!=0:raise SystemExit('Run as root through Ansible')
    app=load_active(sys.argv[1] if len(sys.argv)>1 else 'oob-business.service')
    inherited={}
    for path in (Path('/etc/dobhrap.env'),Path('/etc/dobhrap-mysql.env')):
        if not path.exists():continue
        for line in path.read_text().splitlines():
            key,sep,value=line.partition('=')
            if sep and key.strip().startswith('DOBHRAP_'):
                parts=shlex.split(value,comments=False)
                inherited[key.strip()]=parts[0] if len(parts)==1 else ''
    for key,default in (('DOBHRAP_DB_BACKEND','sqlite'),('DOBHRAP_DB','data/dobhrap.db'),('DOBHRAP_MYSQL_CONFIG','/etc/dobhrap-mysql.json'),('DOBHRAP_ENCRYPTION_KEY','')):
        if inherited.get(key,default)!=os.environ.get(key,default):
            raise SystemExit('Worker environment files differ from the live service for '+key+'. Align service configuration before starting automation. No secret values are displayed.')
    import provider_settings as settings
    import advanced as a
    import database
    if not settings.get('OPENAI_API_KEY') or not (settings.get('TAX_ANALYST_MODEL') or settings.get('TAX_AI_MODEL')):
        raise SystemExit('Configure the existing OpenAI key and a document-capable Tax Analyst model in Super admin before enabling automation. No API credential was changed.')
    with app.connect() as c:
        c.execute('SELECT id FROM tax_analysis_jobs LIMIT 1')
        c.execute('INSERT OR REPLACE INTO provider_settings VALUES(?,?,?)',('DOBHRAP_ENABLE_TAX_ANALYST',a.seal({'value':'1'}),int(time.time())))
        a.audit(c,0,'Sequential tax document automation enabled using existing provider configuration')
        c.commit()
    print(json.dumps({'backend':'mysql' if database.mysql_enabled() else 'sqlite','key_configured':True,'model_configured':True,'analysis_enabled':True,'live_api_tested':False}))
