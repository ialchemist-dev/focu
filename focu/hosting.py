"""Deployment preflight and unit generation; never changes tailnet permissions."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
from urllib.parse import urlsplit


def doctor():
    binary=shutil.which('tailscale');state='not_installed';dns=None
    if binary:
        try:
            r=subprocess.run([binary,'status','--json'],capture_output=True,text=True,timeout=10)
            data=json.loads(r.stdout) if r.returncode==0 else {}
            state=data.get('BackendState','unavailable')
            dns=data.get('Self',{}).get('DNSName')
        except (OSError,ValueError,subprocess.SubprocessError):state='unavailable'
    return {'platform':platform.system(),'tailscale':state,'dns_name':dns,
            'tun_available':Path('/dev/net/tun').exists(),'systemctl':bool(shutil.which('systemctl')),
            'git':bool(shutil.which('git')),'root':hasattr(os,'geteuid') and os.geteuid()==0,
            'platform_persistence':'not_verified','private_https_ready':False,
            'note':'Missing TUN does not prove userspace Serve is unavailable; verify on the target host.'}


def units(checkout,db,media,repo,drive_config,environment_file,public_origin,output):
    origin=urlsplit(public_origin)
    if origin.scheme!='https' or not origin.hostname or origin.username or origin.password or origin.path not in ('','/') or origin.query or origin.fragment:
        raise ValueError('Expected exact HTTPS public origin')
    def quote(value):
        value=str(value)
        if any(c in value for c in '\n\r\0'):raise ValueError('Invalid unit path')
        return json.dumps(value.replace('%','%%'))
    checkout=Path(checkout).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    executable=checkout/'.venv/bin/focu'
    common=f'''[Unit]
Description=Focu private reading service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={quote(checkout)}
EnvironmentFile={quote(Path(environment_file).resolve())}
Restart=on-failure
RestartSec=10
UMask=0077
'''
    reader=' '.join([quote(executable),'--db',quote(Path(db).resolve()),'reader serve --port 8765 --media-root',quote(Path(media).resolve()),
                     '--public-origin',quote(public_origin.rstrip('/')),'--drive-config',quote(Path(drive_config).resolve())])
    sync=' '.join([quote(executable),'--db',quote(Path(db).resolve()),'sync watch --interval 60 --repo',quote(Path(repo).resolve()),
                   '--media-root',quote(Path(media).resolve()),'--drive-config',quote(Path(drive_config).resolve())])
    for name,command in [('focu-reader',reader),('focu-sync',sync)]:
        path=output/(name+'.service')
        path.write_text(common+'ExecStart='+command+'\n\n[Install]\nWantedBy=multi-user.target\n')
    return {'units':[str(output/'focu-reader.service'),str(output/'focu-sync.service')],
            'serve_command':'tailscale serve --bg http://127.0.0.1:8765',
            'public_origin':public_origin.rstrip('/'),'installed':False,
            'note':'Install generated units only after configuring private credentials and authorizing this tailnet device.'}


def main(argv=None):
    p=argparse.ArgumentParser(prog='focu host');sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('doctor');configure=sub.add_parser('configure')
    for name in ('checkout','db','media-root','repo','drive-config','environment-file','public-origin','output-dir'):
        configure.add_argument('--'+name,required=True)
    args=p.parse_args(argv)
    result=doctor() if args.action=='doctor' else units(args.checkout,args.db,args.media_root,args.repo,args.drive_config,args.environment_file,args.public_origin,args.output_dir)
    print(json.dumps(result,indent=2));return 0
