"""Freeze the same bounded two-day audit pilot using fresh S3 HEAD metadata.

No payload download. No overwrite. Credentials never enter the new config.
Use this only for a separately authorized rerun with a new config/run ID.
"""
import argparse
import json
import shutil
import subprocess
import time
from datetime import datetime,timezone
from pathlib import Path

from market_lab.flatfile_cache import CONFIG, atomic_json, client
from market_lab.storage import file_hash
from market_lab.temporal_design import protected_hashes, read

CANDIDATES=[('quotes','2026-05-28'),('quotes','2026-05-29'),('quotes','2026-06-03'),
            ('quotes','2026-06-08'),('quotes','2026-06-09'),('trades','2026-05-28'),('trades','2026-05-29')]


def prepare(template,run_id,output_config,credentials_file=None):
    cfg=read(template);root=Path('data/runs',run_id);output=Path(output_config)
    if root.exists() or output.exists():raise ValueError('New run ID and output config required')
    if not run_id.startswith('m3-s3-') or '/' in run_id:raise ValueError('Invalid pilot run ID')
    if shutil.disk_usage('.').free<cfg['min_disk_free_bytes']:raise RuntimeError('DISK_PREFLIGHT_BUDGET')
    c=client(cfg,credentials_file);objects=[]
    for dataset,date in CANDIDATES:
        key=f'us_stocks_sip/{dataset}_v1/{date[:4]}/{date[5:7]}/{date}.csv.gz'
        started=time.monotonic()
        try:
            r=c.head_object(Bucket=cfg['bucket'],Key=key)
            objects.append({'dataset':dataset,'date':date,'key':key,'size':r['ContentLength'],
                'etag':r['ETag'],'last_modified':r['LastModified'].isoformat(),
                'status':r['ResponseMetadata']['HTTPStatusCode'],'seconds':time.monotonic()-started})
        except Exception as exc:
            # Do not print SDK exception/request structures.
            raise RuntimeError('S3_METADATA_PREFLIGHT_FAILED:'+type(exc).__name__) from None
    selected=[o for o in objects if (o['dataset'],o['date']) in [('quotes','2026-05-28'),('quotes','2026-05-29'),('trades','2026-05-28')]]
    if any(r['status']!=200 for r in selected):raise RuntimeError('SOURCE_METADATA_NOT_ACCESSIBLE')
    if sum(o['size'] for o in selected)>cfg['max_download_bytes']:raise RuntimeError('PLANNED_DOWNLOAD_BUDGET')
    # Conservative raw-transfer staging bound before any selected outputs.
    if sum(o['size'] for o in selected)+max(o['size'] for o in selected)>cfg['max_storage_bytes']:raise RuntimeError('PLANNED_STAGING_BUDGET')
    cfg={**cfg,'run_id':run_id,'objects':selected,'baseline_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()}
    root.mkdir(parents=True)
    atomic_json(root/'metadata-probe.json',{'objects':objects,'head_requests':7,'downloaded_bytes':0,
        'disk_free_bytes':shutil.disk_usage('.').free,'time_utc':datetime.now(timezone.utc).isoformat()})
    atomic_json(output,cfg)
    atomic_json(root/'protected.json',protected_hashes(run_id))
    atomic_json(root/'plan-freeze.json',{'config_sha256':file_hash(output),'metadata_sha256':file_hash(root/'metadata-probe.json'),
        'total_planned_compressed_bytes':sum(o['size'] for o in selected),'marketwide_dates':2,'objects':3,
        'state_policy_frozen_before_download':cfg['state_policy'],'preparation_code_sha256':file_hash(__file__)})
    return {'run_id':run_id,'HEAD_requests':7,'payload_bytes':0,'planned_bytes':sum(o['size'] for o in selected)}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--template',default=CONFIG);p.add_argument('--run-id',required=True)
    p.add_argument('--output-config',required=True);p.add_argument('--credentials-file');a=p.parse_args()
    print(json.dumps(prepare(a.template,a.run_id,a.output_config,a.credentials_file),indent=2))
