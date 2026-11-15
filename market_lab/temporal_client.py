"""Shared hard budgets for the authorized first ten temporal cycles only."""
import json
import time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import parse_qsl,urlparse,quote

import requests

from .api import APIError,safe_url,scrub
from .nbbo_probe import BudgetStop,ProbeClient,usage
from .storage import digest,file_hash,write_json
from .tick_ingest import TickClient


class TemporalClient(ProbeClient,TickClient):
    def __init__(self,root,config,allowed_tickers,key=None,offline=False,session=None):
        self.offline=offline;self.hits=0
        self.allowed={f'/v3/{kind}/{quote(t,safe="")}' for t in allowed_tickers for kind in ['trades','quotes']}
        super().__init__(Path(root),config,key,session)

    def check(self):
        super().check()
        if usage(self.root)+4*self.config['max_page_bytes'] > self.config['max_storage_bytes']:
            raise BudgetStop('STORAGE_HEADROOM_BUDGET')

    def get(self,path,params=None):
        url=safe_url(path if path.startswith('https:') else 'https://api.massive.com'+path)
        if urlparse(url).path not in self.allowed:raise APIError('UNPLANNED_TICK_ENDPOINT')
        request={'url':url.split('?',1)[0],'params':dict(parse_qsl(urlparse(url).query))|(params or {})}
        key=digest(request);raw=self.root/'raw/pages'/(key+'.json');meta=raw.with_suffix('.meta.json')
        if meta.exists():
            m=json.loads(meta.read_text())
            if m['request']!=request or file_hash(raw)!=m['sha256']:raise APIError('CACHE_HASH_OR_REQUEST_MISMATCH')
            body=json.loads(raw.read_text())
            if m['http_status']!=200:raise APIError('HTTP_'+str(m['http_status']))
            if 'results' not in body and body.get('results_count')==0:body={**body,'results':[]}
            self.hits+=1;return body,m
        if self.offline:raise APIError('OFFLINE_CACHE_MISS')
        self.check()
        if not self.key:raise BudgetStop('MISSING_API_KEY')
        time.sleep(min(self.config['minimum_request_spacing_seconds'],max(0,self.deadline-time.monotonic())))
        self.check()
        attempt={'request':request,'started_at':datetime.now(timezone.utc).isoformat(),'status':'STARTED','bytes':0}
        self.ledger['attempts'].append(attempt);self.save();chunks=[]
        try:
            remaining=max(.001,self.deadline-time.monotonic())
            with self.session.get(request['url'],params=request['params'],headers={'Authorization':'Bearer '+self.key},
                    stream=True,allow_redirects=False,timeout=(min(self.config['connect_timeout_seconds'],remaining),min(self.config['read_timeout_seconds'],remaining))) as response:
                attempt['http_status']=response.status_code
                iterator=response.iter_content(16384)
                while True:
                    if time.monotonic()>=self.deadline:raise BudgetStop('WALL_TIME_BUDGET')
                    available=min(self.config['max_page_bytes']-attempt['bytes'],self.config['max_decoded_bytes']-self.ledger['decoded_bytes'])
                    if available<16384:raise BudgetStop('DECODED_BYTE_OR_PAGE_BYTE_BUDGET')
                    try:block=next(iterator)
                    except StopIteration:break
                    if len(block)>available:raise BudgetStop('DECODER_RESERVATION_EXCEEDED')
                    chunks.append(block);attempt['bytes']+=len(block);self.ledger['decoded_bytes']+=len(block);self.save()
                body=json.loads(b''.join(chunks));clean=scrub(body,self.key)
                content=b''.join(chunks) if clean==body else json.dumps(clean,separators=(',',':')).encode()
                self.persist(raw,content)
                m={'path':str(raw.resolve()),'sha256':file_hash(raw),'request':request,'http_status':response.status_code,
                   'retrieved_at':datetime.now(timezone.utc).isoformat(),'bytes':len(content),'decoded_bytes':attempt['bytes']}
                write_json(meta,m)
                if response.status_code!=200:raise APIError('HTTP_'+str(response.status_code))
                self.ledger['pages']+=1
                if 'results' not in clean and clean.get('results_count')==0:clean={**clean,'results':[]}
                if not isinstance(clean.get('results'),list):raise APIError('INVALID_RESULTS_SCHEMA')
                attempt['status']='OK';return clean,m
        except requests.RequestException as exc:
            attempt['status']='NETWORK_'+type(exc).__name__;raise APIError(attempt['status']) from None
        except (APIError,ValueError,BudgetStop) as exc:
            attempt['status']=str(exc) if not isinstance(exc,ValueError) else 'INVALID_JSON'
            if isinstance(exc,BudgetStop):raise
            raise APIError(attempt['status']) from None
        finally:
            if attempt['status']=='STARTED':attempt['status']='INTERRUPTED'
            self.save()

    def window(self,kind,ticker,start_ns,end_ns,output):
        try:return TickClient.window(self,kind,ticker,start_ns,end_ns,output)
        except BudgetStop as exc:
            p=Path(output)/'coverage.json'
            cov=json.loads(p.read_text()) if p.exists() else {'request':{'kind':kind,'ticker':ticker,'start_ns':start_ns,'end_ns':end_ns},'pages':[],'raw_rows':0}
            cov.update(complete=False,error=str(exc));write_json(p,cov)
            raise
