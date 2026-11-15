"""Full-pilot cohort/session descriptive statistics, with explicit censored denominators."""
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_lab.m2_report import records
from market_lab.storage import write_json


def aggregate(run_id):
    root=Path('data/runs',run_id)
    events=records(root/'events/events.parquet')
    outcomes={o['event_id']:o for o in records(root/'outcomes/outcomes.parquet')}
    results=[]
    for sample in ['SYSTEMATIC','DIAGNOSTIC']:
        for cohort in ['EXCHANGE_PRICE_ONLY','MASSIVE_CURRENT_FLOAT_PROXY']:
            for session in ['ALL','AH','PRE','RTH']:
                selected=[e for e in events if e['sample']==sample and cohort in e['cohorts'] and (session=='ALL' or e['session']==session)]
                rows=[outcomes[e['event_id']] for e in selected]
                forward={}
                for horizon in ['5m','15m','30m','60m','session_end','cycle_end']:
                    marks=[m for r in rows for m in r['forward'] if m['horizon']==horizon]
                    vals=sorted(Decimal(m['return']) for m in marks if m['return'] is not None)
                    n=len(vals)
                    forward[horizon]={'events':len(rows),'uncensored':n,'censored':len(marks)-n,
                                      'mean':str(sum(vals)/n) if n else None,'median':str((vals[(n-1)//2]+vals[n//2])/2) if n else None,
                                      'min':str(vals[0]) if n else None,'max':str(vals[-1]) if n else None}
                barriers={str(u)+'/'+str(d):dict(Counter(b['outcome'] for r in rows for b in r['barriers'] if b['up']==u and b['down']==d)) for u,d in [('0.03','0.03'),('0.05','0.03'),('0.10','0.05')]}
                results.append({'sample':sample,'cohort':cohort,'session':session,'events':len(rows),'forward':forward,'barriers':barriers,
                                'excursions':[{'event_id':r['event_id'],'mfe':r['observed_mfe'],'mae':r['observed_mae'],'censored':r['excursion_censored']} for r in rows]})
    result={'scope':'FULL_SELECTED_PILOT; not full universe; overlapping cohorts must not be summed',
            'inference':'No statistical significance claims; no confidence intervals estimated for tiny clustered sample', 'groups':results}
    write_json(Path('reports',run_id,'cohort_outcomes.json'),result)
    return result

if __name__=='__main__':
    result=aggregate(sys.argv[1]);print(json.dumps({'groups':len(result['groups'])}))
