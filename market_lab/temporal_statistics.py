"""Descriptive design estimates and explicit small-cluster uncertainty limits."""
import math
import random
from collections import Counter,defaultdict


def sample_variance(values):
    if len(values)<2:return None
    mean=sum(values)/len(values)
    return sum((x-mean)**2 for x in values)/(len(values)-1)


def design_incidence(rows,date_strata):
    """Two-stage SRSWOR Taylor ratio variance, conditional on full response."""
    complete=[r for r in rows if r['complete_observed_sessions'] and r.get('observed_opportunity_eligible',True)]
    base={'selected_denominator':len(rows),'complete_denominator':len(complete),'incomplete':len(rows)-len(complete),
          'date_clusters':len({r['cycle_id'] for r in complete}),'security_clusters':len({r['security_id'] for r in complete})}
    if not complete:return {**base,'weighted_incidence':None,'uncertainty_status':'NO_COMPLETE_WINDOWS'}
    W=sum(r['joint_sampling_weight'] for r in complete)
    rate=sum(r['joint_sampling_weight']*bool(r['event_id']) for r in complete)/W
    base.update(weighted_incidence=rate,observed_events=sum(bool(r['event_id']) for r in complete),
                kish_effective_n=W*W/sum(r['joint_sampling_weight']**2 for r in complete),weight_sum=W)
    if len(complete)!=len(rows) or len({r['cycle_id'] for r in rows})!=sum(s['batch_n'] for s in date_strata):
        return {**base,'uncertainty_status':'SUPPRESSED_NONRESPONSE_OR_MISSING_DATES','two_stage_taylor_se':None}
    by_date=defaultdict(list)
    for r in rows:by_date[r['cycle_id']].append(r)
    totals={};within={};X=0
    for cycle,rr in by_date.items():
        T=0;V=0;Ndate=0
        for stratum in sorted({r['stratum'] for r in rr}):
            ss=[r for r in rr if r['stratum']==stratum];N=ss[0]['population_N'];n=len(ss)
            if n!=ss[0]['sample_n'] or n<2:return {**base,'uncertainty_status':'INSUFFICIENT_WITHIN_STRATUM_SAMPLE'}
            y=[float(bool(r['event_id'])) for r in ss]
            T+=N*sum(y)/n;Ndate+=N
            V+=N*N*(1-n/N)*sample_variance(y)/n
        totals[cycle]=T-rate*Ndate;within[cycle]=V
        X+=Ndate/rr[0]['date_inclusion_probability']
    variance=0
    for m in date_strata:
        dates=[c for c in by_date if c.startswith(m['month'])];N=m['population_N'];n=len(dates)
        if n!=m['batch_n'] or n<2:return {**base,'uncertainty_status':'INSUFFICIENT_DATE_STRATUM_RESPONSE'}
        variance+=N*N*(1-n/N)*sample_variance([totals[c] for c in dates])/n+(N/n)*sum(within[c] for c in dates)
    return {**base,'uncertainty_status':'EXPLORATORY_TWO_STAGE_DESIGN_LINEARIZATION_NOT_SIGNIFICANCE',
            'two_stage_taylor_se':math.sqrt(max(0,variance))/X,'estimated_finite_population_denominator':X,
            'assumptions':'Independent randomized date/security draws, fixed finite outcomes, SRSWOR within both strata; only 2-3 dates/month. No normal/iid confidence interval.'}


def clustered_ratio(rows,value_key,weight_key='joint_sampling_weight'):
    valid=[r for r in rows if r.get(value_key) is not None]
    if not valid:return {'n':0,'ratio':None,'status':'NO_VALUES'}
    W=sum(r[weight_key] for r in valid);mean=sum(r[weight_key]*r[value_key] for r in valid)/W
    def variance(keys):
        clusters=defaultdict(float)
        for r in valid:clusters[tuple(r[k] for k in keys)]+=r[weight_key]*(r[value_key]-mean)/W
        G=len(clusters)
        return (G/(G-1)*sum(x*x for x in clusters.values()) if G>1 else None),G
    vd,Gd=variance(['cycle_id']);vs,Gs=variance(['security_id']);vi,Gi=variance(['cycle_id','security_id'])
    v=vd+vs-vi if None not in [vd,vs,vi] else None
    return {'n':len(valid),'ratio':mean,'date_clusters':Gd,'security_clusters':Gs,'intersection_clusters':Gi,
            'two_way_variance':v,'two_way_se':math.sqrt(v) if v is not None and v>=0 else None,
            'status':'ILLUSTRATIVE_SMALL_CLUSTER_SENSITIVITY' if v is not None and v>=0 else 'UNDEFINED_OR_NEGATIVE_VARIANCE_NOT_CLAMPED',
            'confidence_interval':None,'caveat':'Date + security - intersection score variance; not a calibrated small-sample significance test.'}


def crossed_cluster_bootstrap(rows,replicates,seed):
    """Month-stratified date and crossed-security multiplier sensitivity."""
    valid=[r for r in rows if r['complete_observed_sessions'] and r.get('observed_opportunity_eligible',True)]
    if not valid:return {'replicates':0,'interval':None}
    dates=defaultdict(list)
    for c in sorted({r['cycle_id'] for r in valid}):dates[c[:7]].append(c)
    securities=sorted({r['security_id'] for r in valid});rng=random.Random(seed);estimates=[]
    for _ in range(replicates):
        cd=Counter(c for pool in dates.values() for c in rng.choices(pool,k=len(pool)))
        cs=Counter(rng.choices(securities,k=len(securities)))
        weights=[r['joint_sampling_weight']*cd[r['cycle_id']]*cs[r['security_id']] for r in valid]
        total=sum(weights)
        if total:estimates.append(sum(w*bool(r['event_id']) for w,r in zip(weights,valid))/total)
    estimates.sort()
    def q(p):return estimates[round((len(estimates)-1)*p)] if estimates else None
    return {'replicates':len(estimates),'seed':seed,'p025':q(.025),'median':q(.5),'p975':q(.975),
        'status':'ILLUSTRATIVE_CROSSED_CLUSTER_RESAMPLING_RANGE_NOT_CALIBRATED_CI',
        'limitations':'Only 10 new date clusters, 2-3/month. Reweights repeated security globally; not an exact SRSWOR two-stage bootstrap and no significance claim.'}
