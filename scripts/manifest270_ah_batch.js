// Approval-gated seed270 supplement: previous-day AH aggregates only. This driver never calls /v3/trades.
return (async()=>{
 const cwd='/Users/yarnin/Documents/yarnin-p/market-microstructure-platform';
 const initial=await tools.exec_command({cmd:'.venv/bin/python -m market_lab.manifest270 state',workdir:cwd,max_output_tokens:7000});
 if(initial.exit_code!==0)throw Error(initial.output);
 const state=JSON.parse(initial.output),cfg=state.config,started=Date.now();
 let calls=0,bytes=0,cursor=0,done=0;const errors=[];
 const quote=s=>"'"+s.replaceAll("'","'\\''")+"'";
 async function save(path,obj){const r=await tools.apply_patch('*** Begin Patch\n*** Add File: '+path+'\n+'+JSON.stringify(obj)+'\n*** End Patch');if(r?.isError)throw Error(JSON.stringify(r));}
 async function one(ticker,worker){
  if(Date.now()-started>=cfg.batch_seconds*1000||calls>=cfg.batch_requests||bytes>cfg.batch_decoded_bytes-33554432*4)throw Error('BATCH_BUDGET_CHECKPOINT');
  const request={path:'/v2/aggs/ticker/'+ticker+'/range/1/minute/'+cfg.ah_from_ms+'/'+cfg.ah_to_ms,params:{adjusted:false,sort:'asc',limit:50000}};
  const attempt=Date.now()+'-'+worker+'-'+calls;calls++;
  await save(state.root+'/attempts/'+attempt+'.json',{request,started_at:new Date().toISOString(),kind:'AGGREGATES_ONLY'});
  let response;
  try{response=await tools.mcp__codex_apps__massive_call_api(request);}
  catch(error){await save(state.root+'/errors/'+attempt+'.json',{ticker,request,error:String(error)});throw error;}
  bytes+=JSON.stringify(response).length;
  const text=response.structuredContent?.result||(response.content||[]).filter(x=>x.type==='text').map(x=>x.text).join('\n');
  if(response.isError)throw Error(text.slice(0,400));
  if(text.includes('Next page available'))throw Error('AGGREGATE_PAGINATION_UNEXPECTED_FOR_1441_MINUTES_WITH_50000_LIMIT');
  const file=state.root+'/raw-aggregates/'+ticker+'.json';
  await save(file,{...request,ticker,csv:text,retrieved_at:new Date().toISOString(),decoded_connector_bytes:JSON.stringify(response).length,next_params:null,transport:'MASSIVE_REST_VIA_MCP'});
  const imported=await tools.exec_command({cmd:'.venv/bin/python -m market_lab.manifest270 import '+quote(file),workdir:cwd,max_output_tokens:500});
  if(imported.exit_code!==0)throw Error(imported.output.slice(-700));
 }
 await Promise.all(Array.from({length:cfg.max_workers},(_,worker)=>(async()=>{
  while(cursor<state.tickers.length){const ticker=state.tickers[cursor++];
   try{await one(ticker,worker);done++;if(done%25===0)notify({aggregate_complete:done+state.completed_before_batch,population:state.population_total,calls,bytes,tick_requests:0});}
   catch(error){errors.push({ticker,error:String(error)});notify(errors.at(-1));if(String(error).includes('BUDGET'))break;}
  }
 })()));
 const result={kind:'AGGREGATES_ONLY',done,completed_before_batch:state.completed_before_batch,calls,bytes,errors,elapsed_seconds:(Date.now()-started)/1000};
 await save(state.root+'/aggregate-batches/'+started+'.json',result);text(result);
})();
