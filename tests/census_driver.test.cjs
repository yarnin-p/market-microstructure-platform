const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const source=fs.readFileSync('scripts/census_mcp_batch.js','utf8');
async function run(mode,requestBudget=10,workers=1){
 const files=[],requests=[];let summary;
 const state={root:'/tmp/census-test',tickers:['A','B'],resume:{},completed_before_batch:0,population_total:2,start_ns:'1',end_ns:'100',
  transport:{default_page_limit:50000,retry_page_limit:5000,retry_small_page_tickers:['A'],max_workers:workers,batch_seconds:10,batch_requests:requestBudget,batch_decoded_bytes:1000000,page_bytes:100000,request_timeout_seconds:2}};
 const tools={
  exec_command:async ({cmd})=>({exit_code:0,output:cmd.includes('broker-state')?JSON.stringify(state):'sealed'}),
  apply_patch:async patch=>{const p=patch.match(/Add File: (.+)\n\+(.+)\n\*\*\* End Patch/s);files.push({path:p[1],body:JSON.parse(p[2])});return {};},
  mcp__codex_apps__massive_call_api:async request=>{
   requests.push(request);
   if(request.path.endsWith('/B'))return {isError:true,structuredContent:{result:'provider unavailable'}};
   const csv='sip_timestamp,participant_timestamp,sequence_number,price,size\n10,10,1,1.1,100\n';
   const next='\n\n\nNext page available. To fetch, call call_api with path="/v3/trades/A" and params={"cursor":"two"}';
   return {structuredContent:{result:csv+(!request.params.cursor||mode==='loop'?next:'')}};
  }
 };
 await new Function('tools','text','notify',source)(tools,x=>summary=x,()=>{});
 return {files,requests,summary};
}
test('complete multi-page export, smaller retry pages and explicit provider error',async()=>{
 const r=await run('normal');assert.equal(r.requests.length,3);assert.equal(r.requests[0].params.limit,5000);assert.deepEqual(r.requests[1].params,{cursor:'two'});
 const pages=r.files.filter(x=>x.path.includes('/raw/'));assert.equal(pages.length,2);assert.equal(pages[0].body.next_params.cursor,'two');assert.equal(pages[1].body.next_params,null);
 assert.equal(r.summary.complete,1);assert.equal(r.summary.errors[0].ticker,'B');assert.equal(r.files.filter(x=>x.path.includes('/attempts/')).length,3);
});
test('budget leaves resumable partial pages, never a complete stream',async()=>{
 const r=await run('normal',1);assert.equal(r.requests.length,1);assert.equal(r.summary.complete,0);assert.match(r.summary.errors[0].error,/BUDGET/);
 assert.equal(r.files.filter(x=>x.path.includes('/raw/'))[0].body.next_params.cursor,'two');
});
test('cursor loops stop before a repeated third request',async()=>{
 const r=await run('loop');assert.equal(r.requests.filter(x=>x.path.endsWith('/A')).length,2);assert.match(r.summary.errors[0].error,/CURSOR_LOOP/);
});

test('concurrent workers reserve request slots before asynchronous I/O',async()=>{
 const r=await run('normal',1,2);assert.equal(r.requests.length,1);assert.equal(r.summary.calls,1);assert.equal(r.summary.complete,0);
});
