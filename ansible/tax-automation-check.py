"""Check existing credentials without displaying them; enable user-consented jobs."""
import json
import os
import sys
import time
import shlex
import argparse
from pathlib import Path
from active_runtime import load_active


if __name__=='__main__':
    if os.geteuid()!=0:raise SystemExit('Run as root through Ansible')
    parser=argparse.ArgumentParser()
    parser.add_argument('service',nargs='?',default='oob-business.service')
    parser.add_argument('--status',action='store_true')
    args=parser.parse_args()
    app=load_active(args.service)
    import provider_settings as settings
    import database
    readiness={'backend':'mysql' if database.mysql_enabled() else 'sqlite',
        'key_configured':bool(settings.get('OPENAI_API_KEY')),
        'analyst_model_configured':bool(settings.get('TAX_ANALYST_MODEL')),
        'tax_model_configured':bool(settings.get('TAX_AI_MODEL')),
        'analysis_enabled':settings.get('DOBHRAP_ENABLE_TAX_ANALYST')=='1',
        'live_api_tested':False}
    if args.status:
        print(json.dumps(readiness));sys.exit(0)
    inherited={}
    for path in (Path('/etc/dobhrap.env'),Path('/etc/dobhrap-mysql.env')):
        if not path.exists():continue
        for line in path.read_text().splitlines():
            key,sep,value=line.partition('=')
            if sep and (key.strip().startswith('DOBHRAP_') or key.strip() in settings.FIELDS):
                parts=shlex.split(value,comments=False)
                inherited[key.strip()]=parts[0] if len(parts)==1 else ''
    for key,default in (('DOBHRAP_DB_BACKEND','sqlite'),('DOBHRAP_DB','data/dobhrap.db'),('DOBHRAP_MYSQL_CONFIG','/etc/dobhrap-mysql.json'),('DOBHRAP_ENCRYPTION_KEY','')):
        if inherited.get(key,default)!=os.environ.get(key,default):
            raise SystemExit('Worker environment files differ from the live service for '+key+'. Align service configuration before starting automation. No secret values are displayed.')
    import provider_settings as settings
    import advanced as a
    import database
    if not readiness['key_configured']:
        raise SystemExit('No OpenAI key is configured in the live application database or service environment. Restore/save your existing key under Super admin > Provider provisioning & keys. No credential was changed.')
    if not (readiness['analyst_model_configured'] or readiness['tax_model_configured']):
        raise SystemExit('Existing OpenAI key found, but no Tax Analyst or Tax AI model is configured. Set a document-capable Tax Analyst model in Super admin > Provider provisioning & keys. No credential was changed.')
    with app.connect() as c:
        for key in ('OPENAI_API_KEY','TAX_ANALYST_MODEL','TAX_AI_MODEL'):
            saved=c.execute('SELECT 1 FROM provider_settings WHERE key=?',(key,)).fetchone()
            if not saved and inherited.get(key,'')!=os.environ.get(key,''):
                raise SystemExit('The web service has '+key+' but its value is not shared by the worker environment files. Save the existing setting in Provider provisioning & keys or align the service environment. No secret was copied or displayed.')
    with app.connect() as c:
        c.execute('SELECT id FROM tax_analysis_jobs LIMIT 1')
        c.execute('INSERT OR REPLACE INTO provider_settings VALUES(?,?,?)',('DOBHRAP_ENABLE_TAX_ANALYST',a.seal({'value':'1'}),int(time.time())))
        a.audit(c,0,'Sequential tax document automation enabled using existing provider configuration')
        c.commit()
    print(json.dumps({'backend':'mysql' if database.mysql_enabled() else 'sqlite','key_configured':True,'model_configured':True,'analysis_enabled':True,'live_api_tested':False}))
