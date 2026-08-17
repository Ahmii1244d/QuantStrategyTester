# ============================== WEB UI =====================================
# Imported by tester_app.py — kept separate so the HTML/JS never collides with
# shell heredocs during editing.
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<title>Quant Strategy Tester</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0f1216;color:#e8eaed;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:20px}
h1{font-size:20px;margin:0 0 16px;letter-spacing:.5px}
.bar{background:#171b21;border:1px solid #242a33;border-radius:10px;padding:12px 16px;margin-bottom:12px;
     display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.bar b{color:#8ab4f8}
button{background:#2a6df4;color:#fff;border:0;border-radius:8px;padding:10px 16px;font-size:14px;cursor:pointer}
button:hover{background:#1b5ae0}
button.sm{background:#2a3038;padding:7px 12px;font-size:13px;margin-left:6px}
button.sm:hover{background:#39414c}
button.big{width:100%;padding:18px;font-size:18px;font-weight:600;margin:12px 0}
textarea{width:100%;height:340px;background:#0b0e12;color:#d7e0ea;border:1px solid #242a33;border-radius:10px;
         padding:14px;font:13px/1.55 Consolas,Monaco,monospace;resize:vertical}
.card{background:#171b21;border:1px solid #242a33;border-radius:10px;padding:16px;margin-bottom:12px}
.verdict{text-align:center;padding:26px 16px}
.verdict .v{font-size:34px;font-weight:700;margin-bottom:6px}
.verdict .s{font-size:52px;font-weight:800;color:#8ab4f8}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.m{background:#0f1319;border:1px solid #232932;border-radius:8px;padding:12px}
.m .lab{font-size:11px;color:#93a0b0;text-transform:uppercase;letter-spacing:.6px}
.m .val{font-size:22px;font-weight:700;margin-top:4px}
.q{display:inline-block;width:15px;height:15px;line-height:15px;text-align:center;border-radius:50%;
   background:#2a3038;color:#9fb0c4;font-size:10px;cursor:pointer;margin-left:5px;vertical-align:middle}
.hint{display:none;margin-top:7px;font-size:12px;color:#9fb0c4;border-left:2px solid #2a6df4;padding-left:8px}
.row{display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid #1e242c;gap:10px}
.row:last-child{border:0}
.err{background:#2a1416;border:1px solid #6e2b30;border-radius:10px;padding:16px;margin-bottom:12px}
.err h3{margin:0 0 8px;color:#ff8a8a}
.warn{background:#2a2413;border:1px solid #6e5b2b;border-radius:10px;padding:14px;margin-bottom:12px;color:#ffd88a}
label{display:block;font-size:12px;color:#93a0b0;margin:8px 0 3px}
input{width:100%;background:#0b0e12;border:1px solid #242a33;color:#e8eaed;border-radius:7px;padding:9px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:6px 8px;text-align:right;border-bottom:1px solid #1e242c}
th:first-child,td:first-child{text-align:left}
th{color:#93a0b0;font-weight:500;font-size:11px;text-transform:uppercase}
.hide{display:none}
canvas{width:100%;height:180px;background:#0b0e12;border-radius:8px;border:1px solid #232932}
.pill{padding:3px 9px;border-radius:20px;font-size:12px;font-weight:600}
.ok{background:#12361f;color:#7ee2a0}.bad{background:#3a1618;color:#ff9b9b}
</style></head><body><div class="wrap">
<h1>QUANT STRATEGY TESTER</h1>

<div class="bar"><div id="dsinfo">Loading dataset...</div>
  <div><button class="sm" onclick="tog('dset')">DATA SETTINGS</button>
       <button class="sm" onclick="tog('acct')">ACCOUNT SETTINGS</button>
       <button class="sm" onclick="hist()">HISTORY</button></div></div>

<div class="card hide" id="dset">
  <label>Folder containing your CSV files</label><input id="dir">
  <label>Symbol (files must be named SYMBOL_TF.csv, e.g. XAUUSD_M30.csv)</label><input id="sym">
  <button class="sm" style="margin:12px 0 0 0" onclick="saveCfg()">SAVE DATASET</button>
</div>

<div class="card hide" id="acct">
  <div class="grid">
    <div><label>Account balance ($)</label><input id="balance"></div>
    <div><label>Phase 1 target (%)</label><input id="phase1"></div>
    <div><label>Phase 2 target (%)</label><input id="phase2"></div>
    <div><label>Max daily loss (%)</label><input id="daily_loss"></div>
    <div><label>Max total loss (%)</label><input id="max_loss"></div>
    <div><label>Risk per trade (%)</label><input id="risk_pct"></div>
    <div><label>Min trading days (optional)</label><input id="min_days"></div>
  </div>
  <button class="sm" style="margin:12px 0 0 0" onclick="saveCfg()">SAVE ACCOUNT</button>
</div>

<div class="card"><div style="font-size:12px;color:#93a0b0;margin-bottom:8px">STRATEGY CODE</div>
  <textarea id="code" spellcheck="false"></textarea></div>

<div style="display:flex;gap:10px">
  <button class="big" id="run" style="flex:2" onclick="test('fast')">FAST TEST</button>
  <button class="big" id="deep" style="flex:1;background:#3a2f6e" onclick="test('deep')">DEEP VALIDATION</button>
</div>
<div class="card hide" id="prog">
  <div style="display:flex;justify-content:space-between;margin-bottom:8px">
    <span id="pstage" style="font-size:13px;color:#c3cede">Working...</span>
    <span id="pelapsed" style="font-size:12px;color:#93a0b0">0.0s</span></div>
  <div style="height:8px;background:#0b0e12;border-radius:6px;overflow:hidden">
    <div id="pbar" style="height:100%;width:0%;background:#2a6df4;transition:width .2s"></div></div>
  <button class="sm" style="margin:12px 0 0 0;background:#3a1618" onclick="cancelTest()">CANCEL</button>
</div>
<div id="out"></div>
</div>
<script>
let CFG={};
function tog(id){document.getElementById(id).classList.toggle('hide')}
function q(id){const e=document.getElementById(id);e.style.display=(e.style.display=='block')?'none':'block'}
async function boot(){
  const r=await fetch('/api/init').then(x=>x.json());
  CFG=r.cfg; document.getElementById('code').value=r.code;
  document.getElementById('dir').value=CFG.dataset_dir;
  document.getElementById('sym').value=CFG.symbol;
  ['balance','phase1','phase2','daily_loss','max_loss','risk_pct','min_days']
    .forEach(k=>document.getElementById(k).value=CFG[k]);
  const d=r.ds; let s='';
  if(!d.ok){ s='<span style="color:#ff9b9b">! '+d.msg+'</span>'; }
  else{ const tfs=Object.keys(d.tfs); const f=d.tfs[tfs[0]];
    s='<b>DATASET</b> OK &nbsp;'+d.symbol+' &mdash; '+tfs.join(', ')
     +'<br><span style="font-size:12px;color:#93a0b0">'+String(f.first).slice(0,10)+' to '
     +String(f.last).slice(0,10)+' &middot; '+Number(f.rows).toLocaleString()+' candles ('+tfs[0]+')</span>'; }
  document.getElementById('dsinfo').innerHTML=s;
}
async function saveCfg(){
  const c={dataset_dir:document.getElementById('dir').value,symbol:document.getElementById('sym').value};
  ['balance','phase1','phase2','daily_loss','max_loss','risk_pct','min_days']
    .forEach(k=>c[k]=parseFloat(document.getElementById(k).value)||0);
  await fetch('/api/config',{method:'POST',body:JSON.stringify(c)});
  location.reload();
}
let POLL=null, CANCELLED=false;
function setBusy(on){
  document.getElementById('run').disabled=on;
  document.getElementById('deep').disabled=on;
  document.getElementById('prog').classList.toggle('hide',!on);
}
function cancelTest(){ CANCELLED=true; if(POLL)clearInterval(POLL); setBusy(false);
  document.getElementById('out').innerHTML='<div class="warn">Test cancelled. '
   +'The strategy may still be finishing in the background; you can start another test.</div>'; }
async function test(mode){
  CANCELLED=false; setBusy(true); document.getElementById('out').innerHTML='';
  document.getElementById('pbar').style.width='2%';
  document.getElementById('pstage').textContent='Starting '+(mode=='deep'?'deep validation':'fast test')+'...';
  let job;
  try{
    job=await fetch('/api/test',{method:'POST',
      body:JSON.stringify({code:document.getElementById('code').value,mode:mode})})
      .then(x=>x.json());
  }catch(e){ setBusy(false); return render({error:'ERROR',msg:String(e),hint:'Server not reachable.'}); }
  if(!job.job){ setBusy(false); return render({error:'ERROR',msg:'Could not start test.'}); }
  POLL=setInterval(async()=>{
    if(CANCELLED){ clearInterval(POLL); return; }
    let p;
    try{ p=await fetch('/api/progress',{method:'POST',body:JSON.stringify({job:job.job})}).then(x=>x.json()); }
    catch(e){ return; }
    document.getElementById('pstage').textContent=p.stage||'Working...';
    document.getElementById('pbar').style.width=(p.pct||0)+'%';
    document.getElementById('pelapsed').textContent=(p.elapsed||0).toFixed(1)+'s';
    if(p.done){ clearInterval(POLL); setBusy(false); render(p.result||{error:'ERROR',msg:'No result.'}); }
  }, 250);
}
function H(k,t){return '<span class="q" onclick="q(\''+k+'\')">?</span><div class="hint" id="'+k+'">'+t+'</div>'}
function pill(v){return v?'<span class="pill ok">POSITIVE</span>':'<span class="pill bad">NEGATIVE</span>'}
function fmtpct(v){return (v===null||v===undefined)?'&mdash;':v+'%'}
function dash(v){return (v===null||v===undefined)?'&mdash;':v}
function rcol(v){return (v>0)?'#7ee2a0':(v<0?'#ff9b9b':'#c3cede')}
function render(r){
  const o=document.getElementById('out');
  if(r.error){
    const map={'CODE ERROR':'CODE ERROR','STRATEGY ERROR':'STRATEGY ERROR','LOOKAHEAD':'INVALID TEST',
               'CANNOT_TEST':'CANNOT TEST','NO_TRADES':'NO TRADES','DATA':'DATA PROBLEM',
               'METRIC ERROR':'METRIC ERROR','TIMEOUT':'TEST TIMEOUT','SIGNAL LENGTH ERROR':'SIGNAL LENGTH ERROR'};
    let h='<div class="err"><h3>'+(map[r.error]||'ERROR')+'</h3>';
    if(r.line) h+='<div style="color:#ffd88a">Line '+r.line+'</div>';
    h+='<div style="margin:8px 0"><b>'+(r.msg||'')+'</b></div>';
    if(r.hint) h+='<div style="color:#c3cede">'+r.hint+'</div>';
    if(r.need){ h+='<div style="margin-top:12px">NEEDED:<br>';
      for(const k in r.need) h+=k+' '+(r.need[k]=='missing'?'MISSING':'ok')+'<br>';
      h+='<br>AVAILABLE: '+(r.avail||[]).join(', ')+'</div>'; }
    o.innerHTML=h+'</div>'; return;
  }
  const m=r.metrics,a=r.account,s=r.splits;
  let h='';
  if(r.audit && !r.audit.ok){
    h+='<div class="err"><h3>REPORT INCONSISTENT</h3>'
     +'<div style="margin:6px 0">Internal consistency checks failed. Numbers are shown below but must not be trusted &mdash; this is an engine bug.</div>';
    r.audit.checks.filter(c=>!c.ok).forEach(c=>h+='<div style="color:#ffd88a">&#10007; '+c.name+' &mdash; '+c.detail+'</div>');
    h+='</div>';
  } else if(r.audit && r.audit.ok){
    h+='<div style="text-align:center;font-size:12px;color:#7ee2a0;margin-bottom:10px">&#10003; '
     +r.audit.checks.length+' internal consistency checks passed</div>';
  }
  h+='<div class="card verdict"><div class="v">'+r.verdict[0]+' '+r.verdict[1]+'</div>'
   +'<div style="font-size:12px;color:#93a0b0;margin-top:10px">PROP SCORE'
   +H('hs','Primarily the probability of passing YOUR configured challenge, plus robustness: holdout edge by magnitude, survival at 3x cost, and outperformance vs a drift benchmark. Raw trade count and a fixed RR earn nothing; failing the edge gates caps the score and labels it NO CLEAR EDGE.')
   +'</div><div class="s">'+r.score+'<span style="font-size:22px;color:#5b6675">/100</span></div></div>';

  // ============ PROP CHALLENGE SIMULATION (the headline product) ============
  if(r.prop){ const P=r.prop;
    h+='<div class="card" style="border-color:#2f4a86">'
     +'<div style="font-size:14px;color:#8ab4f8;font-weight:700;letter-spacing:.4px;margin-bottom:3px">PROP CHALLENGE SIMULATION</div>'
     +'<div style="font-size:11px;color:#5b6675;margin-bottom:12px">'+dash(P.nsims)+' Monte-Carlo challenges on YOUR configured account &middot; every number below recomputes when you change ACCOUNT SETTINGS</div>'
     +'<div class="grid" style="margin-bottom:12px">'
     +'<div class="m"><div class="lab">Starting balance</div><div class="val" style="font-size:18px">$'+Number(P.start).toLocaleString()+'</div></div>'
     +'<div class="m"><div class="lab">Risk / trade</div><div class="val" style="font-size:18px">'+P.risk_pct+'%</div></div>'
     +'<div class="m"><div class="lab">Phase 1 / 2 target</div><div class="val" style="font-size:18px">'+P.phase1_tgt+'% / '+P.phase2_tgt+'%</div></div>'
     +'<div class="m"><div class="lab">Daily / Max loss</div><div class="val" style="font-size:18px">'+P.daily_loss+'% / '+P.max_loss+'%</div></div>'
     +'</div>'
     +'<div class="grid">'
     +'<div class="m"><div class="lab">Phase 1 pass'+H('hp1','Chance of reaching the Phase-1 target before a max-loss or daily-loss breach, over the Monte-Carlo challenges.')+'</div><div class="val">'+fmtpct(P.p1_pass)+'</div></div>'
     +'<div class="m"><div class="lab">Phase 2 pass</div><div class="val">'+fmtpct(P.p2_pass)+'</div></div>'
     +'<div class="m"><div class="lab">Pass BOTH phases</div><div class="val" style="color:#8ab4f8">'+fmtpct(P.both_pass)+'</div></div>'
     +'<div class="m"><div class="lab">Hit max loss first</div><div class="val" style="color:#ff9b9b">'+fmtpct(P.fail_maxloss)+'</div></div>'
     +'<div class="m"><div class="lab">Daily-loss breach</div><div class="val" style="color:#ff9b9b">'+fmtpct(P.fail_daily)+'</div></div>'
     +'</div>'
     +'<div style="margin-top:14px"><table>'
     +'<tr><th>Phase 1</th><th>Phase 2</th><th>Risk profile</th></tr>'
     +'<tr><td>Typical trades to pass: <b>'+dash(P.p1_med_trades)+'</b></td>'
        +'<td>Typical trades to pass: <b>'+dash(P.p2_med_trades)+'</b></td>'
        +'<td>Typical drawdown: <b>'+dash(P.typ_dd)+'%</b></td></tr>'
     +'<tr><td>Worst-case trades: <b>'+dash(P.p1_worst_trades)+'</b></td>'
        +'<td></td>'
        +'<td>Worst drawdown: <b>'+dash(P.worst_dd)+'%</b></td></tr>'
     +'<tr><td>Typical trading days: <b>'+dash(P.p1_typ_days)+'</b></td>'
        +'<td></td>'
        +'<td>Typical losing streak: <b>'+dash(P.typ_streak)+'</b></td></tr>'
     +'<tr><td>Worst trading days: <b>'+dash(P.p1_worst_days)+'</b></td>'
        +'<td></td>'
        +'<td>Worst losing streak: <b>'+dash(P.worst_streak)+'</b></td></tr>'
     +'</table></div></div>';
  }

  // ============ STRATEGY EDGE (is it real, or drift?) ============
  if(r.edge){ const E=r.edge; const noEdge=(''+E.hold_quality).indexOf('NO CLEAR')>=0;
    h+='<div class="card"><div style="font-size:14px;color:#8ab4f8;font-weight:700;letter-spacing:.4px;margin-bottom:4px">STRATEGY EDGE</div>'
     +'<div style="font-size:11px;color:#5b6675;margin-bottom:10px">A real edge beats the aligned drift benchmark AND its own inverse loses. Positive expectancy alone is not enough.</div>'
     +'<div class="row"><span>Development expectancy</span><b style="color:'+rcol(E.dev)+'">'+E.dev+'R</b></div>'
     +'<div class="row"><span>Validation expectancy</span><b style="color:'+rcol(E.val)+'">'+E.val+'R</b></div>'
     +'<div class="row"><span>Holdout expectancy '+H('heo','Unseen data the strategy was never tuned on. Compared against this engine\'s execution-noise floor, not just zero.')+'</span>'
        +'<b>'+E.hold+'R &middot; '+E.hold_n+' trades '
        +(noEdge?'<span class="pill bad">'+E.hold_quality+'</span>':'<span class="pill ok">CLEAR EDGE</span>')+'</b></div>'
     +'<div class="row"><span>Profit factor</span><b>'+E.pf+'</b></div>'
     +'<div class="row"><span>Win rate</span><b>'+E.win+'%</b></div>'
     +'<div class="row"><span>Sharpe</span><b>'+E.sharpe+'</b></div>'
     +'<div class="row"><span>Trade count</span><b>'+E.trades+'</b></div>'
     +'<div class="row"><span>Expectancy at 3x cost</span><b style="color:'+rcol(E.cost3x)+'">'+dash(E.cost3x)+'R</b></div>'
     +'<div class="row"><span>Benchmark expectancy ('+E.bench_aligned+'-only drift)</span><b>'+E.bench+'R</b></div>'
     +'<div class="row"><span><b>Edge vs benchmark</b> '+H('hev','Strategy expectancy minus the matched always-'+E.bench_aligned+' benchmark. If this is ~0, the strategy is just riding drift (e.g. gold\'s uptrend), not timing anything.')+'</span>'
        +'<b style="color:'+rcol(E.edge_vs_bench)+'">'+E.edge_vs_bench+'R</b></div>'
     +'<div class="row"><span>Inverted-strategy expectancy (BUY&#8596;SELL)</span><b style="color:'+rcol(-E.inverted)+'">'+E.inverted+'R</b></div>'
     +'<div style="font-size:11px;color:#5b6675;margin-top:8px">Long-only drift '+E.bench_long+'R &middot; Short-only drift '+E.bench_short+'R</div>'
     +'</div>';
  }

  if(r.edge_ok===false){
    h+='<div class="warn"><b>NO CLEAR EDGE</b><br>This strategy may still make money in the backtest, but it does not clearly beat the drift benchmark, its holdout edge, its inverse, or realistic costs. Passing the prop simulation here would not be reliable evidence of a repeatable edge.</div>';
  }
  if(r.exec_sensitive){
    h+='<div class="warn"><b>EXECUTION-SENSITIVE</b> ('+String(r.exec_threshold)+'R)<br>'
     +'Expectancy is smaller than this engine\'s measured execution uncertainty, so its <b>sign is not trustworthy</b> '
     +'from OHLC alone. Treat as "no clear edge" rather than a winner or loser. (Engine-specific calibration, not a universal law.)</div>';
  }

  h+='<div class="card"><div style="font-size:12px;color:#93a0b0;margin-bottom:8px">WHY THIS VERDICT</div>';
  (r.reasons||[]).forEach(x=>h+='<div class="row"><span>'+x[0]+' '+x[1]+'</span></div>');
  h+='</div>';

  if(r.low_exec) h+='<div class="warn"><b>LOW EXECUTION CONFIDENCE</b><br>Trades close very fast on this timeframe. '
   +'Your data does not contain enough detail to reproduce exact fills - treat these numbers as indicative.</div>';

  h+='<div class="card"><div class="grid">'
   +'<div class="m"><div class="lab">Profit factor'+H('h1','How much it made vs what it lost. Above 1 means it made more than it lost.')+'</div><div class="val">'+m.pf+'</div></div>'
   +'<div class="m"><div class="lab">Expectancy'+H('h2','Average won or lost per trade in risk units (R). Positive is better. Under about 0.04 is basically noise.')+'</div><div class="val">'+m.expR+'R</div></div>'
   +'<div class="m"><div class="lab">Win rate'+H('h3','Share of trades that won. A high win rate does not by itself mean a good strategy.')+'</div><div class="val">'+m.win+'%</div></div>'
   +'<div class="m"><div class="lab">Max drawdown'+H('h4','The biggest drop in the account before it recovered, as a % of the peak balance. Lower is safer.')+'</div><div class="val">'+m.maxdd+'%<span style="font-size:12px;color:#93a0b0"> / $'+(m.maxdd_usd||0).toLocaleString()+'</span></div></div>'
   +'<div class="m"><div class="lab">Trades'+H('h5','How many trades were tested. Under about 100 means the result may not be trustworthy.')+'</div><div class="val">'+m.trades+'</div></div>'
   +'<div class="m"><div class="lab">Sharpe'+H('h6','Return compared with how bumpy the ride was. Higher is generally better.')+'</div><div class="val">'+m.sharpe+'</div></div>'
   +'</div></div>';

  const oc={'PASS':'PASSED','FAIL_MAXLOSS':'FAILED (max loss)','FAIL_DAILY':'FAILED (daily loss)','TIMEOUT':'did not reach target'}[a.outcome]||a.outcome;
  h+='<div class="card"><div style="font-size:12px;color:#93a0b0;margin-bottom:8px">ACCOUNT SIMULATION'
   +H('hac','One deterministic run of your actual trades under the prop rules. Stops at the target or at a breach. Same sizing model as the Monte Carlo.')+'</div>'
   +'<div class="row"><span>Starting balance</span><b>$'+a.start.toLocaleString()+'</b></div>'
   +'<div class="row"><span>Phase 1 target</span><b>$'+a.target1.toLocaleString()+'</b></div>'
   +'<div class="row"><span>Daily loss limit</span><b>-$'+a.daily.toLocaleString()+'</b></div>'
   +'<div class="row"><span>Maximum loss</span><b>-$'+a.maxloss.toLocaleString()+'</b></div>'
   +'<div class="row"><span>Outcome</span><b>'+oc+'</b></div>'
   +'<div class="row"><span>Worst balance reached</span><b>$'+a.worst.toLocaleString()+'</b></div>'
   +'<div class="row"><span>Final balance</span><b>$'+a.final.toLocaleString()+'</b></div>'
   +'<div class="row"><span>Trades taken before it stopped</span><b>'+a.trades_taken+'</b></div></div>'
   +'<div style="font-size:11px;color:#5b6675;margin:6px 0 12px">'+(r.sizing||'')+'</div>';

  h+='<div class="card"><div style="font-size:12px;color:#93a0b0;margin-bottom:8px">EQUITY CURVE</div>'
   +'<canvas id="eq"></canvas><div style="font-size:12px;color:#93a0b0;margin:10px 0 8px">DRAWDOWN</div>'
   +'<canvas id="dd"></canvas></div>';

  h+='<div class="card"><div style="font-size:12px;color:#93a0b0;margin-bottom:8px">OUT-OF-SAMPLE'
   +H('h7','How it did on data it was never tuned on. The holdout is the most important number on this page.')+'</div>'
   +'<div class="row"><span>Development <span style="color:#5b6675">'+r.split_dates.dev+'</span></span><span>'+s.dev.expR+'R &middot; '+s.dev.n+' trades '+pill(s.dev.pos)+'</span></div>'
   +'<div class="row"><span>Validation <span style="color:#5b6675">'+r.split_dates.val+'</span></span><span>'+s.val.expR+'R &middot; '+s.val.n+' trades '+pill(s.val.pos)+'</span></div>'
   +'<div class="row"><span><b>Holdout</b> <span style="color:#5b6675">'+r.split_dates.hold+'</span></span><span>'+s.hold.expR+'R &middot; '+s.hold.n+' trades '+pill(s.hold.pos)+'</span></div></div>';

  if(r.cost&&r.cost.length){
    h+='<div class="card"><div style="font-size:12px;color:#93a0b0;margin-bottom:8px">COST TEST</div>';
    r.cost.forEach(c=>h+='<div class="row"><span>'+c.mult+'x cost</span><span>'+(c.pos?'PASS':'FAIL')+' &nbsp;'+c.expR+'R</span></div>');
    h+='<div class="row"><span><b>Cost robustness</b></span><b>'+(r.cost_ok?'GOOD':'WEAK')+'</b></div></div>';
  }

  h+='<div class="card"><div style="font-size:12px;color:#93a0b0;margin-bottom:8px">TRADES (last 200)</div>'
   +'<div style="max-height:300px;overflow:auto"><table><tr><th>Date</th><th>Side</th><th>Entry</th><th>SL</th><th>TP</th><th>R</th></tr>';
  (r.trades||[]).forEach(t=>h+='<tr><td>'+t.date+'</td><td>'+t.dir+'</td><td>'+t.entry+'</td><td>'+t.sl
   +'</td><td>'+t.tp+'</td><td style="color:'+(t.R>0?'#7ee2a0':'#ff9b9b')+'">'+t.R+'</td></tr>');
  h+='</table></div></div>';

  if(r.timing){
    const t=r.timing; let ts='';
    ['data_prep','lookahead','strategy','backtest','metrics','diagnostics','total'].forEach(k=>{
      if(t[k]!==undefined) ts+='<span style="margin-right:14px">'+k+': '+t[k].toFixed(2)+'s</span>';});
    h+='<div style="font-size:11px;color:#5b6675;margin:10px 0">'+(r.mode||'').toUpperCase()+' &middot; '+ts+'</div>';
  }
  h+='<button class="sm" style="margin:0" onclick="dl()">DOWNLOAD CODE</button>';
  o.innerHTML=h;
  draw('eq',r.equity,'#2a6df4'); draw('dd',r.drawdown,'#e05555');
}
function draw(id,d,col){
  const c=document.getElementById(id); if(!c||!d||!d.length) return;
  const w=c.width=c.clientWidth*2, hh=c.height=360, x=c.getContext('2d');
  const mn=Math.min.apply(null,d), mx=Math.max.apply(null,d), rg=(mx-mn)||1;
  x.strokeStyle=col; x.lineWidth=3; x.beginPath();
  d.forEach((v,i)=>{const px=i/(d.length-1)*w, py=hh-((v-mn)/rg)*(hh-20)-10;
    if(i) x.lineTo(px,py); else x.moveTo(px,py);});
  x.stroke();
}
function dl(){
  const b=new Blob([document.getElementById('code').value],{type:'text/plain'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(b);
  a.download='strategy_'+new Date().toISOString().slice(0,10)+'.py'; a.click();
}
async function hist(){
  const r=await fetch('/api/history').then(x=>x.json());
  let h='<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">'
   +'<span style="font-size:12px;color:#93a0b0">HISTORY &mdash; full reports are saved and reopenable anytime</span>'
   +(r.length?'<button class="sm" style="margin:0;background:#3a1618" onclick="clearHist()">CLEAR ALL</button>':'')+'</div>';
  if(!r.length){ h+='<div style="color:#93a0b0">No saved runs yet.</div></div>'; document.getElementById('out').innerHTML=h; return; }
  h+='<table><tr><th>When</th><th>Verdict</th><th>Score</th><th>Trades</th><th>Holdout</th><th></th></tr>';
  r.slice().reverse().forEach(x=>{
    const id=x.id||'';
    h+='<tr><td>'+x.date+(x.mode?' <span style="color:#5b6675">'+x.mode+'</span>':'')+'</td>'
     +'<td>'+x.verdict+'</td><td>'+x.score+'</td><td>'+x.trades+'</td><td>'+x.hold_expR+'R</td>'
     +'<td style="white-space:nowrap">'
     +(id?'<button class="sm" style="margin:0;padding:5px 9px" onclick="openReport(\''+id+'\')">OPEN FULL REPORT</button>'
          +'<button class="sm" style="margin-left:6px;padding:5px 9px;background:#3a1618" onclick="delReport(\''+id+'\')">DELETE</button>'
        :'<span style="color:#5b6675">summary only</span>')
     +'</td></tr>';
  });
  document.getElementById('out').innerHTML=h+'</table></div>';
}
async function openReport(id){
  document.getElementById('out').innerHTML='<div class="card">Loading report...</div>';
  const r=await fetch('/api/report',{method:'POST',body:JSON.stringify({id:id})}).then(x=>x.json());
  render(r);
}
async function delReport(id){
  if(!confirm('Delete this saved report?')) return;
  await fetch('/api/history_delete',{method:'POST',body:JSON.stringify({id:id})});
  hist();
}
async function clearHist(){
  if(!confirm('Delete ALL saved reports? This cannot be undone.')) return;
  await fetch('/api/history_clear',{method:'POST',body:JSON.stringify({})});
  hist();
}
boot();
</script></body></html>"""


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def _send(self, code, body, ctype="application/json"):
            b = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path == "/":
                return self._send(200, PAGE, "text/html; charset=utf-8")
            if self.path == "/api/init":
                cfg = app.load_cfg()
                return self._send(200, json.dumps(
                    {"cfg": cfg, "ds": app.scan_dataset(cfg), "code": app.DEFAULT_STRATEGY},
                    default=str))
            if self.path == "/api/history":
                return self._send(200, json.dumps(app.load_hist()))
            self._send(404, "{}")

        def do_POST(self):
            ln = int(self.headers.get("Content-Length", 0))
            try: body = json.loads(self.rfile.read(ln) or "{}")
            except Exception: body = {}
            if self.path == "/api/config":
                cfg = app.load_cfg(); cfg.update(body); app.save_cfg(cfg)
                return self._send(200, json.dumps({"ok": True}))
            if self.path == "/api/test":
                cfg = app.load_cfg()
                mode = body.get("mode", "fast")
                job_id = app.start_job(body.get("code", ""), cfg, mode)
                return self._send(200, json.dumps({"job": job_id}))
            if self.path == "/api/progress":
                return self._send(200, json.dumps(app.job_status(body.get("job", "")),
                                                  default=str))
            if self.path == "/api/report":
                r = app.load_report(body.get("id", ""))
                return self._send(200, json.dumps(r or {"error": "NO_REPORT",
                                  "msg": "That report is no longer stored."}, default=str))
            if self.path == "/api/history_delete":
                app.delete_report(body.get("id", ""))
                return self._send(200, json.dumps({"ok": True}))
            if self.path == "/api/history_clear":
                app.clear_history()
                return self._send(200, json.dumps({"ok": True}))
            self._send(404, "{}")
    return Handler


def serve(app, port=None):
    import os
    # Cloud hosts (Render/Railway/Heroku) inject the port via $PORT and require
    # binding to 0.0.0.0. Locally, $PORT is unset and we use 5000 on all
    # interfaces (still reachable at http://127.0.0.1:5000).
    env_port = os.environ.get("PORT", "").strip()
    port = int(env_port) if env_port.isdigit() else (port or 5000)
    host = "0.0.0.0"
    print("\n  QUANT STRATEGY TESTER")
    print(f"  Listening on {host}:{port}  (local: http://127.0.0.1:{port})\n")
    HTTPServer((host, port), make_handler(app)).serve_forever()
