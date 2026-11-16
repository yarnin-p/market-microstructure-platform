"""Mandatory independent gzip CRC/length proof for fast CSV readers.

DuckDB 2.0 rejects truncated gzip but can ignore a CRC32 mismatch. Therefore a
successful CSV parse is not a gzip-integrity certificate. This streamed pass
counts exact decoded bytes without retaining or writing the market-wide CSV.
"""
import argparse
import fcntl
import subprocess
import time
from pathlib import Path

from .flatfile_cache import CONFIG, atomic_json, location, object_identity
from .storage import file_hash
from .temporal_design import read


def _verify_gzip_locked(source, config):
    path=location(source)/'integrity'/(source['sha256']+'.json')
    if path.exists():
        proof=read(path)
        if proof['source_sha256']!=source['sha256'] or not proof['crc_validated']:raise ValueError('Invalid cached gzip proof')
        return proof
    started=time.monotonic();decoded=0
    process=subprocess.Popen(['/usr/bin/gzip','-dc','--',source['local_path']],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        while True:
            if time.monotonic()-started>config['max_active_seconds'] or time.time()>config.get('_execution_deadline_utc',float('inf')):
                raise RuntimeError('INTEGRITY_EXECUTION_BUDGET')
            chunk=process.stdout.read(1024*1024)
            if not chunk:break
            decoded+=len(chunk)
            if decoded>config['max_decoded_bytes']:raise RuntimeError('INTEGRITY_DECODED_BUDGET')
        remaining=max(.1,config['max_active_seconds']-(time.monotonic()-started))
        status=process.wait(timeout=remaining)
        if status!=0:raise ValueError('GZIP_CRC_OR_LENGTH_VALIDATION_FAILED')
    finally:
        if process.poll() is None:process.kill();process.wait()
        process.stdout.close();process.stderr.close()
    result={'source_sha256':source['sha256'],'source_key':source['key'],'source_size':Path(source['local_path']).stat().st_size,
        'decoded_bytes_exact':decoded,'crc_validated':True,'complete':True,'validator':'/usr/bin/gzip -dc; complete EOF and exit0',
        'elapsed_seconds':time.monotonic()-started,'code_sha256':file_hash(__file__),'raw_csv_materialized':False}
    atomic_json(path,result);return result


def verify_gzip(source, config):
    folder=location(source)/'integrity';folder.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    with (folder/(source['sha256']+'.lock')).open('a') as lock:
        while True:
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                if time.monotonic()-started>config['max_active_seconds'] or time.time()>config.get('_execution_deadline_utc',float('inf')):
                    raise RuntimeError('INTEGRITY_LOCK_BUDGET')
                time.sleep(.1)
        return _verify_gzip_locked(source,config)


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',default=CONFIG);a=p.parse_args();config=read(a.config)
    root=Path('data/runs',config['run_id']);ledger=root/'resource-ledger.json';started=time.monotonic()
    config={**config,'_execution_deadline_utc':ledger.stat().st_mtime+config['max_active_seconds']-read(ledger)['active_seconds']}
    proofs=[]
    for meta in config['objects']:
        source_path=location(meta)/'sources'/(object_identity(meta)+'.json')
        while not source_path.exists():
            if time.time()>config['_execution_deadline_utc']:raise RuntimeError('SHARED_INTEGRITY_EXECUTION_BUDGET')
            if (root/'acquisition-attempt-state.json').exists() and read(root/'acquisition-attempt-state.json')['status']=='STOPPED':raise RuntimeError('ACQUISITION_STOPPED_INCOMPLETE')
            time.sleep(5)
        proof=verify_gzip(read(source_path),config);proofs.append(proof)
        atomic_json(root/'gzip-integrity.json',{'sources':proofs,'decoded_bytes_exact':sum(r['decoded_bytes_exact'] for r in proofs),
            'elapsed_seconds':time.monotonic()-started,'complete':len(proofs)==len(config['objects'])})
        print(meta['dataset'],meta['date'],'CRC_PASS',proof['decoded_bytes_exact'],flush=True)


if __name__=='__main__':main()
