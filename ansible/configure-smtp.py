"""Verify and encrypt SMTP settings using the running service's database."""
import argparse
import json
import os
from pathlib import Path
import sys
import time


def configure(app, supplied):
    import advanced as a
    import password_reset as recovery
    import provider_settings as settings
    keys=('HOST','PORT','USERNAME','PASSWORD','FROM','SECURITY')
    defaults={'HOST':'smtp.gmail.com','USERNAME':'dobcalldemo@gmail.com',
              'FROM':'dobcalldemo@gmail.com','SECURITY':'starttls'}
    candidate={}
    for key in keys:
        value=supplied.get('SMTP_'+key,'')
        if not isinstance(value,str):raise ValueError('SMTP values must be strings')
        candidate[key]=value or settings.get('SMTP_'+key,'') or defaults.get(key,'')
    candidate['PORT']=candidate['PORT'] or ('465' if candidate['SECURITY']=='tls' else '587')
    for key,value in candidate.items():settings.validate('SMTP_'+key,value)
    if not candidate['HOST'] or not candidate['FROM']:
        raise ValueError('SMTP host and sender are required')
    if candidate['USERNAME'] and not candidate['PASSWORD']:
        raise ValueError('Supply the provider SMTP password or save one in the GUI first')
    candidate['PORT']=int(candidate['PORT'])
    # No settings are replaced when TLS, authentication or connectivity fails.
    result=recovery.check_mail_connection(candidate)
    with app.connect() as c:
        settings.initialize(c)
        c.execute('BEGIN IMMEDIATE')
        for key,value in candidate.items():
            c.execute('INSERT OR REPLACE INTO provider_settings VALUES(?,?,?)',
                      ('SMTP_'+key,a.seal({'value':str(value)}),int(time.time())))
        c.execute('INSERT OR REPLACE INTO provider_checks VALUES(?,?,?,?,?)',
                  ('smtp',1,int(time.time()),result['message'],0))
        a.audit(c,0,'SMTP recovery configuration encrypted; TLS and authentication checked')
        c.commit()
    return result


def main():
    if os.geteuid()!=0:raise RuntimeError('Run as root through Ansible')
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    parser.add_argument('--service',default='oob-business.service')
    args=parser.parse_args()
    path=Path(args.config)
    stat=path.stat()
    if stat.st_uid!=0 or stat.st_mode&0o077:
        raise RuntimeError('SMTP input must be root-owned and private')
    from active_runtime import load_active
    result=configure(load_active(args.service),json.loads(path.read_text()))
    print(json.dumps(result))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('SMTP configuration failed ('+type(error).__name__+'). Check credentials, TLS, hostname and outbound port access. Existing SMTP settings were not replaced unless verification completed.',file=sys.stderr)
        sys.exit(1)
