import gzip
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pyarrow.parquet as pq
import pytest

from market_lab.flatfile_cache import Resources, object_identity, resume_prefix, transfer
from market_lab.flatfile_ingest import ingest_source
from market_lab.flatfile_revalidation import codes
from market_lab.quote_state import QuoteState, state_confirmation
from market_lab.storage import file_hash
from market_lab.tick_replay import SECOND as S

CYCLE={'cycle_id':'test','anchor_at':'2026-05-27T20:00:00+00:00','afterhours_end':'2026-05-28T00:00:00+00:00',
       'premarket_start':'2026-05-28T08:00:00+00:00','rth_open':'2026-05-28T13:30:00+00:00','end_at':'2026-05-28T20:00:00+00:00'}
BASE=1779975000000000000  # 2026-05-28 13:30 UTC
CFG={'c2_deadline_seconds':60,'max_state_age_seconds':60,'c2_min_span_seconds':10}


def q(t,bid='1.10',ask='1.11',conditions='[]',size='100',seq=1):
    return {'sip_timestamp':t,'record_id':str(t)+bid+conditions+str(seq),'sequence_number':seq,
            'bid_price':bid,'ask_price':ask,'bid_size':size,'ask_size':size,'conditions_json':conditions,
            'indicators_json':'[]','normalization_status':'OK','source_json':'{}'}


def stream(quotes,complete=True):
    return QuoteState(quotes,[{'start_ns':BASE-100*S,'end_ns':BASE+4000*S,'complete':complete}],CYCLE)


def signal(quotes):
    state=SimpleNamespace(eligible=[{'sip_timestamp':BASE,'record_id':'trade','price':'1.10','source_json':'{}'}])
    event={'event_timestamp':BASE,'threshold_price':'1.10'}
    return state_confirmation(stream(quotes),state,event,CYCLE,CFG)


def test_state_is_distinct_from_freshness_and_never_uses_future():
    replay=stream([q(BASE),q(BASE+20*S,bid='.9')])
    assert replay.asof(BASE-1)['status']=='NO_QUOTE_UPDATE_OBSERVED'
    mark=replay.asof(BASE+10*S)
    assert mark['valid'] and not mark['fresh'] and mark['quote_timestamp']==BASE
    assert replay.asof(BASE+61*S)['valid'] is True  # latest update is 41s old
    assert not stream([q(BASE)]).asof(BASE+60*S+1)['valid']
    assert signal([q(BASE)])['signal_timestamp']==BASE+10*S


def test_invalidation_crossed_zero_corrected_and_missing_coverage_block_state():
    for invalid in [q(BASE+4*S,bid='1.2',ask='1.1'),q(BASE+4*S,size='0'),q(BASE+4*S,conditions='[81]')]:
        replay=stream([q(BASE),invalid])
        assert not replay.asof(BASE+5*S)['valid']
        assert signal([q(BASE),invalid])['status']!='CONFIRMED'
    assert stream([q(BASE)],False).asof(BASE)['status']=='SOURCE_COVERAGE_UNKNOWN'
    assert signal([q(BASE),q(BASE+5*S,bid='1.0'),q(BASE+7*S)])['signal_timestamp']==BASE+17*S


def test_session_reset_and_equal_timestamp_invalidation_precede_timer():
    before=q(BASE-1)  # PRE quote must not carry into RTH
    assert stream([before]).asof(BASE)['flags']==['SESSION_RESET']
    assert signal([before])['status']!='CONFIRMED'
    # An invalidation at the timer clock must prevent the earlier timer signal.
    assert signal([q(BASE),q(BASE+10*S,bid='1.0')])['status']!='CONFIRMED'
    # Same SIP group contains a below event then a new support: restart at that SIP.
    result=signal([q(BASE),q(BASE+10*S,bid='1.0',seq=2),q(BASE+10*S,seq=3)])
    assert result['signal_timestamp']==BASE+20*S


def test_same_sip_sequence_disagreement_invalidates_but_locked_is_explicit():
    r=stream([q(BASE),q(BASE,bid='1.2',ask='1.3')]).asof(BASE)
    assert not r['valid'] and 'AMBIGUOUS_SAME_SIP_SEQUENCE' in r['flags']
    r=stream([q(BASE,ask='1.10')]).asof(BASE)
    assert r['valid'] and r['locked']


def resource_config():
    return {'max_active_seconds':60,'max_download_bytes':100000,'max_decoded_bytes':10000000,
        'max_memory_bytes':2*1024**3,'min_disk_free_bytes':0,'max_storage_bytes':10000000,
        'max_selected_rows':1000,'max_requests':100,'chunk_bytes':3,'csv_block_bytes':256,
        'bucket':'flatfiles','endpoint':'https://example.invalid'}


