import json
import pytest
from market_lab.audit_supplement import calibration_clearance, freshness_witness, verify_manifest, SCENARIOS
from market_lab.audit_paths import S, quote_mark, pages
from market_lab.preholdout_audit import Budget
from market_lab.storage import file_hash


def trade(t, conditions=None):
    return {'sip_timestamp': t, 'participant_timestamp': t, 'price': '1', 'size': 100,
            'conditions': conditions or [], '_source': {'row': 1}}


def test_calibration_cannot_discard_failed_rare_scenario():
    data = [dict(scenario=s, coverage_all_replicates=.95, replicates=1000,
                 valid_intervals=1000, synthetic_only=True) for s in SCENARIOS]
    assert calibration_clearance(data)['status'] == 'PASS'
    rare = next(r for r in data if r['scenario'] == 'rare_domain')
    rare['coverage_all_replicates'] = .915
    assert calibration_clearance(data)['status'] == 'BLOCKED'
    assert calibration_clearance([r for r in data if r != rare])['status'] == 'BLOCKED'
    assert not calibration_clearance(data)['holdout_authorized']


def test_complete_provider_silence_vs_filtered_messages_vs_closed_window():
    bounds = (0, 10*S, 20*S, 30*S, 1000*S)
    mark = {'target_ns': 500*S, 'horizon': '5m', 'mark': {'sip_timestamp': 300*S}}
    assert freshness_witness([], mark, bounds, {}, 10)['classification'] == 'NO_RETURNED_MESSAGES_IN_RECENT_WINDOW'
    out = freshness_witness([trade(490*S, [22])], mark, bounds, {}, 10)
    assert out['classification'] == 'RECENT_RETURNED_MESSAGES_ALL_REJECTED'
    assert out['eligible_recent'] == 0
    assert out['rejections'] == {'OUT_OF_SEQUENCE_OR_REFERENCE_PRICE': 1}
    out = freshness_witness([trade(490*S)], mark, bounds, {}, 10)
    assert out['classification'] == 'RECENT_ELIGIBLE_PRINT'
    out = freshness_witness([], {**mark, 'target_ns': 1001*S}, bounds, {}, 10)
    assert out['classification'] == 'TARGET_AFTER_OBSERVED_CYCLE' and out['raw_recent'] is None


def test_session_end_does_not_borrow_next_session_opening_trade():
    bounds = (0, 100*S, 200*S, 300*S, 1000*S)
    mark = {'target_ns': 300*S, 'horizon': 'session_end', 'mark': {'sip_timestamp': 220*S}}
    out = freshness_witness([trade(300*S)], mark, bounds, {}, 10)
    assert out['eligible_recent'] == 0


def test_quote_never_uses_future_or_stale_support():
    cfg = {'max_quote_age_seconds': 5}
    q = {'sip_timestamp': 10*S, 'bid_price': 1, 'ask_price': 1.1, 'bid_size': 100,
         'ask_size': 100, '_source': {}}
    coverage = [{'complete': True, 'request': {'start_ns': 0, 'end_ns': 100*S}}]
    assert quote_mark([q], coverage, 10*S-1, cfg)['status'] == 'MISSING'
    assert quote_mark([q], coverage, 10*S, cfg)['status'] == 'OK'
    assert 'STALE' in quote_mark([q], coverage, 15*S+1, cfg)['flags']


def test_strict_manifest_rejects_missing_not_just_changed_sources(tmp_path):
    (tmp_path/'manifest.json').write_text(json.dumps({'files': {'missing.json': {'sha256': 'x'}}}))
    with pytest.raises(ValueError, match='Missing or changed'): verify_manifest(tmp_path)


def test_raw_timestamp_nanoseconds_and_terminal_pagination(tmp_path):
    t = 1781208669390366694
    p = tmp_path/'raw.json'
    p.write_text(json.dumps({'results': [{'sip_timestamp': t, 'price': 1}]}))
    coverage = {'complete': True, 'request': {'start_ns': t-1, 'end_ns': t},
                'pages': [{'path': str(p), 'sha256': file_hash(p)}]}
    budget = Budget({'max_wall_seconds': 10, 'max_raw_bytes': 100000, 'max_window_rows': 10})
    assert pages(coverage, budget)[0][0]['sip_timestamp'] == t
    p.write_text(json.dumps({'results': [], 'next_url': 'https://example.org/next'}))
    coverage['pages'][0]['sha256'] = file_hash(p)
    with pytest.raises(AssertionError, match='terminal'): pages(coverage, budget)
