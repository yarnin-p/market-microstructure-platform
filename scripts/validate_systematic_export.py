"""Independent denominator, historical-gate and complete export consistency checks."""
import json
import sys
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_lab.m2_pilot import control_eligible,source_rows
from market_lab.m2_report import records
from market_lab.storage import write_json,file_hash

if __name__=='__main__':
    config=json.loads(Path('configs/task-002-2-systematic-v1.json').read_text())
    root=Path('data/runs',config['run_id']);dest=Path('reports',config['run_id'])
    selection=json.loads((root/'selection.json').read_text())
    tables={name:records(root/name/(name+'.parquet')) for name in ['events','outcomes','opportunities']}
    exported=json.loads((dest/'event-level-results.json').read_text())
    assert tables==exported,'full JSON export differs from Parquet'
    selected={(o['cycle_id'],o['security_id']):o for o in selection['selected']}
    expected={(c,s,p) for c,s in selected for p in config['condition_policies']}
    actual={(o['cycle_id'],o['security_id'],o['condition_policy']) for o in tables['opportunities']}
    assert actual==expected and len(actual)==len(tables['opportunities'])
    events={(e['cycle_id'],e['security_id'],e['condition_policy']):e for e in tables['events']}
    assert len(events)==len(tables['events'])
    for o in tables['opportunities']:
        key=(o['cycle_id'],o['security_id'],o['condition_policy']);e=events.get(key)
        assert o['event_id']==(e['event_id'] if e else None)
        assert o['zero_event_observed']==(o['observed_opportunity_eligible'] and e is None)
        if e:assert e['observed_sessions_first_verified']==o['observed_opportunity_eligible']
        src=selected[key[:2]]
        assert o['selection_probability']==src['sample_n']/src['population_N']
        assert o['sampling_weight']==src['population_N']/src['sample_n']
    for c in selection['calendar']:
        rows,_=source_rows(config['source_m1_run'],c['cycle_id'])
        index={r['record_id']:r for r in rows}
        for o in selection['selected']:
            if o['cycle_id']!=c['cycle_id']:continue
            r=index[o['m1_record_id']]
            assert control_eligible(r) and r['security_id']==o['security_id'] and r['ticker']==o['ticker']
            assert str(r['previous_rth_close'])==o['previous_rth_close']
    manifest=json.loads((dest/'manifest.json').read_text())
    with zipfile.ZipFile(dest/'research_bundle.zip') as z:
        assert z.testzip() is None
        for name,meta in manifest['artifacts'].items():
            import hashlib
            assert file_hash(dest/name)==meta['sha256']==hashlib.sha256(z.read(name)).hexdigest()
    result={'status':'PASS','historical_opportunities_checked':len(selected),'policy_opportunities':len(actual),
            'event_policy_records':len(events),'outcomes':len(tables['outcomes']),'full_json_equals_parquet':True,
            'zero_event_denominators_preserved':True,'zip_and_manifest_hashes_verified':True}
    write_json(dest/'export-validation.json',result)
    from market_lab.systematic_report import package
    package(config,root,dest)
    print(json.dumps(result,indent=2))
