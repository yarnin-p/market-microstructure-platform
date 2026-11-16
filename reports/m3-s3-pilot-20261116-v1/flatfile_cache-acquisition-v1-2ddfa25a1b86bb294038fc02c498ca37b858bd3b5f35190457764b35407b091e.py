"""Bounded Massive S3 immutable daily snapshots with resumable local partials.

Credentials are read at runtime only; never placed in metadata or error text.
ETag is object identity evidence, not assumed to be a content MD5.
"""
import argparse
import hashlib
import json
import os
import resource
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .storage import digest, file_hash
from .temporal_design import read

CONFIG = 'configs/task-003-s3-pilot-v1.json'


def atomic_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    os.replace(tmp, path)


def object_identity(meta):
    return digest([meta['key'], meta['size'], meta['etag'], meta['last_modified']])


def memory_bytes():
    n = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return n if sys.platform == 'darwin' else n*1024


class Resources:
    def __init__(self, config, root):
        self.config = config; self.path = Path(root)/'resource-ledger.json'
        self.state = read(self.path) if self.path.exists() else {
            'requests': 7, 'downloaded_bytes': 0, 'active_seconds': 0., 'decoded_bytes': 0,
            'max_rss_bytes': 0, 'metadata_probe_requests': 7}
        self.last = time.monotonic()
    def save(self):
        now = time.monotonic(); self.state['active_seconds'] += now-self.last; self.last = now
        self.state['max_rss_bytes'] = max(self.state['max_rss_bytes'], memory_bytes())
        atomic_json(self.path, self.state)
    def check(self):
        cfg, s = self.config, self.state
        if s['active_seconds']+time.monotonic()-self.last > cfg['max_active_seconds']:raise RuntimeError('EXECUTION_BUDGET')
        if s['downloaded_bytes'] > cfg['max_download_bytes']:raise RuntimeError('DOWNLOAD_BYTE_BUDGET')
        if s['decoded_bytes'] > cfg['max_decoded_bytes']:raise RuntimeError('DECODED_BYTE_BUDGET')
        if memory_bytes() > cfg['max_memory_bytes']:raise RuntimeError('MEMORY_BUDGET')
        if shutil.disk_usage('.').free < cfg['min_disk_free_bytes']:raise RuntimeError('DISK_FREE_BUDGET')
    def request(self):
        self.check()
        if self.state['requests'] >= self.config['max_requests']:raise RuntimeError('REQUEST_BUDGET')
        self.state['requests'] += 1; self.save()


def client(config, credentials_file=None):
    import boto3
    from botocore.config import Config
    if credentials_file:
        p = Path(credentials_file)
        if p.stat().st_mode & 0o077:raise ValueError('Credential file must have private permissions')
        credentials = read(p)
        key, secret = credentials['access_key_id'], credentials['secret_access_key']
    else:
        key = os.environ['MASSIVE_S3_ACCESS_KEY_ID']; secret = os.environ['MASSIVE_S3_SECRET_ACCESS_KEY']
    return boto3.client('s3', endpoint_url=config['endpoint'], region_name='us-east-1',
        aws_access_key_id=key, aws_secret_access_key=secret,
        config=Config(signature_version='s3v4', s3={'addressing_style':'path'},
            connect_timeout=config['connect_timeout_seconds'], read_timeout=config['read_timeout_seconds'],
            retries={'total_max_attempts':1}))


def head(c, config, meta, resources):
    resources.request()
    r = c.head_object(Bucket=config['bucket'], Key=meta['key'])
    return {'key':meta['key'], 'size':r['ContentLength'], 'etag':r['ETag'],
            'last_modified':r['LastModified'].isoformat()}


def location(meta):
    return Path('data/flatfiles', meta['dataset']+'_v1', meta['date'])


def partial(meta):
    folder = location(meta)/'partial'; folder.mkdir(parents=True, exist_ok=True)
    ident = object_identity(meta)
    return folder/(ident+'.part'), folder/(ident+'.json')


def resume_prefix(path, checkpoint):
    if not checkpoint.exists():
        if path.exists():raise ValueError('Partial without integrity checkpoint')
        return 0, hashlib.sha256()
    saved = read(checkpoint); offset = saved['offset']
    if not path.exists() or path.stat().st_size < offset:raise ValueError('Truncated partial')
    with path.open('r+b') as f:f.truncate(offset)
    h = hashlib.sha256()
    with path.open('rb') as f:
        while chunk := f.read(8*1024**2):h.update(chunk)
    if h.hexdigest() != saved['prefix_sha256']:raise ValueError('Partial prefix hash mismatch')
    return offset, h