class FakeS3:
    def __init__(self,data):self.data=data;self.etag='"v1"';self.calls=[]
    def get_object(self,**kw):
        self.calls.append(kw);lo,hi=map(int,kw['Range'][6:].split('-'));body=self.data[lo:hi+1]
        assert kw['IfMatch']==self.etag
        return {'Body':io.BytesIO(body),'ETag':self.etag,'ContentLength':len(body),
            'ContentRange':f'bytes {lo}-{hi}/{len(self.data)}','ResponseMetadata':{'HTTPStatusCode':206}}
    def head_object(self,**kw):
        return {'ContentLength':len(self.data),'ETag':self.etag,'LastModified':datetime(2026,5,29,tzinfo=timezone.utc)}


def test_resumable_source_identity_change_preserves_old_content_snapshot(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);cfg=resource_config();root=Path('run');root.mkdir();res=Resources(cfg,root)
    fake=FakeS3(b'abcdefghij')
    meta={'dataset':'quotes','date':'2026-05-28','key':'quotes/day.csv.gz','size':10,'etag':fake.etag,'last_modified':'2026-05-29T00:00:00+00:00'}
    first=transfer(fake,cfg,meta,res,probe_bytes=3)
    assert first['prefix_bytes']==3
    complete=transfer(fake,cfg,meta,res)
    assert Path(complete['local_path']).read_bytes()==b'abcdefghij'
    requests=len(fake.calls);transfer(fake,cfg,meta,res);assert len(fake.calls)==requests
    fake.data=b'ABCDEFGHIJ';fake.etag='"v2"';new={**meta,'etag':fake.etag}
    second=transfer(fake,cfg,new,res)
    assert second['local_path']!=complete['local_path']
    assert file_hash(complete['local_path'])==complete['sha256']
    assert object_identity(meta)!=object_identity(new)


def test_partial_corruption_and_hard_budget_do_not_become_complete(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);cfg=resource_config();root=Path('run');root.mkdir();res=Resources(cfg,root)
    res.state['requests']=cfg['max_requests']
    with pytest.raises(RuntimeError,match='REQUEST_BUDGET'):res.request()
    p=Path('part');p.write_bytes(b'wrong');cp=Path('checkpoint.json');cp.write_text(json.dumps({'offset':5,'prefix_sha256':'bad'}))
    with pytest.raises(ValueError,match='hash mismatch'):resume_prefix(p,cp)


def test_streaming_filter_preserves_nanoseconds_raw_fields_and_empty_partition(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);cfg=resource_config();root=Path('run');root.mkdir()
    raw='ticker,ask_price,bid_price,ask_size,bid_size,conditions,sequence_number,sip_timestamp,extra\n'
    raw+=f'AAA,1.001,1.000,12.5,14.25,"0,1",1,{BASE+123},keep\n'
    raw+=f'OTHER,2,1,10,10,,2,{BASE+456},skip\n'
    path=Path('source.gz')
    with gzip.open(path,'wb') as f:f.write(raw.encode())
    source={'dataset':'quotes','date':'2026-05-28','sha256':file_hash(path),'local_path':str(path),'key':'quote/day','complete':True}
    import time
    result=ingest_source(source,{'AAA':['id1'],'EMPTY':['id2']},cfg,root,time.monotonic(),{'decoded':0,'selected':0})
    assert result['complete'] and result['raw_rows']==2 and result['selected_rows']==1
    part=next(x for x in result['partitions'] if x['ticker']=='AAA');row=pq.ParquetFile(part['path']).read().to_pylist()[0]
    assert row['_sip_timestamp_ns']==BASE+123 and row['sip_timestamp']==str(BASE+123)
    assert row['bid_size']=='14.25' and row['extra']=='keep' and row['_source_row']==0
    assert next(x for x in result['partitions'] if x['ticker']=='EMPTY')['empty']
    again=ingest_source(source,{'AAA':['id1'],'EMPTY':['id2']},cfg,root,time.monotonic(),{'decoded':0,'selected':0})
    assert again==result


def test_conditions_are_explicit_and_not_silently_dropped():
    assert codes('81')==[81] and codes('0,1')==[0,1] and codes('[0, 1]')==[0,1]
    with pytest.raises(ValueError):codes('corrected')


def test_truncated_gzip_is_partial_and_never_a_complete_source(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);cfg=resource_config();root=Path('run');root.mkdir()
    path=Path('broken.gz')
    content=f'ticker,sip_timestamp,sequence_number\nAAA,{BASE},1\n'.encode()
    data=gzip.compress(content);path.write_bytes(data[:-5])
    source={'dataset':'quotes','date':'2026-05-28','sha256':file_hash(path),'local_path':str(path),'key':'quote/day','complete':True}
    import time
    with pytest.raises((EOFError,OSError)):
        ingest_source(source,{'AAA':['id1']},cfg,root,time.monotonic(),{'decoded':0,'selected':0})
    assert not list(Path('data/flatfiles').rglob('manifest.json'))
    assert list(Path('data/flatfiles').rglob('incomplete.json'))


