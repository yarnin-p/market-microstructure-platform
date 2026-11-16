"""Prepare a new authorized pilot and bind code before any payload download.

The metadata utility and this freeze wrapper are separate so neither silently
rewrites an existing run. This command performs seven HEAD requests only.
"""
import argparse
import json
from pathlib import Path

from scripts.prepare_flatfile_pilot import prepare
from market_lab.flatfile_cache import CONFIG, atomic_json
from market_lab.storage import file_hash


def bootstrap(template,run_id,output_config,credentials_file=None):
    result=prepare(template,run_id,output_config,credentials_file)
    root=Path('data/runs',run_id)
    paths=['market_lab/flatfile_ingest.py','market_lab/flatfile_ingest_duckdb.py',
           'market_lab/flatfile_integrity.py','market_lab/flatfile_revalidation.py',
           'market_lab/flatfile_reconcile.py','market_lab/quote_state.py',__file__]
    atomic_json(root/'analysis-code-freeze.json',{'before_s3_outcomes':True,
        'hashes':{p:file_hash(p) for p in paths},'bootstrap_config_sha256':file_hash(output_config),
        'provider_session_basis':'America/New_York04:00-20:00; preserve source spill/context'})
    atomic_json(root/'acquisition-code.json',{p:file_hash(p) for p in ['market_lab/flatfile_cache.py','market_lab/flatfile_transfer.py']})
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--template',default=CONFIG);p.add_argument('--run-id',required=True)
    p.add_argument('--output-config',required=True);p.add_argument('--credentials-file');a=p.parse_args()
    print(json.dumps(bootstrap(a.template,a.run_id,a.output_config,a.credentials_file),indent=2))
