"""Crossed cycle/session/cohort/policy denominators; no population inference."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_lab.m2_report import records
from market_lab.m2_pilot import event_table
from market_lab.storage import write_json
from market_lab.systematic_report import package

if __name__=='__main__':
    config=json.loads(Path('configs/task-002-2-systematic-v1.json').read_text())
    root=Path('data/runs',config['run_id']);dest=Path('reports',config['run_id'])
    opps=records(root/'opportunities/opportunities.parquet');events=records(root/'events/events.parquet')
    frame=records(root/'population/frame.parquet');groups=[];rank={'AH':0,'PRE':1,'RTH':2}
    for cycle in sorted({o['cycle_id'] for o in opps}):
        for policy in config['condition_policies']:
            for cohort in ['EXCHANGE_PRICE_ONLY','MASSIVE_CURRENT_FLOAT_PROXY','SEC_HISTORICAL_EVIDENCE_OVERLAP']:
                def member(r):return bool(r.get('sec_evidence')) if cohort=='SEC_HISTORICAL_EVIDENCE_OVERLAP' else cohort in r['cohorts']
                oo=[o for o in opps if o['cycle_id']==cycle and o['condition_policy']==policy and member(o)]
                ee=[e for e in events if e['cycle_id']==cycle and e['condition_policy']==policy and member(e)]
                for session in ['ALL','AH','PRE','RTH']:
                    earlier={e['security_id'] for e in ee if session!='ALL' and rank[e['session']]<rank[session]}
                    eligible=[o for o in oo if o['observed_opportunity_eligible'] and o['security_id'] not in earlier]
                    chosen=[e for e in ee if session=='ALL' or e['session']==session]
                    verified=sum(e['observed_sessions_first_verified'] for e in chosen)
                    groups.append({'run_id':config['run_id'],'cycle_id':cycle,'sample':'SYSTEMATIC','condition_policy':policy,'cohort':cohort,'session':session,
                                   'population_eligibility_frame_N':sum(f['cycle_id']==cycle and member(f) for f in frame),
                                   'sampled_opportunities':len(oo),'complete_sampled_opportunities':sum(o['complete_observed_sessions'] for o in oo),
                                   'verified_session_risk_set':len(eligible),'observed_events':len(chosen),'verified_events':verified,
                                   'no_first_touch_in_this_session':len(eligible)-verified,'strict_full_cycle_denominator':0})
    write_json(dest/'denominators.json',{'scope':'FULL_SELECTED_SAMPLE; population eligibility frame is not a population session risk set; cohorts and policies overlap','groups':groups})
    event_table(dest/'denominators.parquet',groups)
    package(config,root,dest)
    print(json.dumps({'crossed_denominator_rows':len(groups)}))
