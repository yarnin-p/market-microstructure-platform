"""Streaming gzip CSV filter into immutable date/ticker Parquet partitions.

All original CSV fields remain strings; nanosecond timestamps get additional
integer columns. No whole-market table or decompressed CSV is materialized.
Completed extraction is reused; an interrupted gzip scan is explicitly partial
and a new attempt rescans only that incomplete daily file.
"""
import argparse
import csv
import gzip
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from .flatfile_cache import CONFIG, atomic_json, location, memory_bytes
from .m2_report import records
from .storage import digest, file_hash
from .temporal_design import read

SCHEMA_VERSION = 'massive-flatfile-selected-v1'


def selected_mapping(config):
    src = Path('data/runs', config['source_run'])
    events = [e for e in records(src/'events/events.parquet') if e['condition_policy']=='HIGH_LOW_ONLY']
    assert len(events)==40 and len({e['event_id'] for e in events})==40
    selection = read(src/'selection.json'); mapping=defaultdict(set)
    for event in events:
        op=next(o for o in selection['selected'] if (o['cycle_id'],o['security_id'])==(event['cycle_id'],event['security_id']))
        assert op['ticker']==event['ticker']
        mapping[event['ticker']].add(event['security_id'])
    return events,{k:sorted(v) for k,v in mapping.items()}


def check_budget(config, root, started, decoded, selected):
    if time.monotonic()-started>config['max_active_seconds']:raise RuntimeError('INGEST_TIME_BUDGET')
    if time.time()>config.get('_execution_deadline_utc',float('inf')):raise RuntimeError('SHARED_EXECUTION_BUDGET')
    if decoded>config['max_decoded_bytes']:raise RuntimeError('INGEST_DECODED_BUDGET')
    if selected>config['max_selected_rows']:raise RuntimeError('SELECTED_ROW_BUDGET')
    if memory_bytes()>config['max_memory_bytes']:raise RuntimeError('INGEST_MEMORY_BUDGET')
    if config.get('_resource_progress_path'):
        atomic_json(config['_resource_progress_path'],{'max_rss_bytes':memory_bytes(),'elapsed_seconds':time.monotonic()-started,'decoded_logical_upper_bytes':decoded,'selected_logical_rows':selected})
    # Raw compressed sources, temporary fragments and selected outputs stay local.
    size=sum(p.stat().st_size for folder in [Path('data/flatfiles'),root] for p in folder.rglob('*') if p.is_file())
    if size>config['max_storage_bytes']:raise RuntimeError('INGEST_STORAGE_BUDGET')


