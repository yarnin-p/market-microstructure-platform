// Execute inside Codex functions.exec: new Function('tools','text','notify', source).
// Authenticated Massive MCP is the only market-data transport; no local API key.
return (async () => {
  const cwd = '/Users/yarnin/Documents/yarnin-p/market-microstructure-platform';
  let stateResult = await tools.exec_command({cmd:'.venv/bin/python -m market_lab.census broker-state',workdir:cwd,max_output_tokens:12000,yield_time_ms:30000});
  while(stateResult.session_id){stateResult=await tools.write_stdin({session_id:stateResult.session_id,chars:'',yield_time_ms:1000,max_output_tokens:12000});}
  if (stateResult.exit_code !== 0) throw Error(stateResult.output);
  const state = JSON.parse(stateResult.output);
  const started = Date.now();
  const budget=state.transport;
  function shellQuote(value) {return "'"+value.replaceAll("'", "'\\''")+"'";}
  let cursor=0, calls=0, bytes=0, complete=0, halted=false, reservedBytes=0;
  const errors=[];
  async function save(path,value) {
    const result=await tools.apply_patch('*** Begin Patch\n*** Add File: '+path+'\n+'+JSON.stringify(value)+'\n*** End Patch');
    if(result?.isError) throw Error('LOCAL_WRITE_FAILED '+JSON.stringify(result));
  }
  async function one(ticker,worker) {
    let prior=state.resume[ticker];
    let index=prior?.page_index || 0;
    // Smaller pages are an operational transport repair, not a sampling limit.
    let params=prior?prior.next_params:{'timestamp.gt':state.start_ns,'timestamp.lte':state.end_ns,sort:'timestamp',order:'asc',limit:state.transport.retry_small_page_tickers.includes(ticker)?state.transport.retry_page_limit:state.transport.default_page_limit};
    let join=null;
    if(prior&&prior.last_sip_timestamp&&prior.cursor_page_limit&&prior.cursor_page_limit<budget.default_page_limit){
      join=prior.next_params;params={'timestamp.gte':prior.last_sip_timestamp,'timestamp.lte':state.end_ns,sort:'timestamp',order:'asc',limit:budget.default_page_limit};
    }
    const seen=new Set();
    while(params) {
      if(halted)throw Error('BATCH_STOPPED_AFTER_TIMEOUT');
      const key=JSON.stringify(params);if(seen.has(key))throw Error('CURSOR_LOOP');seen.add(key);
      if(Date.now()-started>=budget.batch_seconds*1000 || calls>=budget.batch_requests || bytes+reservedBytes+budget.page_bytes>budget.batch_decoded_bytes)throw Error('BATCH_BUDGET_CHECKPOINT');
      const request={path:'/v3/trades/'+ticker,params};
      const attempt=Date.now()+'-'+worker+'-'+calls;
      calls++;reservedBytes+=budget.page_bytes;
      let response,timer;
      try {
        await save(state.root+'/attempts/'+attempt+'.json',{request,started_at:new Date().toISOString(),page_index:index});
        const timeout=Math.min(budget.request_timeout_seconds*1000,budget.batch_seconds*1000-(Date.now()-started));
        response=await Promise.race([tools.mcp__codex_apps__massive_call_api(request),new Promise((_,reject)=>{timer=setTimeout(()=>{halted=true;reject(Error('CONNECTOR_TIMEOUT'));},timeout);})]);
      } catch(error) {await save(state.root+'/errors/'+attempt+'.json',{request,error:String(error)});throw error;}
      finally {clearTimeout(timer);reservedBytes-=budget.page_bytes;}
      const decodedBytes=JSON.stringify(response).length;
      if(decodedBytes>budget.page_bytes)throw Error('PAGE_DECODED_BYTES_BUDGET');
      bytes+=decodedBytes;
      const result=response.structuredContent?.result || (response.content||[]).filter(x=>x.type==='text').map(x=>x.text).join('\n');
      if(response.isError) {await save(state.root+'/errors/'+attempt+'.json',{request,error:result});throw Error(result.slice(0,500));}
      const marker='\n\nNext page available.';
      const pos=result.indexOf(marker);
      let csv=(pos<0?result:result.slice(0,pos)).trimEnd()+'\n';
      const next=result.match(/params=(\{[^\n]+\})/);
      if(pos>=0&&!next)throw Error('NEXT_CURSOR_NOT_PARSEABLE');
      if(!csv.split('\n')[0].includes('sip_timestamp'))throw Error('UNRECOGNIZED_MCP_RESPONSE '+result.slice(0,500));
      if(csv.includes('[truncated'))throw Error('TRUNCATED_EXPORT');
      const rows=csv.trimEnd().split('\n').length-1;
      const nextParams=next?JSON.parse(next[1]):null;
      const capture={...request,coverage_join:join?'TIMESTAMP_OVERLAP_TAIL':undefined,prior_next_params:join||undefined,page_index:index,expected_rows:rows,next_params:nextParams,csv,
        metadata:pos<0?'Terminal connector response; no next-page hint':result.slice(pos),
        retrieved_at:new Date().toISOString(),http_status:null,http_headers:null,transport:'MASSIVE_REST_VIA_MCP',
        attempt_id:attempt,decoded_connector_bytes:decodedBytes,row_count_source:'complete CSV export; equivalence to store_as/SQL checked separately'};
      const size=JSON.stringify(capture).length;
      if(size>budget.page_bytes)throw Error('PAGE_BYTES_BUDGET');

      const filename=state.root+'/raw/'+ticker+'/page-'+String(index).padStart(5,'0')+'.json';
      await save(filename,capture);
      const sealed=await tools.exec_command({cmd:'.venv/bin/python -m market_lab.census seal '+shellQuote(filename),workdir:cwd,max_output_tokens:500});
      if(sealed.exit_code!==0)throw Error(sealed.output);
      index++;params=nextParams;join=null;
    }
  }
  await Promise.all(Array.from({length:budget.max_workers},(_,worker)=>(async()=>{
    while(cursor<state.tickers.length) {
      const ticker=state.tickers[cursor++];
      try {await one(ticker,worker);complete++;if(complete%25===0)notify({complete:complete+state.completed_before_batch,total:state.population_total,calls,bytes});}
      catch(error){errors.push({ticker,error:String(error)});notify(errors.at(-1));if(/BUDGET|TIMEOUT/.test(String(error)))break;}
    }
  })()));
  const summary={transport_policy:state.transport,started_at:new Date(started).toISOString(),elapsed_seconds:(Date.now()-started)/1000,calls,bytes,complete,completed_before_batch:state.completed_before_batch,errors};
  await save(state.root+'/batches/'+started+'.json',summary);
  text(summary);
})();
