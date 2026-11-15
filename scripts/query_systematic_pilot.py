"""Read-only bounded DuckDB drilldowns; extracts are explicitly non-population data."""
import argparse
import json
import re
from pathlib import Path
import duckdb


def query(args):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.run_id):
        raise ValueError('invalid run ID')
    root = Path('data/runs', args.run_id)
    files = {'events': 'events/events.parquet', 'outcomes': 'outcomes/outcomes.parquet',
             'opportunities': 'opportunities/opportunities.parquet', 'population': 'population/frame.parquet',
             'trades': 'ticks/cycle=*/security=*/trades/normalized/*.parquet', 'quotes': 'ticks/cycle=*/security=*/quotes/*/normalized/*.parquet'}
    paths = [str(p) for p in sorted(root.glob(files[args.kind]))]
    if not paths:
        return {'matching_rows': 0, 'returned_rows': 0, 'rows': [], 'scope': 'FOCUSED_EXTRACT'}
    filters, params = [], []
    for field in ['cycle_id', 'security_id', 'ticker', 'session', 'event_id']:
        value = getattr(args, field)
        if value:
            if field == 'event_id' and args.kind in {'trades', 'quotes'}:
                raise ValueError('For ticks, obtain cycle/security/timestamp from the event drilldown first')
            filters.append(field + ' = ?'); params.append(value)
    sql = 'FROM read_parquet(?, hive_partitioning=false)' + (' WHERE ' + ' AND '.join(filters) if filters else '')
    with duckdb.connect() as db:
        db.execute("SET memory_limit='256MB'")
        total = db.execute('SELECT count(*) ' + sql, [paths, *params]).fetchone()[0]
        cursor = db.execute('SELECT * ' + sql + ' LIMIT ?', [paths, *params, args.limit])
        fields = [d[0] for d in cursor.description]
        rows = [dict(zip(fields, row)) for row in cursor.fetchall()]
    result = {'scope': 'FOCUSED_EXTRACT_NOT_POPULATION_STATISTICS', 'matching_rows': total,
              'returned_rows': len(rows), 'truncated': total > len(rows), 'rows': rows}
    if args.output:
        p = Path(args.output)
        if p.exists(): raise ValueError('extract path exists; choose a new path')
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(result, indent=2) + '\n')
        return {k:v for k,v in result.items() if k != 'rows'} | {'output':str(p.resolve())}
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id',default='m2-systematic-10cycles-20261115-v2')
    p.add_argument('--kind',choices=['events','outcomes','opportunities','population','trades','quotes'],default='events')
    for field in ['cycle-id','security-id','ticker','session','event-id']:
        p.add_argument('--'+field)
    p.add_argument('--limit',type=int,default=100)
    p.add_argument('--output')
    args=p.parse_args()
    if not 1 <= args.limit <= 5000: p.error('limit must be 1..5000; full evidence is retained separately')
    print(json.dumps(query(args),indent=2))
