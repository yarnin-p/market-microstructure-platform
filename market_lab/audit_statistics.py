"""Domain-ratio Taylor variance under month/date and security SRSWOR.

All sampled opportunities, including zero-event rows, contribute to the domain
linearization. Inference targets fixed finite outcomes, not a price process.
"""
import math
from collections import defaultdict
import numpy as np

CRITICAL=2.055529438642871  # two-sided Student t(.975,26); candidate interval only


def ratio(groups,date_population,critical=CRITICAL):
    by_month=defaultdict(lambda:defaultdict(list));Y=Z=0.
    for i,g in enumerate(groups):
        by_month[g['month']][g.get('cycle_id',str(i))].append(g)
    for month,dates in by_month.items():
        f=date_population[month]/len(dates)
        Y+=f*sum(g['N']*float(np.mean(g['y'])) for gg in dates.values() for g in gg)
        Z+=f*sum(g['N']*float(np.mean(g['z'])) for gg in dates.values() for g in gg)
    if Z<=0:return {'estimate':None,'se':None,'interval':None,'status':'EMPTY_DOMAIN','domain_total':Z}
    theta=Y/Z;variance=0.
    for month,dates in by_month.items():
        M=date_population[month];m=len(dates);totals=[];within=[]
        if m>M:raise ValueError('Invalid first-stage allocation')
        for gg in dates.values():
            T=V=0.
            for g in gg:
                y=np.asarray(g['y'],float);z=np.asarray(g['z'],float);n=len(y);N=g['N']
                if n!=len(z) or n<1 or n>N or (n==1 and N>1):raise ValueError('Invalid second-stage sample')
                residual=y-theta*z
                T+=N*float(residual.mean())
                V+=N*N*(1-n/N)*float(residual.var(ddof=1))/n if n<N else 0.
            totals.append(T);within.append(V)
        if m<M and m<2:return {'estimate':theta,'se':None,'interval':None,'status':'SINGLE_DATE_STRATUM','domain_total':Z}
        first=M*M*(1-m/M)*float(np.var(totals,ddof=1))/m if m>1 and m<M else 0.
        variance+=first+M/m*sum(within)
    se=math.sqrt(max(0,variance))/Z
    return {'estimate':theta,'se':se,'interval':[theta-critical*se,theta+critical*se],
        'domain_total':Z,'numerator_total':Y,'variance':variance/(Z*Z),'critical_value':critical,
        'status':'CANDIDATE_DESIGN_TAYLOR_INTERVAL_NOT_FORMAL_EXPLORATION_INFERENCE'}


def groups_from_rows(rows,y,z):
    grouped=defaultdict(list)
    for r,a,b in zip(rows,y,z):grouped[(r['cycle_id'],r['stratum'])].append((r,a,b))
    return [{'month':rr[0][0]['cycle_id'][:7],'cycle_id':key[0],'stratum':key[1],
        'N':rr[0][0]['population_N'],'y':[a for r,a,b in rr],'z':[b for r,a,b in rr]} for key,rr in sorted(grouped.items())]


def simulate(replicates=1000,seed=202611160005):
    """Repeated probability sampling from known fixed synthetic populations.

    Shared security effects, AR(1) day effects, unequal security populations,
    and informative censoring are generated once, then held fixed per scenario.
    """
    output=[]
    for scenario,event_rate,censor,holdout in [('regular',.13,0.,False),('rare_domain',.02,0.,False),
        ('informative_missing',.13,.2,False),('holdout_census_dates',.13,0.,True)]:
        rng=np.random.default_rng(seed+len(output));M=[14,22,21,13] if not holdout else [20,20]
        m=[6,9,9,6] if not holdout else M;security=rng.normal(0,.9,240);population=[];latent_y=0.;latent_z=0.
        for month,size in enumerate(M):
            days=[];ar=0.
            for day in range(size):
                ar=.75*ar+rng.normal(0,.5);strata=[]
                for st in range(2):
                    N=int(rng.integers(30,100));ids=rng.choice(240,N,replace=False)
                    p=1/(1+np.exp(-(math.log(event_rate/(1-event_rate))+security[ids]+ar+.3*st)))
                    z=(rng.random(N)<p).astype(float)
                    down=rng.random(N)<1/(1+np.exp(-(0.4+security[ids]*.5+ar)))
                    neither=rng.random(N)<.06
                    latent=z*np.where(neither,0,np.where(down,1,-1));latent_y+=latent.sum();latent_z+=z.sum()
                    missing=(rng.random(N)<censor*(1+.7*down)) & (z>0)
                    # Published classification estimand retains unknown as zero contrast,
                    # with unknown category separately disclosed; not latent imputation.
                    y=np.where(missing,0,latent)
                    strata.append((y,z,ids))
                days.append(strata)
            population.append(days)
        trueY=sum(g[0].sum() for days in population for day in days for g in day)
        trueZ=sum(g[1].sum() for days in population for day in days for g in day)
        truth=trueY/trueZ;hits=latent_hits=valid=0;values=[];ses=[];widths=[]
        for _ in range(replicates):
            groups=[]
            for month,days in enumerate(population):
                for day in rng.choice(len(days),m[month],replace=False):
                    for st,(y,z,ids) in enumerate(days[day]):
                        ix=rng.choice(len(y),12,replace=False)
                        groups.append({'month':str(month),'cycle_id':str(day),'N':len(y),'y':y[ix],'z':z[ix]})
            result=ratio(groups,{str(i):v for i,v in enumerate(M)})
            if result['interval'] is None:continue
            lo,hi=result['interval'];valid+=1;hits+=lo<=truth<=hi;latent_hits+=lo<=latent_y/latent_z<=hi
            values.append(result['estimate']);ses.append(result['se']**2);widths.append(hi-lo)
        p=hits/replicates
        output.append({'scenario':scenario,'replicates':replicates,'valid_intervals':valid,'known_population_target':truth,
            'latent_uncensored_target':latent_y/latent_z,'coverage_all_replicates':p,
            'coverage_monte_carlo_se':math.sqrt(p*(1-p)/replicates),'latent_target_coverage':latent_hits/replicates,
            'bias':float(np.mean(values))-truth,'empirical_sd':float(np.std(values,ddof=1)),
            'mean_estimated_variance':float(np.mean(ses)),'mean_interval_width':float(np.mean(widths)),
            'synthetic_only':True,'interpretation':'Calibration under specified fixed populations only; does not prove market coverage or recover latent missing outcomes.'})
    return output
