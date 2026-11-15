"""Assemble methodology, observed findings and all ten cycles in one bundle."""
import argparse
import re
import shutil
from pathlib import Path

from market_lab.confirmation_pilot import package, read
from market_lab.m2_report import records
from market_lab.storage import file_hash, write_json
from scripts.analyze_confirmation import analyze


def finalize(pytest_output=None):
    config = read('configs/task-003-confirmation-v1.json')
    root = Path('data/runs', config['run_id'])
    dest = Path('reports', config['run_id'])
    frozen = read(root / 'execution.json')
    assert frozen['config'] == config
    assert all(file_hash(p) == h for p,h in frozen['code_hashes'].items())
    assert read(dest/'validation.json')['status'] == 'PASS'
    assert read(dest/'resume-validation.json')['status'] == 'PASS'
    test_hashes = {str(p):file_hash(p) for p in sorted(Path('tests').glob('*.py'))}
    if pytest_output:
        text = Path(pytest_output).read_text()
        passed = re.search(r'(?m)^(\d+) passed, (\d+) warnings in [^\n]+$', text)
        if not passed:
            raise ValueError('Expected a successful full pytest summary')
        write_json(dest/'tests.json',{'status':'PASS','passed':int(passed[1]),'warnings':int(passed[2]),
            'command':'python -m pytest -q','warning_scope':'Existing pandas deprecation warnings',
            'test_source_hashes':test_hashes})
    tests = read(dest/'tests.json')
    assert tests['status']=='PASS' and tests['test_source_hashes']==test_hashes, 'Tests changed; rerun pytest and pass --pytest-output'
    analyze(config)
    assert read(dest/'event-level-results.json')['records'] == records(root/'events/event_results.parquet')
    documents = {'docs/plans/TASK-003-price-confirmation.md':'methodology.md',
                 'docs/research/task-003-price-confirmation-pilot.md':'findings-th.md'}
    for source, name in documents.items():
        shutil.copyfile(source, dest/name)
    write_json(dest/'finalization.json',{'status':'PASS','finalizer_sha256':file_hash(__file__),
        'analysis_sha256':file_hash('scripts/analyze_confirmation.py'),
        'documents':{p:file_hash(p) for p in documents},'all_event_json_equals_parquet':True,
        'execution_sha256':file_hash(root/'execution.json'),
        'risk_set':40,'event_policy_condition_rows':240,'primary_c0_equivalence':True,
        'note':'Run integrity and deterministic source replay receipts are separate from packaging checks.'})
    selection=read(Path('data/runs',config['source_run'],'selection.json'))
    package(config, root, dest, selection)
    manifest=read(dest/'manifest.json')
    schema=read('schemas/research-bundle-v1.json')
    assert set(schema['required']) <= set(manifest)
    assert set(schema['properties']['files']['required']) <= set(manifest['files'])
    return read(dest/'bundle-validation.json')


if __name__=='__main__':
    import json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pytest-output',help='Captured successful full pytest output; required when test sources change')
    args=parser.parse_args()
    print(json.dumps(finalize(args.pytest_output),indent=2))