def transfer(c, config, meta, resources, probe_bytes=None):
    folder = location(meta); identity = object_identity(meta)
    entry = folder/'sources'/(identity+'.json')
    if entry.exists():
        saved = read(entry)
        if file_hash(saved['local_path']) != saved['sha256']:raise ValueError('Cached source hash mismatch')
        return saved
    path, checkpoint = partial(meta)
    offset, h = resume_prefix(path, checkpoint)
    end = min(meta['size'], offset+probe_bytes) if probe_bytes else meta['size']
    if offset < end:
        expected = end-offset
        if resources.state['downloaded_bytes']+expected > config['max_download_bytes']:raise RuntimeError('PLANNED_DOWNLOAD_BUDGET')
        resources.request(); started = time.monotonic()
        r = c.get_object(Bucket=config['bucket'], Key=meta['key'], Range=f'bytes={offset}-{end-1}', IfMatch=meta['etag'])
        if r['ResponseMetadata']['HTTPStatusCode'] != 206 or r.get('ETag') != meta['etag'] or r['ContentLength'] != expected:
            r['Body'].close();raise ValueError('Range/source identity mismatch')
        expected_range = f'bytes {offset}-{end-1}/{meta["size"]}'
        if r.get('ContentRange') != expected_range:
            r['Body'].close();raise ValueError('ContentRange mismatch')
        with path.open('ab') as f:
            try:
                while offset < end:
                    resources.check()
                    chunk = r['Body'].read(min(config['chunk_bytes'], end-offset))
                    if not chunk:raise RuntimeError('INCOMPLETE_SOURCE_DOWNLOAD')
                    f.write(chunk); h.update(chunk); offset += len(chunk)
                    resources.state['downloaded_bytes'] += len(chunk)
                    f.flush()
                    atomic_json(checkpoint, {'offset':offset,'prefix_sha256':h.hexdigest(),'object_identity':identity})
                    resources.save()
                    if offset % (256*1024**2) < config['chunk_bytes']:
                        print(json.dumps({'date':meta['date'],'dataset':meta['dataset'],'downloaded':offset,'size':meta['size']}),flush=True)
            finally:
                r['Body'].close(); f.flush(); os.fsync(f.fileno()); resources.save()
        elapsed = time.monotonic()-started
        print(json.dumps({'date':meta['date'],'dataset':meta['dataset'],'range_bytes':expected,'seconds':elapsed,'MiB_per_second':expected/max(elapsed,.001)/1024**2}),flush=True)
    if probe_bytes:
        return {'partial_path':str(path),'prefix_bytes':offset,'prefix_sha256':h.hexdigest()}
    if offset != meta['size']:raise RuntimeError('SOURCE_LENGTH_MISMATCH')
    current = head(c, config, meta, resources)
    if object_identity(current) != identity:raise ValueError('SOURCE_CHANGED_DURING_DOWNLOAD: partial retained')
    sha = h.hexdigest(); dest = folder/'snapshots'/(sha+'.csv.gz');dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():
        if file_hash(dest) != sha:raise ValueError('Content address collision')
        path.unlink()
    else:os.replace(path,dest)
    record = {**meta,'bucket':config['bucket'],'endpoint':config['endpoint'],'downloaded_at':datetime.now(timezone.utc).isoformat(),
              'sha256':sha,'local_path':str(dest),'object_identity':identity,'complete':True,
              'etag_not_content_md5':True}
    atomic_json(entry,record)
    return record


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['probe','download']);p.add_argument('--config',default=CONFIG);p.add_argument('--credentials-file');a=p.parse_args()
    config=read(a.config);root=Path('data/runs',config['run_id']);resources=Resources(config,root)
    assert file_hash(a.config)==read(root/'plan-freeze.json')['config_sha256']
    c=client(config,a.credentials_file)
    try:
        if a.command=='probe':
            result=transfer(c,config,config['objects'][0],resources,8*1024**2)
            import zlib
            with Path(result['partial_path']).open('rb') as f:
                header=zlib.decompressobj(16+zlib.MAX_WBITS).decompress(f.read(64*1024),4096).decode().splitlines()[0]
            atomic_json(root/'throughput-probe.json',{**result,'header':header,'resources':resources.state})
            print(header)
        else:
            sources=[]
            for meta in config['objects']:
                sources.append(transfer(c,config,meta,resources))
                atomic_json(root/'downloaded-sources.json',sources)
    except Exception as exc:
        # Never serialize arbitrary SDK exceptions or request headers.
        atomic_json(root/'acquisition-stop.json',{'status':'INCOMPLETE','error_type':type(exc).__name__,
            'reason':str(exc) if isinstance(exc,(RuntimeError,ValueError)) else 'S3_OR_IO_ERROR_REDACTED',
            'resources':resources.state})
        raise RuntimeError('S3 pilot stopped; see sanitized acquisition-stop.json') from None
    finally:resources.save()


if __name__=='__main__':main()
