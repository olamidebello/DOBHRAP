"""Account recovery. Store only token hashes; revoke sessions after any change."""
import hashlib
import hmac
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
import advanced as a
import provider_settings as settings

GENERIC='If an account exists for this email, a reset link will be sent. Check your inbox and spam folder.'


def initialize(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS password_resets(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL,expires INTEGER NOT NULL,used INTEGER NOT NULL DEFAULT 0,created INTEGER NOT NULL,delivery TEXT NOT NULL DEFAULT 'pending');
    CREATE TABLE IF NOT EXISTS password_reset_limits(key TEXT PRIMARY KEY,count INTEGER NOT NULL,started INTEGER NOT NULL);''')


def throttle(c, key, maximum, now):
    key=hashlib.sha256(key.encode()).hexdigest()
    row=c.execute('SELECT * FROM password_reset_limits WHERE key=?',(key,)).fetchone()
    count=row['count']+1 if row and now-row['started']<900 else 1
    start=row['started'] if row and now-row['started']<900 else now
    c.execute('INSERT OR REPLACE INTO password_reset_limits VALUES(?,?,?)',(key,count,start))
    c.execute('DELETE FROM password_reset_limits WHERE started<?',(now-86400,))
    if count>maximum:
        c.commit()
        raise a.ServiceError('Too many reset attempts. Try again in 15 minutes.',429)


def issue(c, user_id, now):
    token=secrets.token_urlsafe(32)
    digest=hashlib.sha256(token.encode()).hexdigest()
    c.execute('UPDATE password_resets SET used=1 WHERE user_id=?',(user_id,))
    c.execute('DELETE FROM password_resets WHERE expires<?',(now-86400,))
    c.execute('INSERT INTO password_resets(token_hash,user_id,expires,created) VALUES(?,?,?,?)',(digest,user_id,now+900,now))
    return token,digest


def link(token):
    # Fixed trusted origin; never build recovery links from an incoming Host header.
    return 'https://olamideolatayobello.com/reset-password#token='+token


def mail_config():
    result={key:settings.get('SMTP_'+key,'') for key in ('HOST','PORT','USERNAME','PASSWORD','FROM','SECURITY')}
    if not result['HOST'] or not result['FROM']:
        raise a.ServiceError('Email recovery is not configured. Contact your administrator for a reset link.',503)
    result['PORT']=int(result['PORT'] or ('465' if result['SECURITY']=='tls' else '587'))
    result['SECURITY']=result['SECURITY'] or 'starttls'
    if result['SECURITY']=='local':
        if result['HOST']!='127.0.0.1' or result['PORT']!=25 or result['USERNAME'] or result['PASSWORD']:
            raise a.ServiceError('Local mail requires 127.0.0.1 port 25 without credentials',503)
    elif result['SECURITY'] not in ('tls','starttls'):raise a.ServiceError('Secure email delivery is not configured',503)
    return result


def smtp_connection(config):
    if config['SECURITY'] not in ('local','starttls','tls'):
        raise a.ServiceError('Unsupported SMTP security mode',503)
    if config['SECURITY']=='local' and (config['HOST']!='127.0.0.1' or config['PORT']!=25 or config['USERNAME'] or config['PASSWORD']):
        raise a.ServiceError('Local SMTP is restricted to 127.0.0.1 port 25 without credentials',503)
    client=smtplib.SMTP_SSL if config['SECURITY']=='tls' else smtplib.SMTP
    options={'timeout':15}
    if config['SECURITY']=='tls':options['context']=ssl.create_default_context()
    smtp=client(config['HOST'],config['PORT'],**options)
    try:
        smtp.ehlo()
        if config['SECURITY']=='starttls':
            smtp.starttls(context=ssl.create_default_context());smtp.ehlo()
        if config['USERNAME']:smtp.login(config['USERNAME'],config['PASSWORD'])
        return smtp
    except Exception:
        smtp.close()
        raise


def check_mail_connection(config=None):
    config=config or mail_config()
    with smtp_connection(config) as smtp:
        code,_=smtp.noop()
        if code!=250:raise a.ServiceError('SMTP connection check failed',502)
    local=config['SECURITY']=='local'
    return {'ok':True,'message':('Local SMTP connection verified.' if local else 'SMTP TLS and configured authentication verified.')+' No email was sent; inbox delivery is not yet verified.'}


def send_email(config, email, token):
    message=EmailMessage()
    message['From']=config['FROM'];message['To']=email;message['Subject']='Reset your Olamide Olatayo Bello password'
    message['Date']=formatdate(localtime=False)
    message['Message-ID']=make_msgid(domain=config['FROM'].rsplit('@',1)[-1])
    message.set_content('Use this link within 15 minutes to choose a new password:\n\n'+link(token)+'\n\nIf you did not request this, you can ignore this message. Your password has not changed.')
    with smtp_connection(config) as smtp:
        smtp.send_message(message)


def request(c, body, ip):
    config=mail_config()
    email=str(body.get('email','')).strip().lower()
    if len(email)>254 or '@' not in email:raise a.ServiceError('Enter a valid email')
    now=int(time.time());c.execute('BEGIN IMMEDIATE')
    throttle(c,'request-ip:'+ip,100,now);throttle(c,'request-email:'+email,3,now)
    row=c.execute('SELECT id,email FROM users WHERE lower(email)=?',(email,)).fetchone()
    token=digest=None
    if row:token,digest=issue(c,row['id'],now)
    c.commit()
    if row:
        try:send_email(config,row['email'],token)
        except Exception:
            c.execute("UPDATE password_resets SET used=1,delivery='failed' WHERE token_hash=?",(digest,))
            a.audit(c,0,'Password recovery email delivery failed')
        else:c.execute("UPDATE password_resets SET delivery='sent' WHERE token_hash=?",(digest,))
    return {'ok':True,'message':GENERIC}


def update_password(c, user_id, body):
    import app
    password=str(body.get('password',''))
    if not 14<=len(password)<=1024:raise a.ServiceError('Password must contain 14 to 1024 characters')
    if password!=body.get('confirm_password'):raise a.ServiceError('Passwords do not match')
    salt=secrets.token_hex(16)
    c.execute('UPDATE users SET salt=?,hash=? WHERE id=?',(salt,app.password(password,salt),user_id))
    c.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
    c.execute('UPDATE password_resets SET used=1 WHERE user_id=?',(user_id,))
    a.audit(c,user_id,'Password changed; all sessions revoked')


def finish(c, body, ip):
    now=int(time.time());c.execute('BEGIN IMMEDIATE');throttle(c,'finish-ip:'+ip,30,now)
    token=str(body.get('token',''))
    if not 32<=len(token)<=128:c.commit();raise a.ServiceError('Reset link is invalid or expired',400)
    digest=hashlib.sha256(token.encode()).hexdigest()
    row=c.execute('SELECT user_id FROM password_resets WHERE token_hash=? AND used=0 AND expires>?',(digest,now)).fetchone()
    if not row:c.commit();raise a.ServiceError('Reset link is invalid or expired',400)
    if c.execute("SELECT account_status FROM users WHERE id=?",(row['user_id'],)).fetchone()[0]!='active':raise a.ServiceError('Account unavailable',403)
    update_password(c,row['user_id'],body)
    return {'ok':True,'message':'Password updated. Sign in with your new password.'}


def authenticated(c, user, body, admin=False):
    import app
    c.execute('BEGIN IMMEDIATE')
    throttle(c,'password-confirm:'+str(user['id']),20,int(time.time()))
    if not hmac.compare_digest(user['hash'],app.password(str(body.get('current_password','')),user['salt'])):
        c.commit()
        raise a.ServiceError('Current password is incorrect',403)
    if not admin:
        update_password(c,user['id'],body)
        return {'ok':True,'message':'Password changed. Sign in again.'}
    if user['role'] not in ('admin','super_admin'):raise a.ServiceError('Administrator required',403)
    target=c.execute('SELECT id,role,tenant_id FROM users WHERE lower(email)=?',(str(body.get('email','')).strip().lower(),)).fetchone()
    if not target or (user['role']!='super_admin' and (target['tenant_id']!=user['tenant_id'] or target['role']=='super_admin')):
        raise a.ServiceError('Account is unavailable for password recovery',403)
    throttle(c,'admin:'+str(user['id']),20,int(time.time()))
    token,digest=issue(c,target['id'],int(time.time()))
    c.execute("UPDATE password_resets SET delivery='administrator' WHERE token_hash=?",(digest,))
    a.audit(c,user['id'],'Administrator issued password recovery for user '+str(target['id']))
    return {'ok':True,'reset_url':link(token),'expires_in':900}

