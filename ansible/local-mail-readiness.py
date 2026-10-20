"""Public DNS and network checks; never sends a message or reads a private key."""
import argparse
import ipaddress
import json
from pathlib import Path
import re
import shlex
import socket
import subprocess


def dig(*args):
    result=subprocess.run(['dig','+short','+time=3','+tries=1',*args],capture_output=True,text=True,timeout=8)
    return result.stdout.strip().splitlines() if result.returncode==0 else []


def txt(name):
    return [''.join(shlex.split(line)) for line in dig(name,'TXT')]


def public_record(raw):
    record=''.join(re.findall(r'"([^"\n]*)"',raw))
    if not record.startswith('v=DKIM1;') or 'p=' not in record:
        raise ValueError('DKIM public record is missing; existing private key was not rotated')
    return record


def inspect(domain,hostname,ip,selector):
    ipaddress.IPv4Address(ip)
    for name in (domain,hostname):
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]+\.[a-z]{2,}',name):raise ValueError('Invalid domain')
    if not re.fullmatch(r'[a-z0-9]{1,30}',selector):raise ValueError('Invalid selector')
    record=public_record(Path('/etc/opendkim/keys',domain,selector+'.txt').read_text())
    dkim_name=selector+'._domainkey.'+domain
    instructions=(f'A {hostname} -> {ip}\n'
        f'PTR {ip} -> {hostname} (request this from your server/IP provider)\n'
        f'DKIM TXT {dkim_name}:\n{record}\n\n'
        f'SPF TXT {domain}: authorize ip4:{ip} in the existing v=spf1 record.\n'
        f'If this is your only sender and no SPF exists: v=spf1 ip4:{ip} -all\n'
        'Publish only ONE SPF record; preserve existing authorized senders.\n'
        f'DMARC TXT _dmarc.{domain}: v=DMARC1; p=none (only if no policy exists).\n'
        'Preserve existing DMARC policy. No incoming MX/mailbox is installed by this workflow.\n'
        'Outbound TCP 25 must be permitted by the hosting provider.\n')
    Path('/var/log/oob-local-mail-dns.txt').write_text(instructions)
    spf=[value for value in txt(domain) if value.startswith('v=spf1')]
    checks={'hostname_a':ip in dig(hostname,'A'),
            'reverse_dns':hostname+'.' in dig('-x',ip),
            'dkim_published':record in txt(dkim_name),
            'spf_explicit_ip':len(spf)==1 and ('ip4:'+ip) in spf[0].split(),
            'dmarc_published':any(value.startswith('v=DMARC1;') for value in txt('_dmarc.'+domain)),
            'outbound_tcp25':False}
    for line in dig('gmail.com','MX')[:2]:
        fields=line.split()
        if len(fields)!=2:continue
        try:
            with socket.create_connection((fields[1].rstrip('.'),25),timeout=4):
                checks['outbound_tcp25']=True
                break
        except OSError:pass
    report={'local_engine_configured':True,'checks':checks,
            'external_checks_passed':all(checks.values()),'inbox_delivery_verified':False,
            'notice':'DNS/network checks are not proof of delivery. SPF include mechanisms require separate review when explicit IP is absent.'}
    Path('/var/log/oob-local-mail-readiness.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for key in ('domain','hostname','ip','selector'):parser.add_argument('--'+key,required=True)
    args=parser.parse_args()
    print(json.dumps(inspect(args.domain,args.hostname,args.ip,args.selector)))