def ingest_source(source, mapping, config, root, started, cumulative):
    assert source['complete'] and file_hash(source['local_path'])==source['sha256']
    from .flatfile_integrity import verify_gzip
    verify_gzip(source,config)
    extraction=digest([SCHEMA_VERSION,source['sha256'],mapping])
    folder=location(source)/'extractions'/extraction;folder.mkdir(parents=True,exist_ok=True)
    manifest_path=folder/'manifest.json'
    if manifest_path.exists():
        previous=read(manifest_path)
        for r in previous['partitions']:
            assert file_hash(r['path'])==r['sha256']
        return previous
    attempt=folder/('attempt='+str(len(list(folder.glob('attempt=*')))).zfill(3));attempt.mkdir()
    writers={};buffers=defaultdict(list);buffer_counts=defaultdict(int);counts=defaultdict(int)
    raw_rows=selected=decoded=0;minimum=maximum=None;outside_utc=0
    date=datetime.fromisoformat(source['date']).replace(tzinfo=timezone.utc)
    low=int(date.timestamp())*10**9;high=low+86400*10**9
    def flush(ticker):
        if buffers[ticker]:
            table=pa.concat_tables(buffers[ticker])
            if ticker not in writers:
                p=attempt/('ticker='+ticker)/'part-000.parquet';p.parent.mkdir(parents=True,exist_ok=True)
                writers[ticker]=pq.ParquetWriter(p,table.schema,compression='zstd')
            writers[ticker].write_table(table,row_group_size=16384)
            buffers[ticker].clear();buffer_counts[ticker]=0
    try:
        with gzip.open(source['local_path'],'rb') as header_stream:
            header=next(csv.reader([header_stream.readline().decode('utf-8').rstrip('\r\n')]))
        if len(header)!=len(set(header)) or 'ticker' not in header or 'sip_timestamp' not in header:
            raise ValueError('Unexpected CSV header')
        with duckdb.connect() as db:
            db.execute("SET memory_limit='768MB'");db.execute('SET threads=4')
            db.execute("SET preserve_insertion_order=true")
            sequence="TRY_CAST(sequence_number AS BIGINT)" if 'sequence_number' in header else "NULL::BIGINT"
            query="SELECT * EXCLUDE(ordinality), ordinality-1 AS _source_row, CAST(sip_timestamp AS BIGINT) AS _sip_timestamp_ns, "+sequence+" AS _sequence_number_int FROM read_csv(?,header=true,columns=?,all_varchar=true,parallel=true,nullstr='__MMP_NO_NULL_SENTINEL__',strict_mode=true) WITH ORDINALITY"
            reader=db.sql(query,params=[source['local_path'],{k:'VARCHAR' for k in header}]).to_arrow_reader(batch_size=65536)
            decoded=len((','.join(header)+'\n').encode())
            for i,batch in enumerate(reader):
                timestamps=batch.column(batch.schema.get_field_index('_sip_timestamp_ns'))
                extremes=pc.min_max(timestamps).as_py()
                if extremes['min'] is not None:
                    minimum=extremes['min'] if minimum is None else min(minimum,extremes['min'])
                    maximum=extremes['max'] if maximum is None else max(maximum,extremes['max'])
                outside_utc+=pc.sum(pc.or_(pc.less(timestamps,low),pc.greater_equal(timestamps,high))).as_py() or 0
                mask=pc.is_in(batch.column(header.index('ticker')),value_set=pa.array(list(mapping)))
                if pc.any(mask).as_py():
                    table=pa.Table.from_batches([batch]).filter(mask)
                    # Ordinality is assigned by the CSV table function before any filtering.
                    table=table.replace_schema_metadata({b'schema_version':SCHEMA_VERSION.encode(),b'source_sha256':source['sha256'].encode(),b'source_key':source['key'].encode()})
                    for ticker in pc.unique(table['ticker']).to_pylist():
                        part=table.filter(pc.equal(table['ticker'],ticker))
                        ids=mapping[ticker]
                        part=part.append_column('_security_id',pa.array([ids[0] if len(ids)==1 else None]*len(part),type=pa.string()))
                        buffers[ticker].append(part);buffer_counts[ticker]+=len(part);counts[ticker]+=len(part)
                        if buffer_counts[ticker]>=16384:flush(ticker)
                    selected+=len(table)
                raw_rows+=batch.num_rows
                # Conservative encoded-CSV upper bound, including quoting/escapes/CRLF.
                field_bytes=sum(pc.sum(pc.binary_length(pc.cast(batch.column(j),pa.binary()))).as_py() or 0 for j in range(len(header)))
                decoded+=2*field_bytes+batch.num_rows*(3*len(header)+2)
                if i%16==0:
                    check_budget(config,root,started,cumulative['decoded']+decoded,cumulative['selected']+selected)
                    atomic_json(attempt/'progress.json',{'raw_rows':raw_rows,'selected_rows':selected,'decoded_bytes':decoded,'complete':False})
                if i%256==0:print(json.dumps({'ingest':source['dataset'],'date':source['date'],'raw_rows':raw_rows,'selected_rows':selected,'decoded_bytes':decoded}),flush=True)
        for ticker in list(buffers):flush(ticker)
        for writer in writers.values():writer.close()
        check_budget(config,root,started,cumulative['decoded']+decoded,cumulative['selected']+selected)
        partitions=[]
        for ticker,ids in mapping.items():
            path=attempt/('ticker='+ticker)/'part-000.parquet'
            if not path.exists():
                schema=pa.schema([(k,pa.string()) for k in header]+[('_source_row',pa.int64()),('_sip_timestamp_ns',pa.int64()),('_sequence_number_int',pa.int64()),('_security_id',pa.string())])
                path.parent.mkdir(parents=True,exist_ok=True);pq.write_table(pa.Table.from_pylist([],schema=schema),path,compression='zstd')
            partitions.append({'ticker':ticker,'security_ids':ids,'rows':counts[ticker],'empty':counts[ticker]==0,
                               'path':str(path),'sha256':file_hash(path)})
        result={'schema_version':SCHEMA_VERSION,'source':source,'extraction_id':extraction,'partitions':partitions,
            'header':header,'raw_rows':raw_rows,'selected_rows':selected,'decoded_bytes':decoded,
            'min_sip_timestamp':minimum,'max_sip_timestamp':maximum,'rows_outside_object_utc_date':outside_utc,
            'complete':True,'gzip_crc_validated':True,'original_fields_preserved':True,
            'timestamp_basis':'INTEGER_NANOSECONDS; source date alignment audited, not inferred from filename',
            'parser_backend':'DUCKDB_STREAMING_ARROW_READER_V1','decoded_bytes_basis':'CONSERVATIVE_ENCODED_CSV_UPPER_BOUND',
            'ordering':'source_row retained; query by sip_timestamp,sequence_number,source_row',
            'historical_mapping':'Frozen original40 event tickers/IDs; ambiguous mappings retained, never current-ticker substituted'}
        atomic_json(manifest_path,result);return result
    except BaseException as exc:
        for writer in writers.values():
            try:writer.close()
            except Exception:pass
        atomic_json(attempt/'incomplete.json',{'complete':False,'error_type':type(exc).__name__,'raw_rows':raw_rows,'selected_rows':selected,'decoded_bytes':decoded})
        raise


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',default=CONFIG);p.add_argument('--watch',action='store_true');a=p.parse_args();config=read(a.config)
    root=Path('data/runs',config['run_id']);events,mapping=selected_mapping(config)
    import os
    config={**config,'max_memory_bytes':min(config['max_memory_bytes'],1536*1024**2),
        '_resource_progress_path':str(root/('ingest-attempt-'+str(os.getpid())+'.json'))}
    ledger=root/'resource-ledger.json'
    if ledger.exists():
        config={**config,'_execution_deadline_utc':ledger.stat().st_mtime+config['max_active_seconds']-read(ledger)['active_seconds']}
    started=time.monotonic();cum={'decoded':0,'selected':0};outputs=[]
    for expected in config['objects']:
        from .flatfile_cache import object_identity
        source_path=location(expected)/'sources'/(object_identity(expected)+'.json')
        while not source_path.exists():
            if not a.watch:raise RuntimeError('SOURCE_NOT_DOWNLOADED')
            if (root/'acquisition-attempt-state.json').exists() and read(root/'acquisition-attempt-state.json')['status']=='STOPPED':raise RuntimeError('ACQUISITION_STOPPED_INCOMPLETE')
            check_budget(config,root,started,cum['decoded'],cum['selected'])
            time.sleep(5)
        source=read(source_path)
        out=ingest_source(source,mapping,config,root,started,cum);outputs.append(out)
        cum['decoded']+=out['decoded_bytes'];cum['selected']+=out['selected_rows']
        atomic_json(root/'ingested-sources.json',outputs)
    atomic_json(root/'ingest-resources.json',{'decoded_bytes':cum['decoded'],'selected_rows':cum['selected'],
        'decoded_bytes_basis':'CONSERVATIVE_ENCODED_CSV_UPPER_BOUND','elapsed_seconds':time.monotonic()-started,'max_rss_bytes':memory_bytes(),'source_count':len(outputs)})


if __name__=='__main__':main()