def test_daily_spill_is_context_not_an_expansion_of_canonical_session_coverage():
    from market_lab.flatfile_revalidation import source_interval
    m={'source':{'date':'2026-05-28','key':'key','sha256':'sha'},'complete':True,'gzip_crc_validated':True,
       'rows_outside_object_utc_date':14500,'min_sip_timestamp':BASE-8*3600*S,'max_sip_timestamp':BASE+11*3600*S}
    interval=source_interval(m)
    assert interval['complete'] and interval['end_ns']==BASE+int(10.5*3600)*S-1
    assert interval['start_ns']==BASE-int(5.5*3600)*S-1
    m['min_sip_timestamp']=m['max_sip_timestamp']=BASE+3*86400*S
    assert not source_interval(m)['complete']


def test_future_invalidation_never_changes_an_already_available_timer_signal():
    original=signal([q(BASE)])
    future=signal([q(BASE),q(BASE+20*S,bid='.9')])
    assert original==future and original['signal_timestamp']==BASE+10*S


def test_frozen_event_rule_and_state_timer_are_distinct_without_changing_thresholds():
    from market_lab.confirmation import bid_confirmation
    event={'event_timestamp':BASE,'threshold_price':'1.10'}
    state=SimpleNamespace(eligible=[{'sip_timestamp':BASE,'record_id':'trade','price':'1.10','source_json':'{}'}])
    cfg={'c2_window_seconds':60,'c2_min_span_seconds':10,'max_quote_age_seconds':5,'max_mark_age_seconds':60}
    old=bid_confirmation(state,event,CYCLE,cfg,[q(BASE)],{'complete':True,'request':{'start_ns':BASE-1,'end_ns':BASE+60*S}})
    new=signal([q(BASE)])
    assert old['status']=='UNCONFIRMED' and new['status']=='CONFIRMED'
    assert not new['fresh_at_confirmation'] and new['timer_not_second_quote_update']


def test_parallel_fixed_ranges_assemble_original_bytes_with_shared_budget(tmp_path,monkeypatch):
    from market_lab.flatfile_transfer import SharedResources, download_object
    monkeypatch.chdir(tmp_path);cfg=resource_config();root=Path('run');root.mkdir()
    resources=SharedResources(cfg,root);fake=FakeS3(b'abcdefghijklmnopq')
    meta={'dataset':'quotes','date':'2026-05-28','key':'quotes/day.csv.gz','size':len(fake.data),'etag':fake.etag,'last_modified':'2026-05-29T00:00:00+00:00'}
    result=download_object(fake,cfg,meta,resources)
    assert Path(result['local_path']).read_bytes()==fake.data
    assert resources.state['downloaded_bytes']==len(fake.data) and resources.reserved==0
    assert len(fake.calls)==4 and result['range_segments']==4


def test_duckdb_streaming_backend_matches_arrow_rows_and_rejects_truncated_gzip(tmp_path,monkeypatch):
    import duckdb,time
    from market_lab.flatfile_ingest_duckdb import ingest_source as duck_ingest
    cfg=resource_config();cfg['max_decoded_bytes']=10000000
    source_path=tmp_path/'source.gz'
    text='ticker,ask_price,bid_price,ask_size,bid_size,conditions,sequence_number,sip_timestamp,extra\n'
    text+=f'AAA,1.001,1.000,12.5,14.25,"0,1",2,{BASE+123},keep\n'
    text+=f'OTHER,2,1,10,10,,3,{BASE+456},skip\n'
    text+=f'AAA,1.002,1.001,12.5,14.25,,1,{BASE+122},earlier\n'
    source_path.write_bytes(gzip.compress(text.encode()))
    source={'dataset':'quotes','date':'2026-05-28','sha256':file_hash(source_path),'local_path':str(source_path),'key':'quote/day','complete':True}
    output=[]
    for name,func in [('arrow',ingest_source),('duck',duck_ingest)]:
        folder=tmp_path/name;folder.mkdir();monkeypatch.chdir(folder);root=folder/'run';root.mkdir()
        m=func(source,{'AAA':['id1'],'EMPTY':['id2']},cfg,root,time.monotonic(),{'decoded':0,'selected':0})
        part=next(p for p in m['partitions'] if p['ticker']=='AAA')
        output.append(pq.ParquetFile(part['path']).read().to_pylist())
        assert m['complete'] and m['raw_rows']==3 and m['selected_rows']==2
    assert output[0]==output[1]
    broken=tmp_path/'broken.gz';broken.write_bytes(source_path.read_bytes()[:-5])
    source={**source,'sha256':file_hash(broken),'local_path':str(broken)}
    with pytest.raises((duckdb.Error,EOFError,OSError,ValueError)):
        duck_ingest(source,{'AAA':['id1']},cfg,root,time.monotonic(),{'decoded':0,'selected':0})


