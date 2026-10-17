"""Synthetic, temporary server used only by CI browser checks."""
import os
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import app
from cryptography.fernet import Fernet

temporary=tempfile.TemporaryDirectory()
app.DB=temporary.name+'/browser.db'
os.environ['DOBHRAP_ADMIN_PASSWORD']='browser-test-password-123'
os.environ['DOBHRAP_ADMIN_EMAIL']='ui@example.com'
os.environ['DOBHRAP_ENCRYPTION_KEY']=Fernet.generate_key().decode()
app.init()
with app.connect() as c:
    c.execute("UPDATE users SET role='super_admin'")
    app.post_journal(c,'Synthetic sale',[{'account':'1000','debit':25000,'credit':0},{'account':'4000','debit':0,'credit':25000}])
app.ThreadingHTTPServer(('127.0.0.1',8765),app.Handler).serve_forever()
