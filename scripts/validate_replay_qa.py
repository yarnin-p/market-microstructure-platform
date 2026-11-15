"""Independent read-only validation of TASK 002.1 artifacts and source chains."""
import json
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

from market_lab.api import safe_url
from market_lab.m2_report import records
from market_lab.replay_qa import roots, verify_integrity
from market_lab.storage import digest, file_hash, write_json


def validate_chain(coverage):
    checked = 0
    prior_next = None
    last_stamp = 0
    for index, page in enumerate(coverage['pages']):
        assert file_hash(page['path']) == page['sha256'], 'page checksum mismatch'
        request = page['request']
        if index == 0:
            assert request['url'].endswith('/v3/trades/' + coverage['request']['ticker'])
            assert int(request['params']['timestamp.gt']) == coverage['request']['start_ns']
            assert int(request['params']['timestamp.lte']) == coverage['request']['end_ns']
            assert request['params']['order'] == 'asc'
        else:
            url = safe_url(prior_next)
            assert request == {'url': url.split('?',1)[0], 'params': dict(parse_qsl(urlparse(url).query))}, 'broken cursor chain'
        body = json.loads(Path(page['path']).read_text())
        stamps = [r['sip_timestamp'] for r in body['results']]
        assert stamps == sorted(stamps)
        if stamps:
            assert stamps[0] >= last_stamp and stamps[-1] <= coverage['request']['end_ns']
            assert stamps[0] > coverage['request']['start_ns']
            last_stamp = stamps[-1]
        prior_next = body.get('next_url')
        checked += 1
    assert not coverage['complete'] or prior_next is None, 'partial window falsely complete'
    assert coverage['raw_rows'] == sum(p['rows'] for p in coverage['pages'])
    return checked


def run():
    config = json.loads(Path('configs/task-002-1-qa-v1.json').read_text())
    base, root, dest = roots(config)
    execution = json.loads((root/'execution.json').read_text())
    assert execution['config'] == config
    for path, h in execution['code_hashes'].items():
        assert file_hash(path) == h, 'execution code drift'
    verify_integrity(config, execution)
    chain_pages = sum(validate_chain(json.loads(p.read_text())) for p in (root/'repairs').glob('*/*/coverage.json'))
    old_events = records(base/'events/events.parquet')
    old_outcomes = records(base/'outcomes/outcomes.parquet')
    events = records(root/'events/events.parquet')
    outcomes = records(root/'outcomes/outcomes.parquet')
    opportunities = records(root/'opportunities/opportunities.parquet')
    assert len({(e['variant'],e['condition_policy'],e['event_id']) for e in events})==len(events)
    legacy = [e for e in events if e['variant']=='QA_UNREPAIRED' and e['condition_policy']=='LEGACY_BOTH']
    assert len(legacy)==len(old_events)==20
    old_by_pair={(e['security_id'],e['cycle_id']):e for e in old_events}
    new_by_id={(e['variant'],e['condition_policy'],e['event_id']):e for e in events}
    old_out_by_pair={(e['security_id'],e['cycle_id']):e for e in old_outcomes}
    for e in legacy:
        old=old_by_pair[(e['security_id'],e['cycle_id'])]
        assert all(e[k]==old[k] for k in ['record_id','event_timestamp','touch_price','threshold_price'])
    legacy_out=[r for r in outcomes if r['variant']=='QA_UNREPAIRED' and r['condition_policy']=='LEGACY_BOTH' and r['gap_policy']=='GAP_300_SECONDS']
    for r in legacy_out:
        old=old_out_by_pair[(r['security_id'],r['cycle_id'])]
        assert all(r[k]==old[k] for k in ['forward','barriers','observed_mfe','observed_mae','excursion_censored']), 'baseline outcome changed'
    for event in events:
        source=json.loads(event['source_json'])
        raw=json.loads(Path(source['path']).read_text())['results'][source['row']]
        assert digest(raw)==event['record_id'] and raw['sip_timestamp']==event['event_timestamp']
        assert event['strict_full_cycle_first_verified'] is False
    for outcome in outcomes:
        assert (outcome['variant'],outcome['condition_policy'],outcome['event_id']) in new_by_id
        assert all(m['return'] is None for m in outcome['forward'] if m['censored'])
    repaired=[o for o in opportunities if o['variant']=='QA_REPAIRED' and o.get('condition_policy')=='HIGH_LOW_ONLY']
    assert len(repaired)==45 and all(o['complete_observed_sessions'] for o in repaired)
    assert all(not o['strict_full_cycle_opportunity_eligible'] for o in repaired)
    ledger=json.loads((root/'raw/request-ledger.json').read_text())
    assert len(ledger['attempts']) <= config['max_requests'] and ledger['pages'] <= config['max_pages']
    assert ledger['decoded_bytes'] <= config['max_decoded_bytes']
    audit=json.loads((dest/'raw-nbbo-audit.json').read_text())
    assert {a['ticker'] for a in audit}=={'HOTH','SNGX','DBGI'}
    assert all(a['status']=='RAW_TRADE_AND_NBBO_HASH_VERIFIED' and not a['executable_fill_claim'] for a in audit)
    requested=json.loads((dest/'requested-raw-nbbo-audit.json').read_text())
    originals=json.loads((Path('reports')/config['baseline_run']/'verified-audit-examples.json').read_text())
    assert len(requested)==len(originals)==3
    for old, example in zip(originals,requested):
        assert (old['ticker'],old['cycle_id'],old['event_id']) == (example['ticker'],example['cycle_id'],example['baseline_event_id'])
        assert example['same_as_original_audit_record'] and not example['executable_fill_claim']
        assert not example['future_quotes_used_for_trigger']
        for key in ['trade_source','quote_source']:
            source=example[key]
            assert file_hash(source['path'])==source['sha256']
        assert digest(example['raw_trade'])==old['record_id']
    exported=json.loads((dest/'event-level-results.json').read_text())
    assert exported['events']==events and exported['outcomes']==outcomes and exported['opportunities']==opportunities
    result={'status':'PASS','baseline_unchanged':True,'m1_unchanged':True,'legacy_events_exactly_reproduced':20,
            'legacy_outcomes_exactly_reproduced':len(legacy_out),'repaired_cursor_chain_pages':chain_pages,
            'complete_repaired_opportunities':45,'strict_full_cycle_opportunities':0,
            'all_revised_events_source_linked':len(events),'outcome_records_checked':len(outcomes),
            'new_requests':len(ledger['attempts']),'new_pages':ledger['pages'],'new_decoded_bytes':ledger['decoded_bytes'],
            'raw_nbbo_examples_verified':3,'original_published_audit_examples_verified':3,
            'full_json_export_matches_parquet':True,'validator_sha256':file_hash(__file__)}
    write_json(dest/'validation.json',result)
    return result


if __name__=='__main__':
    print(json.dumps(run(),indent=2))
