"""Verify local SMTP envelope acceptance without sending DATA or a message."""
import argparse
from email.utils import parseaddr
import json
import smtplib


def probe(sender, recipient):
    for address in (sender, recipient):
        if not isinstance(address,str) or '\r' in address or '\n' in address or parseaddr(address)[1]!=address or '@' not in address:
            raise ValueError('Use a plain sender and recipient email address')
    with smtplib.SMTP('127.0.0.1',25,timeout=15) as smtp:
        smtp.ehlo()
        code,_=smtp.mail(sender)
        if code!=250:raise RuntimeError('Local Postfix rejected sender (SMTP %s)'%code)
        try:
            code,_=smtp.rcpt(recipient)
            if code not in (250,251):raise RuntimeError('Local Postfix rejected recipient/relay (SMTP %s)'%code)
        finally:
            smtp.rset()
    return {'local_submission_accepted':True,'message_sent':False,
            'inbox_delivery_verified':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--sender',required=True)
    parser.add_argument('--recipient',required=True)
    args=parser.parse_args()
    print(json.dumps(probe(args.sender,args.recipient)))
