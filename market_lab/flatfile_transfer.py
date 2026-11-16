"""Bounded parallel byte-range transfer; compressed segments stay local.

Four fixed contiguous segments per object; shared hard budgets account all
received bytes and all request attempts. Final SHA is over ordered object bytes.
"""
import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .flatfile_cache import (Resources, atomic_json, client, head, location,
                            object_identity, partial, resume_prefix)
from .storage import file_hash
from .temporal_design import read
from datetime import datetime, timezone


class SharedResources(Resources):
    def __init__(self, config, root):
        super().__init__(config, root)
        self.lock = threading.RLock()
        self.reserved = 0
    def claim(self, n):
        with self.lock:
            self.check()
            if self.state['downloaded_bytes']+self.reserved+n > self.config['max_download_bytes']:
                raise RuntimeError('RESERVED_DOWNLOAD_BUDGET')
            self.request(); self.reserved += n
    def received(self, n):
        with self.lock:
            self.reserved -= n; self.state['downloaded_bytes'] += n; self.save(); self.check()
    def release(self, n):
        with self.lock:self.reserved -= n; self.save()


def segment(c, cfg, meta, resources, path, checkpoint, start, end):
    offset, h = resume_prefix(path, checkpoint)
    if offset > end-start:raise ValueError('Oversized segment')
    left = end-start-offset
    if not left:return path
    resources.claim(left)
    response = None
    try:
        response = c.get_object(Bucket=cfg['bucket'], Key=meta['key'],
            Range=f'bytes={start+offset}-{end-1}', IfMatch=meta['etag'])
        if response['ResponseMetadata']['HTTPStatusCode'] != 206 or response.get('ETag') != meta['etag'] or response['ContentLength'] != left:
            raise ValueError('Segment range/source identity mismatch')
        if response.get('ContentRange') != f'bytes {start+offset}-{end-1}/{meta["size"]}':
            raise ValueError('Segment ContentRange mismatch')
        with path.open('ab') as f:
            while left:
                with resources.lock:resources.check()
                chunk = response['Body'].read(min(cfg['chunk_bytes'], left))
                if not chunk:raise RuntimeError('INCOMPLETE_SOURCE_SEGMENT')
                f.write(chunk); h.update(chunk); offset += len(chunk); left -= len(chunk)
                f.flush()
                atomic_json(checkpoint, {'offset':offset,'prefix_sha256':h.hexdigest(),
                    'object_identity':object_identity(meta),'range_start':start,'range_end_exclusive':end})
                resources.received(len(chunk))
            f.flush(); os.fsync(f.fileno())
    finally:
        if response:response['Body'].close()
        resources.release(left)
    return path


def download_object(c, cfg, meta, resources):
    folder = location(meta); ident = object_identity(meta); entry = folder/'sources'/(ident+'.json')
    if entry.exists():
        saved=read(entry)
        if file_hash(saved['local_path']) != saved['sha256']:raise ValueError('Cached object hash mismatch')
        return saved
    parts = folder/'partial'/(ident+'-segments'); parts.mkdir(parents=True, exist_ok=True)
    ranges = [(i*meta['size']//4, (i+1)*meta['size']//4) for i in range(4)]
    original, old_checkpoint = partial(meta)
    if old_checkpoint.exists() and original.exists() and not (parts/'0.part').exists():
        if read(old_checkpoint)['offset'] > ranges[0][1]:raise ValueError('Probe exceeds first fixed segment')
        os.replace(original, parts/'0.part'); os.replace(old_checkpoint, parts/'0.json')
    print('DOWNLOADING '+meta['dataset']+' '+meta['date']+' '+str(meta['size']),flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs=[pool.submit(segment,c,cfg,meta,resources,parts/(str(i)+'.part'),parts/(str(i)+'.json'),a,b) for i,(a,b) in enumerate(ranges)]
        for job in jobs:job.result()
    current=head(c,cfg,meta,resources)
    if object_identity(current)!=ident:raise ValueError('Source changed while downloading; segments preserved')
    merged=parts/'assembled.csv.gz'; h=hashlib.sha256()
    with merged.open('wb') as out:
        for i in range(4):
            with (parts/(str(i)+'.part')).open('rb') as f:
                while chunk:=f.read(cfg['chunk_bytes']):
                    resources.check();out.write(chunk);h.update(chunk)
    if merged.stat().st_size!=meta['size']:raise ValueError('Assembled size mismatch')
    sha=h.hexdigest();dest=folder/'snapshots'/(sha+'.csv.gz');dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():
        if file_hash(dest)!=sha:raise ValueError('Existing content-addressed snapshot corrupt')
        merged.unlink()
    else:os.replace(merged,dest)
    record={**meta,'bucket':cfg['bucket'],'endpoint':cfg['endpoint'],'object_identity':ident,
            'sha256':sha,'local_path':str(dest),'downloaded_at':datetime.now(timezone.utc).isoformat(),
            'complete':True,'range_segments':4,'etag_not_content_md5':True}
    atomic_json(entry,record)
    # Source snapshot is immutable; completed resumable fragments are expendable.
    for i in range(4):
        (parts/(str(i)+'.part')).unlink();(parts/(str(i)+'.json')).unlink()
    resources.save();print('COMPLETE '+meta['dataset']+' '+meta['date']+' '+sha,flush=True)
    return record


def main():
    import argparse
    from .flatfile_cache import CONFIG
    p=argparse.ArgumentParser();p.add_argument('--config',default=CONFIG);p.add_argument('--credentials-file');a=p.parse_args()
    cfg=read(a.config);root=Path('data/runs',cfg['run_id']);resources=SharedResources(cfg,root)
    assert file_hash(a.config)==read(root/'plan-freeze.json')['config_sha256']
    c=client(cfg,a.credentials_file);sources=[]
    state_path=root/'acquisition-attempt-state.json'
    previous=read(state_path) if state_path.exists() else {'attempt':1}
    attempt=previous['attempt']+1
    atomic_json(state_path,{'attempt':attempt,'status':'RUNNING','code_sha256':file_hash(__file__)})
    try:
        for meta in cfg['objects']:
            sources.append(download_object(c,cfg,meta,resources))
            atomic_json(root/'downloaded-sources.json',sources)
    except Exception as exc:
        atomic_json(state_path,{'attempt':attempt,'status':'STOPPED','code_sha256':file_hash(__file__)})
        atomic_json(root/('acquisition-stop-attempt-'+str(attempt)+'.json'),{'status':'INCOMPLETE','error_type':type(exc).__name__,
            'reason':str(exc) if isinstance(exc,(RuntimeError,ValueError)) else 'S3_OR_IO_ERROR_REDACTED','resources':resources.state})
        raise RuntimeError('Bounded S3 transfer stopped; see sanitized acquisition-stop.json') from None
    else:atomic_json(state_path,{'attempt':attempt,'status':'COMPLETE','code_sha256':file_hash(__file__)})
    finally:resources.save()


if __name__=='__main__':main()