def test_local_quote_query_uses_duckdb2_api_and_preserves_source_ordinals(tmp_path,monkeypatch):
    import time
    from market_lab.flatfile_revalidation import source_quotes
    monkeypatch.chdir(tmp_path);cfg=resource_config();root=Path('run');root.mkdir()
    path=Path('source.gz')
    text='ticker,ask_price,bid_price,ask_size,bid_size,conditions,sequence_number,sip_timestamp\n'
    text+=f'AAA,1.11,1.10,100,100,1,1,{BASE+123}\n'
    path.write_bytes(gzip.compress(text.encode()))
    source={'dataset':'quotes','date':'2026-05-28','sha256':file_hash(path),'local_path':str(path),'key':'quote/day','complete':True}
    manifest=ingest_source(source,{'AAA':['id1']},cfg,root,time.monotonic(),{'decoded':0,'selected':0})
    rows,intervals,audit=source_quotes([manifest],'AAA',CYCLE,'id1')
    assert len(rows)==1 and rows[0]['sip_timestamp']==BASE+123
    assert json.loads(rows[0]['source_json'])['row']==0 and audit['duplicates']==0


def test_duckdb_gzip_reader_checks_crc_not_just_length(tmp_path,monkeypatch):
    import duckdb,time
    from market_lab.flatfile_ingest_duckdb import ingest_source as duck_ingest
    monkeypatch.chdir(tmp_path);cfg=resource_config();root=Path('run');root.mkdir()
    data=bytearray(gzip.compress(f'ticker,sip_timestamp,sequence_number\nAAA,{BASE},1\n'.encode()))
    data[-8]^=1  # CRC32 field, preserving the complete compressed byte length.
    path=Path('badcrc.gz');path.write_bytes(data)
    source={'dataset':'quotes','date':'2026-05-28','sha256':file_hash(path),'local_path':str(path),'key':'quote/day','complete':True}
    with pytest.raises((duckdb.Error,EOFError,OSError,ValueError)):
        duck_ingest(source,{'AAA':['id1']},cfg,root,time.monotonic(),{'decoded':0,'selected':0})
    assert not list(Path('data/flatfiles').rglob('manifest.json'))


def test_analysis_rejects_incomplete_independent_integrity_proof(tmp_path):
    from market_lab.flatfile_revalidation import revalidate
    from market_lab.flatfile_reconcile import reconcile
    (tmp_path/'gzip-integrity.json').write_text(json.dumps({'complete':False,'sources':[]}))
    for func in [revalidate,reconcile]:
        with pytest.raises(AssertionError,match='Mandatory gzip proof incomplete'):
            func({'objects':[{},{}]},tmp_path)


def test_provider_session_alignment_uses_dst_not_a_fixed_utc_day():
    from datetime import datetime,timezone
    from market_lab.flatfile_revalidation import source_interval
    low=int(datetime(2026,1,15,9,tzinfo=timezone.utc).timestamp())*S
    high=int(datetime(2026,1,16,1,tzinfo=timezone.utc).timestamp())*S
    m={'source':{'date':'2026-01-15','key':'key','sha256':'sha'},'complete':True,'gzip_crc_validated':True,
       'rows_outside_object_utc_date':100,'min_sip_timestamp':low,'max_sip_timestamp':high+1}
    r=source_interval(m)
    assert r['complete'] and r['start_ns']==low-1 and r['end_ns']==high-1


def test_no_valid_state_is_insufficient_not_an_observed_support_failure():
    assert signal([q(BASE,conditions='[81]')])['status']=='INSUFFICIENT_DATA'
    assert signal([q(BASE-70*S)])['status']=='INSUFFICIENT_DATA'
    assert signal([q(BASE,bid='1.0')])['status']=='UNCONFIRMED'


def test_concurrent_integrity_callers_reuse_one_crc_pass(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import market_lab.flatfile_integrity as integrity
    monkeypatch.chdir(tmp_path);cfg=resource_config();path=Path('source.gz')
    path.write_bytes(gzip.compress(f'ticker,sip_timestamp\nAAA,{BASE}\n'.encode()))
    source={'dataset':'quotes','date':'2026-05-28','sha256':file_hash(path),'local_path':str(path),'key':'quote/day','complete':True}
    original=integrity.subprocess.Popen;calls=[]
    def launch(*args,**kwargs):
        calls.append(1);return original(*args,**kwargs)
    monkeypatch.setattr(integrity.subprocess,'Popen',launch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(integrity.verify_gzip,source,cfg);b=pool.submit(integrity.verify_gzip,source,cfg)
        first,second=a.result(),b.result()
    assert first==second and len(calls)==1 and first['crc_validated']
