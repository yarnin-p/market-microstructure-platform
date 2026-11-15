"""Finalize compact evidence after deterministic replay and full pytest validation."""
import json
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_lab.m2_report import validate_pilot
from market_lab.storage import write_json,file_hash,digest
from market_lab.m2_report import records
from decimal import Decimal

if __name__ == '__main__':
    run_id=sys.argv[1]
    evidence=validate_pilot(run_id)
    events=records(Path('data/runs',run_id,'events/events.parquet'))
    for event in events:
        source=json.loads(event['source_json'])
        raw=json.loads(Path(source['path']).read_text())['results'][source['row']]
        assert digest(raw)==event['record_id']
        price_raw=raw
        if event.get('restoration_source'):
            restore=json.loads(event['restoration_source'])
            assert file_hash(restore['path'])==restore['sha256']
            price_raw=json.loads(Path(restore['path']).read_text())['results'][restore['row']]
        assert Decimal(str(price_raw['price']))==Decimal(event['touch_price'])
        quote=event.get('quote',{})
        if quote.get('source_json'):
            qs=json.loads(quote['source_json'])
            assert file_hash(qs['path'])==qs['sha256']
            qr=json.loads(Path(qs['path']).read_text())['results'][qs['row']]
            assert qr['sip_timestamp']==quote['sip_timestamp']<=event['event_timestamp']
            for field in ['bid','ask']:
                if quote[field] is not None:
                    assert Decimal(str(qr[field+'_price']))==Decimal(quote[field])
    evidence['raw_event_price_and_quote_checks']=len(events)
    result=subprocess.run([sys.executable,'-m','pytest','-q'],capture_output=True,text=True)
    if result.returncode: print(result.stdout+result.stderr);sys.exit(result.returncode)
    evidence['tests']=result.stdout
    root=Path('data/runs',run_id)
    execution=json.loads((root/'execution.json').read_text())
    evidence['code_hashes_match']=all(file_hash(p)==h for p,h in execution['code_hashes'].items())
    if not evidence['code_hashes_match']: raise ValueError('execution source changed')
    dest=Path('reports',run_id)
    write_json(dest/'validation.json',evidence)
    p=dest/'summary.json';summary=json.loads(p.read_text());old_summary=json.dumps(summary,indent=2);summary['statuses']['ENGINEERING_VALIDATED']=True
    write_json(p,summary)
    report=dest/'report.md'
    report.write_text(report.read_text().replace(old_summary,json.dumps(summary,indent=2))+'\n## Executed validation\n\n'+json.dumps(evidence,indent=2)+'\n')
    p=dest/'manifest.json';m=json.loads(p.read_text())
    m['artifacts']={p.name:{'sha256':file_hash(p),'bytes':p.stat().st_size} for p in sorted(dest.iterdir()) if p.is_file() and p.name not in {'manifest.json','research_bundle.zip'}}
    m['storage_bytes']={'run':sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),
                        'compact_uncompressed':sum(p.stat().st_size for p in dest.iterdir() if p.is_file() and p.suffix!='.zip')}
    write_json(p,m)
    with zipfile.ZipFile(dest/'research_bundle.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(dest.iterdir()):
            if p.is_file() and p.name!='research_bundle.zip':z.write(p,p.name)
    print(json.dumps({'validation':{k:v for k,v in evidence.items() if k!='tests'},'summary':summary,'storage_bytes':m['storage_bytes']},indent=2))
