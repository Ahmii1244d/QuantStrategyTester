# ============================== WEB UI =====================================
# Imported by tester_app.py — kept separate so the HTML/JS never collides with
# shell heredocs during editing.
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

LOGIN_USERNAME = "ahmad"
LOGIN_PASSWORD = "Ahmizay"

LOGIN_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>PropLab Login</title>
<style>
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:linear-gradient(135deg,#0f172a,#111827 40%,#1f2937);font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;color:#e5e7eb}
.card{width:min(420px,90vw);background:rgba(15,23,42,.88);border:1px solid rgba(148,163,184,.25);border-radius:16px;padding:28px 28px 20px;box-shadow:0 25px 60px rgba(0,0,0,.35)}
h1{margin:0 0 8px;font-size:26px;letter-spacing:.5px}
p{margin:0 0 20px;color:#a5b4cf}
label{display:block;font-size:12px;color:#9fb0c4;margin:12px 0 6px;text-transform:uppercase;letter-spacing:.7px}
input{width:100%;background:#0b1120;border:1px solid #334155;color:#f8fafc;border-radius:10px;padding:12px 14px;font-size:15px}
input:focus{outline:none;border-color:#60a5fa;box-shadow:0 0 0 3px rgba(96,165,250,.18)}
button{margin-top:18px;width:100%;padding:12px 16px;border:0;border-radius:10px;background:linear-gradient(135deg,#3b82f6,#2563eb);color:#fff;font-weight:700;cursor:pointer}
button:hover{background:linear-gradient(135deg,#2563eb,#1d4ed8)}
.error{margin-top:14px;padding:10px 12px;background:rgba(127,29,29,.35);border:1px solid rgba(248,113,113,.45);border-radius:10px;color:#fecaca;display:none}
.status{margin-top:10px;font-size:12px;color:#93c5fd}
</style></head><body>
  <div class="card">
    <h1>PropLab Access</h1>
    <p>Enter your credentials to continue.</p>
    <form id="loginForm">
      <label for="username">Username</label>
      <input id="username" name="username" type="text" autocomplete="username" required>
      <label for="password">Password</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required>
      <button type="submit">Log in</button>
    </form>
    <div id="error" class="error"></div>
  </div>
<script>
const form = document.getElementById('loginForm');
const error = document.getElementById('error');
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  error.style.display = 'none';
  const body = JSON.stringify({
    username: document.getElementById('username').value.trim(),
    password: document.getElementById('password').value
  });
  const res = await fetch('/api/login', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body
  });
  const data = await res.json().catch(() => ({}));
  if (res.ok && data.ok) {
    window.location.reload();
    return;
  }
  error.textContent = data.message || 'Invalid username or password.';
  error.style.display = 'block';
});
</script></body></html>"""

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
    <div><label>Consistency: best DAY cap (%, 0=off)</label><input id="best_day_pct"></div>
    <div><label>Consistency: best TRADE cap (%, 0=off)</label><input id="best_trade_pct"></div>
  </div>
  <div style="font-size:11px;color:#5b6675;margin-top:8px">
    What most firms call the <b>consistency rule</b> IS the best-DAY rule: your largest winning day
    may not exceed X% of total profit (typical caps 20-45%). The best-TRADE cap is the separate,
    less common variant applied to a single trade. Set either to 0 to switch that rule off.
    Lot-size consistency is not simulated: this engine risks a fixed fraction on every trade, so
    max/avg position risk is always exactly 1.000 and such a rule could never trigger.
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
  ['balance','phase1','phase2','daily_loss','max_loss','risk_pct','min_days','best_day_pct','best_trade_pct']
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
  ['balance','phase1','phase2','daily_loss','max_loss','risk_pct','min_days','best_day_pct','best_trade_pct']
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

  // ================= FINAL VERDICT =================
  if(r.sequential && r.trust){
    const F=r.sequential.full, T=r.trust, E2=r.edge||{};
    h+='<div class="card" style="border-color:#2f4a86">'
     +'<div class="grid">'
     +'<div class="m"><div class="lab">Strategy quality</div><div class="val" style="font-size:17px">'+T.hold_label+'</div></div>'
     +'<div class="m"><div class="lab">Prop risk posture</div><div class="val" style="font-size:17px">'+T.posture+'</div></div>'
     +'<div class="m"><div class="lab">FULL 2-STEP sequential pass</div><div class="val" style="color:#8ab4f8">'+F.pass_pct.toFixed(1)+'%</div></div>'
     +'<div class="m"><div class="lab">Median total calendar days</div><div class="val">'+dash(F.med_days)+'</div></div>'
     +'</div>'
     +'<div style="margin-top:12px;font-size:13px;color:#c3cede;line-height:1.6">'
     +'At '+r.prop.risk_pct+'% risk on $'+Number(r.prop.start).toLocaleString()+', this strategy completed BOTH phases in <b>'
     +F.pass_pct.toFixed(1)+'%</b> of real-order historical simulations (n='+r.sequential.starts+' start points). '
     +'Median completion was <b>'+dash(F.med_days)+' calendar days</b> ('+dash(F.med_trades)+' trades); the 90th percentile was '+dash(F.d90)+' days. '
     +'Holdout expectancy was <b>'+T.hold_expR+'R</b> across '+T.hold_n+' trades (t '+T.hold_t+'), and the inverted strategy returned '+dash(E2.inverted)+'R. '
     +'These are measured historical figures, not predictions.</div></div>';
  }

  // ================= DO NOT MISREAD =================
  h+='<div class="warn"><b>IMPORTANT &mdash; how to read this report</b>'
   +'<ul style="margin:8px 0 0 18px;padding:0;line-height:1.7">'
   +'<li>A backtest is not a guarantee of future performance.</li>'
   +'<li>Shuffled Monte Carlo is not the same as historical-order sequential testing.</li>'
   +'<li>Phase&nbsp;1 pass probability is <b>not</b> full 2-step pass probability.</li>'
   +'<li>One historical path is not a probability estimate.</li>'
   +'<li>Positive holdout expectancy alone is not sufficient evidence of a real edge.</li>'
   +'<li>Lower risk improves account survival but increases time-to-target.</li>'
   +'<li>Higher risk reduces expected time-to-target but increases drawdown/path risk.</li>'
   +'</ul></div>';

  // ================= PROP CHALLENGE RESULTS =================
  if(r.prop){ const P=r.prop, M=P.math||{}, BD=r.best_day||{};
    h+='<div class="card"><div style="font-size:14px;color:#8ab4f8;font-weight:700;margin-bottom:3px">PROP CHALLENGE RESULTS</div>'
     +'<div style="font-size:11px;color:#5b6675;margin-bottom:12px">Every figure below is driven by ACCOUNT SETTINGS and recomputes when you change them.</div>'
     +'<div class="grid">'
     +'<div class="m"><div class="lab">Account</div><div class="val" style="font-size:17px">$'+Number(P.start).toLocaleString()+'</div></div>'
     +'<div class="m"><div class="lab">Risk per trade</div><div class="val" style="font-size:17px">'+P.risk_pct+'%</div></div>'
     +'<div class="m"><div class="lab">Phase 1 target</div><div class="val" style="font-size:17px">'+P.phase1_tgt+'%</div></div>'
     +'<div class="m"><div class="lab">Phase 2 target</div><div class="val" style="font-size:17px">'+P.phase2_tgt+'%</div></div>'
     +'<div class="m"><div class="lab">Daily loss</div><div class="val" style="font-size:17px">'+P.daily_loss+'%</div></div>'
     +'<div class="m"><div class="lab">Maximum loss</div><div class="val" style="font-size:17px">'+P.max_loss+'%</div></div>'
     +'<div class="m"><div class="lab">Minimum trading days</div><div class="val" style="font-size:17px">'+dash(r.sequential?r.sequential.min_days:null)+'</div></div>'
     +'<div class="m"><div class="lab">Best Day Rule</div><div class="val" style="font-size:17px">'
       +(BD.enabled?(BD.threshold+'% cap'):'off')+'</div></div>'
     +'</div>'
     +'<div style="margin-top:12px"><table>'
     +'<tr><th>Exact account math</th><th>Value</th></tr>'
     +'<tr><td>1R</td><td>$'+dash(M.one_R)+'</td></tr>'
     +'<tr><td>Phase 1 target</td><td>$'+dash(M.p1_target_usd)+'</td></tr>'
     +'<tr><td>Phase 2 target</td><td>$'+dash(M.p2_target_usd)+'</td></tr>'
     +'<tr><td>Daily loss limit</td><td>-$'+dash(M.daily_usd)+'</td></tr>'
     +'<tr><td>Maximum loss</td><td>-$'+dash(M.maxloss_usd)+'</td></tr>'
     +'<tr><td>R required for Phase 1 (arithmetic)</td><td>'+dash(M.p1_R_required)+'R</td></tr>'
     +'<tr><td>R required for Phase 2 (arithmetic)</td><td>'+dash(M.p2_R_required)+'R</td></tr>'
     +'</table><div style="font-size:11px;color:#5b6675;margin-top:6px">'
     +'R required is a simple target/risk conversion. It is NOT an estimate of how many trades are needed &mdash; '
     +'losing trades mean the actual trade count is far higher.</div></div></div>';
  }

  // ================= REALITY CHECK =================
  if(r.sequential && r.mc_joint){
    const gap = r.mc_joint.both_pct - r.sequential.full.pass_pct;
    const bad = gap > 5;
    h+='<div class="'+(bad?'warn':'card')+'"'+(bad?'':' style="border-color:#2f4a86"')+'>'
     +'<div style="font-size:13px;font-weight:700;margin-bottom:6px">REALITY CHECK &mdash; SHUFFLED vs REAL ORDER</div>'
     +'<div class="row"><span>Shuffled Monte Carlo, full 2-step pass</span><b>'+r.mc_joint.both_pct.toFixed(1)+'%</b></div>'
     +'<div class="row"><span>Sequential real-order, full 2-step pass</span><b>'+r.sequential.full.pass_pct.toFixed(1)+'%</b></div>'
     +'<div class="row"><span>Difference</span><b style="color:'+(gap>0?'#ff9b9b':'#7ee2a0')+'">'
       +(gap>0?'+':'')+gap.toFixed(1)+' percentage points</b></div>'
     +'<div style="margin-top:8px;font-size:12px;line-height:1.6">'
     +(bad
       ? 'Shuffled results are <b>optimistic here</b>. Randomising trade order breaks up real losing clusters. The sequential result preserves historical clustering and should receive more weight.'
       : 'Shuffled and real-order results are close, so trade-order clustering is not distorting the picture. The sequential number is still the one to weight.')
     +'</div></div>';
  }

  // ================= A. SHUFFLED MONTE CARLO =================
  if(r.mc_joint){ const J=r.mc_joint;
    h+='<div class="card"><div style="font-size:13px;color:#8ab4f8;font-weight:700">A. SHUFFLED MONTE CARLO &mdash; TRADE ORDER RANDOMIZED</div>'
     +'<div style="font-size:11px;color:#5b6675;margin:4px 0 10px">'+J.nsims+' simulations. Trade order is randomized, which deliberately destroys real losing clusters. '
     +'Both phases are simulated jointly, so the both-phase figure is a true <b>Joint Monte Carlo Pass Probability</b> &mdash; not Phase1 &times; Phase2.</div>'
     +'<table><tr><th></th><th>Pass</th><th>Max loss</th><th>Daily loss</th><th>Never reached</th></tr>'
     +'<tr><td>Phase 1</td><td>'+J.p1.PASS.toFixed(1)+'%</td><td>'+J.p1.FAIL_MAXLOSS.toFixed(1)+'%</td><td>'+J.p1.FAIL_DAILY.toFixed(1)+'%</td><td>'+J.p1.TIMEOUT.toFixed(1)+'%</td></tr>'
     +'<tr><td>Phase 2 <span style="color:#5b6675">(given P1 passed)</span></td><td>'+J.p2_cond.PASS.toFixed(1)+'%</td><td>'+J.p2_cond.FAIL_MAXLOSS.toFixed(1)+'%</td><td>'+J.p2_cond.FAIL_DAILY.toFixed(1)+'%</td><td>'+J.p2_cond.TIMEOUT.toFixed(1)+'%</td></tr>'
     +'</table>'
     +'<div class="row" style="margin-top:8px"><span><b>Joint Monte Carlo pass probability (both phases)</b></span><b style="color:#8ab4f8">'+J.both_pct.toFixed(1)+'%</b></div>'
     +'<div class="row"><span>Typical trades to Phase 1 / Phase 2 / total</span><b>'+dash(J.med_trades_p1)+' / '+dash(J.med_trades_p2)+' / '+dash(J.med_trades_total)+'</b></div>'
     +'<div class="row"><span>Typical drawdown / worst drawdown</span><b>'+J.typ_dd.toFixed(1)+'% / '+J.worst_dd.toFixed(1)+'%</b></div>'
     +'<div class="row"><span>Typical losing streak / worst</span><b>'+dash(J.typ_streak)+' / '+dash(J.worst_streak)+' trades</b></div>'
     +'</div>';
  }

  // ================= B. REAL-ORDER SEQUENTIAL =================
  if(r.sequential){ const S=r.sequential, P1=S.p1, P2=S.p2, F=S.full;
    const prow=function(o){return '<td>'+(o===null||o===undefined?'&mdash;':o.toFixed(1)+'%')+'</td>';};
    h+='<div class="card" style="border-color:#2f4a86"><div style="font-size:13px;color:#8ab4f8;font-weight:700">B. REAL-ORDER SEQUENTIAL &mdash; HISTORICAL TRADE ORDER PRESERVED</div>'
     +'<div style="font-size:11px;color:#5b6675;margin:4px 0 10px">Each historical trade is used in its actual chronological order; losing clusters are preserved. '
     +'A challenge is started at every one of the '+S.starts+' historical trades.</div>'
     +'<table><tr><th></th><th>Pass</th><th>Max loss</th><th>Daily loss</th><th>Never reached</th></tr>'
     +'<tr><td>Phase 1 <span style="color:#5b6675">(all starts)</span></td>'+prow(P1.PASS)+prow(P1.FAIL_MAXLOSS)+prow(P1.FAIL_DAILY)+prow(P1.TIMEOUT)+'</tr>'
     +'<tr><td>Phase 2 <span style="color:#5b6675">(conditional)</span></td>'+prow(P2.PASS)+prow(P2.FAIL_MAXLOSS)+prow(P2.FAIL_DAILY)+prow(P2.TIMEOUT)+'</tr>'
     +'</table>'
     +'<div style="font-size:11px;color:#5b6675;margin:6px 0 10px">Phase 2 row = <b>P(Phase 2 pass | Phase 1 passed)</b>, measured on the '
     +P2.evaluated+' paths that actually completed Phase 1. It is NOT the overall probability of completing Phase 2.</div>'
     +'<table><tr><th>Timing (calendar days)</th><th>Median</th><th>25th</th><th>75th</th><th>90th</th><th>Worst</th></tr>'
     +'<tr><td>Phase 1</td><td>'+dash(P1.med_days)+'</td><td>'+dash(P1.d25)+'</td><td>'+dash(P1.d75)+'</td><td>'+dash(P1.d90)+'</td><td>'+dash(P1.worst_days)+'</td></tr>'
     +'<tr><td>Phase 2</td><td>'+dash(P2.med_days)+'</td><td>'+dash(P2.d25)+'</td><td>'+dash(P2.d75)+'</td><td>'+dash(P2.d90)+'</td><td>'+dash(P2.worst_days)+'</td></tr>'
     +'<tr><td><b>Full 2-step</b></td><td><b>'+dash(F.med_days)+'</b></td><td>&mdash;</td><td>'+dash(F.d75)+'</td><td>'+dash(F.d90)+'</td><td>'+dash(F.worst_days)+'</td></tr>'
     +'</table>'
     +'<div style="margin-top:10px;padding-top:10px;border-top:1px solid #242a33">'
     +'<div class="row"><span><b>SEQUENTIAL FULL 2-STEP PASS</b></span><b style="color:#8ab4f8;font-size:16px">'+F.pass_pct.toFixed(1)+'%</b></div>'
     +'<div class="row"><span>Full sequential failure</span><b>'+F.fail_pct.toFixed(1)+'%</b></div>'
     +'<div class="row"><span>Phase 1 passed but Phase 2 failed</span><b>'+F.p1_pass_p2_fail_pct.toFixed(1)+'%</b></div>'
     +'<div class="row"><span>Phase 1 failed</span><b>'+F.p1_fail_pct.toFixed(1)+'%</b></div>'
     +'<div class="row"><span>Median total trades</span><b>'+dash(F.med_trades)+'</b></div>'
     +'</div></div>';
  }

  // ================= C. ONE HISTORICAL PATH =================
  if(r.deterministic){ const D=r.deterministic;
    const NM={'PASS':'PASSED','FAIL_MAXLOSS':'FAILED (max loss)','FAIL_DAILY':'FAILED (daily loss)','TIMEOUT':'target not reached','NOT REACHED':'NOT REACHED'};
    const nm=function(x){return NM[x]||x;};
    h+='<div class="card"><div style="font-size:13px;color:#93a0b0;font-weight:700">C. ONE HISTORICAL PATH &mdash; DETERMINISTIC</div>'
     +'<div style="font-size:11px;color:#5b6675;margin:4px 0 10px">A single realisation: the actual trade sequence from the first trade onward. '
     +'<b>This is one path, not a probability.</b></div>'
     +'<div class="row"><span>Phase 1 result</span><b>'+nm(D.p1_outcome)+'</b></div>'
     +'<div class="row"><span>Phase 2 result</span><b>'+nm(D.p2_outcome)+'</b></div>'
     +'<div class="row"><span>Full challenge</span><b>'+D.full+'</b></div>'
     +'<div class="row"><span>Trades to Phase 1 / Phase 2 / total</span><b>'+dash(D.p1_trades)+' / '+dash(D.p2_trades)+' / '+dash(D.total_trades)+'</b></div>'
     +'<div class="row"><span>Calendar days to Phase 1 / Phase 2 / total</span><b>'+dash(D.p1_days)+' / '+dash(D.p2_days)+' / '+dash(D.total_days)+'</b></div>'
     +'<div class="row"><span>Worst balance / final balance</span><b>$'+Math.round(D.worst_balance).toLocaleString()+' / $'+Math.round(D.final_balance).toLocaleString()+'</b></div>'
     +'<div class="row"><span>Maximum drawdown on this path</span><b>'+D.max_dd_pct.toFixed(1)+'%</b></div>'
     +'</div>';
  }

  // ================= TIME TO TARGET =================
  if(r.prop && r.sequential){ const P=r.prop, S=r.sequential;
    h+='<div class="card"><div style="font-size:13px;color:#8ab4f8;font-weight:700;margin-bottom:3px">TIME TO TARGET</div>'
     +'<div style="font-size:11px;color:#5b6675;margin-bottom:10px">Calendar days include weekends and periods with no trade. '
     +'They are not trading days, not bars, and not trades &mdash; each is labelled separately.</div>'
     +'<div class="row"><span>Trade frequency</span><b>'+dash(P.trades_per_year)+' trades/year</b></div>'
     +'<div class="row"><span>Average calendar days between trades</span><b>'+dash(P.avg_days_between)+'</b></div>'
     +'<div class="row"><span>Distinct days on which it traded</span><b>'+dash(P.active_days)+' trading days</b></div>'
     +'<div class="row"><span>Phase 1 &mdash; median trades / days / 75th / 90th</span><b>'
       +dash(S.p1.med_trades)+' trades &middot; '+dash(S.p1.med_days)+' / '+dash(S.p1.d75)+' / '+dash(S.p1.d90)+' days</b></div>'
     +'<div class="row"><span>Phase 2 &mdash; median trades / days / 75th / 90th</span><b>'
       +dash(S.p2.med_trades)+' trades &middot; '+dash(S.p2.med_days)+' / '+dash(S.p2.d75)+' / '+dash(S.p2.d90)+' days</b></div>'
     +'<div class="row"><span><b>Full 2-step &mdash; median / 75th / 90th / worst</b></span><b>'
       +dash(S.full.med_days)+' / '+dash(S.full.d75)+' / '+dash(S.full.d90)+' / '+dash(S.full.worst_days)+' days</b></div>'
     +'</div>';
  }

  // ================= RISK COMPARISON =================
  if(r.risk_table && r.risk_table.length){
    h+='<div class="card"><div style="font-size:13px;color:#8ab4f8;font-weight:700;margin-bottom:3px">RISK COMPARISON</div>'
     +'<div style="font-size:11px;color:#5b6675;margin-bottom:10px">Identical strategy and identical trades in every row &mdash; only the account risk setting changes.</div>'
     +'<div style="overflow-x:auto"><table><tr><th>Risk</th><th>P1 seq</th><th>P2 seq|P1</th><th>FULL 2-step seq</th><th>MC both (shuffled)</th><th>Max loss</th><th>Daily loss</th><th>Median days</th><th>Typ DD</th><th>Worst DD</th></tr>';
    r.risk_table.forEach(function(x){
      var cur = Math.abs(x.risk - r.prop.risk_pct) < 1e-9;
      h+='<tr'+(cur?' style="background:#1b2330"':'')+'><td>'+x.risk.toFixed(2)+'%'+(cur?' <span style="color:#8ab4f8">&larr;</span>':'')+'</td>'
       +'<td>'+x.seq_p1.toFixed(1)+'%</td><td>'+x.seq_p2_cond.toFixed(1)+'%</td>'
       +'<td><b>'+x.seq_full.toFixed(1)+'%</b></td><td>'+x.mc_both.toFixed(1)+'%</td>'
       +'<td>'+x.maxloss.toFixed(1)+'%</td><td>'+x.daily.toFixed(1)+'%</td>'
       +'<td>'+dash(x.med_days)+'</td><td>'+x.typ_dd.toFixed(1)+'%</td>'
       +'<td style="color:'+(x.worst_dd>=r.prop.max_loss?'#ff9b9b':'#c3cede')+'">'+x.worst_dd.toFixed(1)+'%</td></tr>';
    });
    h+='</table></div><div style="font-size:11px;color:#5b6675;margin-top:6px">'
     +'Worst DD is the 95th-percentile shuffled drawdown; values at or above your '+r.prop.max_loss+'% maximum-loss limit are shown in red.</div></div>';
  }

  // ================= STRATEGY EDGE =================
  if(r.edge){ const E=r.edge, T=r.trust||{};
    h+='<div class="card"><div style="font-size:13px;color:#8ab4f8;font-weight:700;margin-bottom:3px">STRATEGY EDGE</div>'
     +'<div style="font-size:11px;color:#5b6675;margin-bottom:10px">Measured in R. These figures describe the strategy only &mdash; changing account settings must never move them.</div>'
     +'<div class="row"><span>Development expectancy</span><b style="color:'+rcol(E.dev)+'">'+E.dev+'R</b></div>'
     +'<div class="row"><span>Validation expectancy</span><b style="color:'+rcol(E.val)+'">'+E.val+'R</b></div>'
     +'<div class="row"><span>Holdout expectancy</span><b style="color:'+rcol(E.hold)+'">'+E.hold+'R</b></div>'
     +'<div class="row"><span>Holdout trade count</span><b>'+E.hold_n+(E.hold_n<100?' <span class="pill bad">SMALL HOLDOUT SAMPLE</span>':'')+'</b></div>'
     +'<div class="row"><span>Holdout t-stat</span><b style="color:'+((E.hold_t>=2)?'#7ee2a0':'#ffd88a')+'">'+dash(E.hold_t)+'</b></div>'
     +'<div class="row"><span>Overall t-stat</span><b style="color:'+((E.overall_t>=2)?'#7ee2a0':'#ffd88a')+'">'+dash(E.overall_t)+'</b></div>'
     +'<div class="row"><span>Profit factor</span><b>'+E.pf+'</b></div>'
     +'<div class="row"><span>Win rate</span><b>'+E.win+'%</b></div>'
     +'<div class="row"><span>Sharpe</span><b>'+E.sharpe+'</b></div>'
     +'<div class="row"><span>Trade count</span><b>'+E.trades+'</b></div>'
     +'<div class="row"><span>3x cost expectancy</span><b style="color:'+rcol(E.cost3x)+'">'+dash(E.cost3x)+'R</b></div>'
     +'<div class="row"><span>Benchmark expectancy ('+E.bench_aligned+'-only drift)</span><b>'+E.bench+'R</b></div>'
     +'<div class="row"><span>Edge vs benchmark</span><b style="color:'+rcol(E.edge_vs_bench)+'">'+E.edge_vs_bench+'R</b></div>'
     +'<div class="row"><span>Inverted expectancy (BUY&#8596;SELL)</span><b style="color:'+rcol(-E.inverted)+'">'+E.inverted+'R</b></div>'
     +'<div style="margin-top:10px"><span class="pill '+((T.hold_label==='CLEAR EDGE')?'ok':'bad')+'">'+dash(T.hold_label)+'</span>'
     +'<span style="font-size:11px;color:#5b6675;margin-left:8px">rule: holdout &gt; '+dash(T.exec_threshold)+'R execution noise AND t &ge; 2.0 AND n &ge; 15</span></div>'
     +'</div>';
  }

  // ================= PROP RISK PROFILE =================
  if(r.prop && r.mc_joint && r.sequential){ const P=r.prop, J=r.mc_joint, S=r.sequential, T=r.trust||{};
    h+='<div class="card"><div style="font-size:13px;color:#8ab4f8;font-weight:700;margin-bottom:3px">PROP RISK PROFILE</div>'
     +'<div style="font-size:11px;color:#5b6675;margin-bottom:10px">Account-dependent. These DO change with your risk setting; the STRATEGY EDGE figures above do not.</div>'
     +'<div class="row"><span>Risk per trade</span><b>'+P.risk_pct+'% &middot; posture '+dash(T.posture)+'</b></div>'
     +'<div class="row"><span>Typical / worst drawdown (shuffled)</span><b>'+J.typ_dd.toFixed(1)+'% / '+J.worst_dd.toFixed(1)+'%</b></div>'
     +'<div class="row"><span>Typical / worst losing streak</span><b>'+dash(J.typ_streak)+' / '+dash(J.worst_streak)+' trades</b></div>'
     +'<div class="row"><span>Worst streak at this risk</span><b>-'+dash(T.streak_exposure_pct)+'% of account</b></div>'
     +'<div class="row"><span>Max-loss probability (sequential P1)</span><b>'+S.p1.FAIL_MAXLOSS.toFixed(1)+'%</b></div>'
     +'<div class="row"><span>Daily-loss probability (sequential P1)</span><b>'+S.p1.FAIL_DAILY.toFixed(1)+'%</b></div>'
     +'<div class="row"><span>Phase 1 pass (sequential)</span><b>'+S.p1.PASS.toFixed(1)+'%</b></div>'
     +'<div class="row"><span>Phase 2 pass (sequential, given P1)</span><b>'+S.p2.PASS.toFixed(1)+'%</b></div>'
     +'<div class="row"><span><b>Full challenge pass (sequential)</b></span><b style="color:#8ab4f8">'+S.full.pass_pct.toFixed(1)+'%</b></div>'
     +'<div class="row"><span>Median time to pass</span><b>'+dash(S.full.med_days)+' calendar days</b></div>'
     +'</div>';
  }

  // ================= CONTRIBUTION / YEARS / BEST DAY =================
  if(r.concentration && r.concentration.levels && r.concentration.levels.length){
    h+='<div class="card"><div style="font-size:13px;color:#93a0b0;font-weight:700;margin-bottom:8px">TRADE CONTRIBUTION CHECK</div>'
     +'<table><tr><th>Winners removed</th><th>Expectancy without them</th><th>Their share of total R</th></tr>';
    r.concentration.levels.forEach(function(L){
      h+='<tr><td>top '+L.k+'</td><td style="color:'+rcol(L.expR_without)+'">'+L.expR_without.toFixed(4)+'R</td><td>'+L.pct_of_totR.toFixed(1)+'%</td></tr>';});
    h+='</table><div style="font-size:11px;color:#5b6675;margin-top:6px">Baseline expectancy '+r.concentration.expR.toFixed(4)+'R. '
     +'If removing a few winners collapses the edge, the result depends on outliers.</div></div>';
  }
  if(r.yearly && r.yearly.length){
    h+='<div class="card"><div style="font-size:13px;color:#93a0b0;font-weight:700;margin-bottom:8px">YEAR / REGIME BREAKDOWN</div>'
     +'<table><tr><th>Year</th><th>Trades</th><th>Expectancy</th><th>PF</th><th>Win rate</th></tr>';
    r.yearly.forEach(function(y){h+='<tr><td>'+y.year+'</td><td>'+y.n+'</td><td style="color:'+rcol(y.expR)+'">'+y.expR.toFixed(3)+'R</td><td>'+y.pf.toFixed(2)+'</td><td>'+y.win.toFixed(1)+'%</td></tr>';});
    h+='</table><div style="font-size:11px;color:#5b6675;margin-top:6px">Not every year needs to be profitable. This shows whether the edge is concentrated in one period.</div></div>';
  }
  if(r.consistency){ const C=r.consistency;
    const line=function(nm,o){
      return '<tr><td>'+nm+'</td><td>$'+Math.round(o.best).toLocaleString()+'</td><td>'
        +(o.pct===null?'&mdash;':o.pct.toFixed(1)+'%')+'</td><td>'
        +(o.enabled?o.threshold+'%':'<span style="color:#5b6675">off</span>')+'</td><td>'
        +(o.compliant===null?'&mdash;':(o.compliant
            ?'<span class="pill ok">PASS</span>'
            :'<span class="pill bad">NOT YET SATISFIED</span>'))+'</td></tr>';};
    h+='<div class="card"><div style="font-size:13px;color:#93a0b0;font-weight:700;margin-bottom:3px">CONSISTENCY RULES</div>'
     +'<div style="font-size:11px;color:#5b6675;margin-bottom:10px">What firms call "the consistency rule" is the best-DAY rule &mdash; the same mechanic, not a second constraint. Best-TRADE is the distinct variant.</div>'
     +'<table><tr><th>Rule</th><th>Largest</th><th>Share of profit</th><th>Cap</th><th>Status</th></tr>'
     +line('Best winning DAY',C.day)+line('Best single TRADE',C.trade)+'</table>'
     +'<div class="row" style="margin-top:8px"><span>Total positive-day profit</span><b>$'+Math.round(C.total_positive).toLocaleString()+'</b></div>'
     +'<div class="row"><span>Trading days (with &gt;1 trade)</span><b>'+C.total_trading_days+' ('+C.days_with_multiple_trades+')</b></div>'
     +'<div style="font-size:11px;color:#5b6675;margin-top:8px">A violation is <b>not</b> an instant failure: the simulation keeps trading until the ratio complies, as a real challenge requires. '
     +'Lot-size consistency is reported, not simulated &mdash; '+C.lot_size.note+'.</div></div>';
  }

  // ================= WHAT SHOULD I TRUST =================
  if(r.trust){ const T=r.trust;
    h+='<div class="card"><div style="font-size:13px;color:#93a0b0;font-weight:700;margin-bottom:8px">WHAT SHOULD I TRUST?</div>'
     +'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px">'
     +'<div><div style="font-size:11px;color:#7ee2a0;text-transform:uppercase;margin-bottom:4px">Higher trust</div><ul style="margin:0 0 0 16px;padding:0;line-height:1.7;font-size:13px">'
     +T.higher_trust.map(function(x){return '<li>'+x+'</li>';}).join('')+'</ul></div>'
     +'<div><div style="font-size:11px;color:#ff9b9b;text-transform:uppercase;margin-bottom:4px">Lower trust</div><ul style="margin:0 0 0 16px;padding:0;line-height:1.7;font-size:13px">'
     +T.lower_trust.map(function(x){return '<li>'+x+'</li>';}).join('')+'</ul></div></div></div>';
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

  h+='<div class="card"><div style="font-size:13px;color:#8ab4f8;font-weight:700;margin-bottom:3px">ACCOUNT EQUITY</div>'
   +'<div style="font-size:11px;color:#5b6675;margin-bottom:8px">'+(r.sizing||'')
   +' &middot; one point per trade. Dashed lines are your configured Phase&nbsp;1 target and maximum-loss floor.</div>'
   +'<canvas id="eq"></canvas>'
   +'<div style="font-size:13px;color:#8ab4f8;font-weight:700;margin:14px 0 3px">DRAWDOWN FROM PEAK</div>'
   +'<div style="font-size:11px;color:#5b6675;margin-bottom:8px">How far below its own high-water mark the account sat, in percent.</div>'
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
  if(r.text_report){
    h+='<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px">'
     +'<div><div style="font-size:13px;color:#8ab4f8;font-weight:700">FULL REPORT &mdash; PLAIN TEXT</div>'
     +'<div style="font-size:11px;color:#5b6675">Everything above, in one copyable block.</div></div>'
     +'<div><button class="sm" id="copybtn" style="margin:0" onclick="copyReport()">COPY REPORT</button>'
     +'<button class="sm" onclick="dlReport()">DOWNLOAD .TXT</button></div></div>'
     +'<pre id="rptxt" style="margin:0;max-height:460px;overflow:auto;background:#0b0e12;border:1px solid #242a33;'
     +'border-radius:8px;padding:14px;font:12px/1.5 Consolas,Monaco,monospace;color:#c3cede;white-space:pre;'
     +'user-select:text;-webkit-user-select:text">'
     + String(r.text_report).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
     +'</pre></div>';
  }
  h+='<button class="sm" style="margin:0" onclick="dl()">DOWNLOAD CODE</button>';
  o.innerHTML=h;
  drawEquity('eq', r.equity, r.equity_dates, r.equity_levels);
  drawDrawdown('dd', r.drawdown, r.equity_dates, (r.prop ? r.prop.max_loss : null));
}
function fmtMoney(v){
  var a=Math.abs(v);
  if(a>=1e6) return '$'+(v/1e6).toFixed(2)+'M';
  if(a>=1e3) return '$'+(v/1e3).toFixed(1)+'k';
  return '$'+Math.round(v);
}
function niceStep(range,target){
  var raw=range/Math.max(target,1), p=Math.pow(10,Math.floor(Math.log(raw)/Math.LN10));
  var n=raw/p; var m=(n<=1?1:n<=2?2:n<=5?5:10);
  return m*p;
}
function prepCanvas(c,cssH){
  var dpr=window.devicePixelRatio||1;
  var w=c.clientWidth||700;
  c.style.height=cssH+'px';
  c.width=Math.round(w*dpr); c.height=Math.round(cssH*dpr);
  var x=c.getContext('2d'); x.setTransform(dpr,0,0,dpr,0,0);
  return {x:x,w:w,h:cssH};
}
// ---------------- EQUITY ----------------
function drawEquity(id,data,dates,levels){
  var c=document.getElementById(id); if(!c||!data||!data.length) return;
  var P=prepCanvas(c,260), x=P.x, W=P.w, H=P.h;
  var ml=64, mr=12, mt=14, mb=26;
  var pw=W-ml-mr, ph=H-mt-mb;
  x.clearRect(0,0,W,H);

  var lo=Math.min.apply(null,data), hi=Math.max.apply(null,data);
  if(levels){
    if(levels.max_loss_floor!=null) lo=Math.min(lo,levels.max_loss_floor);
    if(levels.p1_target!=null)      hi=Math.max(hi,levels.p1_target);
    if(levels.start!=null){ lo=Math.min(lo,levels.start); hi=Math.max(hi,levels.start); }
  }
  var pad=(hi-lo)*0.08||1; lo-=pad; hi+=pad;
  var Y=function(v){ return mt+ph-((v-lo)/(hi-lo))*ph; };
  var X=function(i){ return ml+(i/(data.length-1))*pw; };

  // grid + y labels
  var step=niceStep(hi-lo,5);
  x.font='10px -apple-system,Segoe UI,Roboto,sans-serif'; x.textAlign='right';
  for(var v=Math.ceil(lo/step)*step; v<=hi; v+=step){
    var yy=Y(v);
    x.strokeStyle='#1e242c'; x.lineWidth=1;
    x.beginPath(); x.moveTo(ml,yy); x.lineTo(ml+pw,yy); x.stroke();
    x.fillStyle='#5b6675'; x.fillText(fmtMoney(v),ml-6,yy+3);
  }
  // reference levels
  function refLine(val,col,label){
    if(val==null||val<lo||val>hi) return;
    var yy=Y(val);
    x.save(); x.setLineDash([5,4]); x.strokeStyle=col; x.lineWidth=1.5;
    x.beginPath(); x.moveTo(ml,yy); x.lineTo(ml+pw,yy); x.stroke(); x.restore();
    x.fillStyle=col; x.textAlign='left'; x.font='10px -apple-system,Segoe UI,Roboto,sans-serif';
    x.fillText(label,ml+4,yy-4); x.textAlign='right';
  }
  if(levels){
    refLine(levels.start,'#5b6675','start');
    refLine(levels.p1_target,'#7ee2a0','Phase 1 target');
    refLine(levels.max_loss_floor,'#ff6b6b','MAX LOSS - account dies');
  }
  // peak-to-trough shading (largest drawdown)
  var peak=data[0],pi=0,bi=0,bj=0,worst=0;
  for(var i=0;i<data.length;i++){
    if(data[i]>peak){peak=data[i];pi=i;}
    var d=peak-data[i];
    if(d>worst){worst=d;bi=pi;bj=i;}
  }
  if(worst>0&&bj>bi){
    x.fillStyle='rgba(224,85,85,.13)';
    x.fillRect(X(bi),mt,X(bj)-X(bi),ph);
  }
  // area under equity
  var g=x.createLinearGradient(0,mt,0,mt+ph);
  g.addColorStop(0,'rgba(42,109,244,.28)'); g.addColorStop(1,'rgba(42,109,244,0)');
  x.beginPath(); x.moveTo(X(0),Y(data[0]));
  for(var i=1;i<data.length;i++) x.lineTo(X(i),Y(data[i]));
  x.lineTo(X(data.length-1),mt+ph); x.lineTo(X(0),mt+ph); x.closePath();
  x.fillStyle=g; x.fill();
  // equity line
  x.strokeStyle='#4d8cff'; x.lineWidth=1.8; x.beginPath();
  for(var i=0;i<data.length;i++){ var px=X(i),py=Y(data[i]); if(i) x.lineTo(px,py); else x.moveTo(px,py); }
  x.stroke();
  // x labels (dates)
  if(dates&&dates.length===data.length){
    x.fillStyle='#5b6675'; x.font='10px -apple-system,Segoe UI,Roboto,sans-serif';
    var ticks=Math.min(6,dates.length);
    for(var k=0;k<ticks;k++){
      var idx=Math.round(k*(dates.length-1)/(ticks-1));
      x.textAlign=(k===0?'left':(k===ticks-1?'right':'center'));
      x.fillText(String(dates[idx]).slice(0,7),X(idx),H-8);
    }
  }
  x.textAlign='left'; x.fillStyle='#93a0b0'; x.font='10px -apple-system,Segoe UI,Roboto,sans-serif';
  if(worst>0) x.fillText('shaded = largest peak-to-trough decline ('+fmtMoney(worst)+')',ml+4,mt+10);
}
// ---------------- DRAWDOWN ----------------
function drawDrawdown(id,data,dates,maxLossPct){
  var c=document.getElementById(id); if(!c||!data||!data.length) return;
  var P=prepCanvas(c,180), x=P.x, W=P.w, H=P.h;
  var ml=64, mr=12, mt=12, mb=26;
  var pw=W-ml-mr, ph=H-mt-mb;
  x.clearRect(0,0,W,H);

  var worst=Math.min.apply(null,data);           // most negative
  var lo=Math.min(worst,-(maxLossPct||0))*1.12; if(lo>=0) lo=-1;
  var hi=0;
  var Y=function(v){ return mt+((v-hi)/(lo-hi))*ph; };
  var X=function(i){ return ml+(i/(data.length-1))*pw; };

  var step=niceStep(Math.abs(lo),4);
  x.font='10px -apple-system,Segoe UI,Roboto,sans-serif'; x.textAlign='right';
  for(var v=0; v>=lo; v-=step){
    var yy=Y(v);
    x.strokeStyle='#1e242c'; x.lineWidth=1;
    x.beginPath(); x.moveTo(ml,yy); x.lineTo(ml+pw,yy); x.stroke();
    x.fillStyle='#5b6675'; x.fillText(v.toFixed(0)+'%',ml-6,yy+3);
  }
  if(maxLossPct){
    var yy=Y(-maxLossPct);
    x.save(); x.setLineDash([5,4]); x.strokeStyle='#ff6b6b'; x.lineWidth=1.5;
    x.beginPath(); x.moveTo(ml,yy); x.lineTo(ml+pw,yy); x.stroke(); x.restore();
    x.fillStyle='#ff6b6b'; x.textAlign='left';
    x.fillText('max loss limit -'+maxLossPct+'%',ml+4,yy-4);
  }
  x.beginPath(); x.moveTo(X(0),Y(0));
  for(var i=0;i<data.length;i++) x.lineTo(X(i),Y(data[i]));
  x.lineTo(X(data.length-1),Y(0)); x.closePath();
  x.fillStyle='rgba(224,85,85,.30)'; x.fill();
  x.strokeStyle='#e05555'; x.lineWidth=1.5; x.beginPath();
  for(var i=0;i<data.length;i++){ var px=X(i),py=Y(data[i]); if(i) x.lineTo(px,py); else x.moveTo(px,py); }
  x.stroke();
  // worst marker
  var wi=data.indexOf(worst);
  if(wi>=0){
    x.fillStyle='#ff9b9b';
    x.beginPath(); x.arc(X(wi),Y(worst),3,0,6.283); x.fill();
    x.textAlign=(wi>data.length*0.75?'right':'left');
    x.fillText('worst '+worst.toFixed(1)+'%',X(wi)+(wi>data.length*0.75?-6:6),Y(worst)+12);
  }
  if(dates&&dates.length===data.length){
    x.fillStyle='#5b6675';
    var ticks=Math.min(6,dates.length);
    for(var k=0;k<ticks;k++){
      var idx=Math.round(k*(dates.length-1)/(ticks-1));
      x.textAlign=(k===0?'left':(k===ticks-1?'right':'center'));
      x.fillText(String(dates[idx]).slice(0,7),X(idx),H-8);
    }
  }
}
function copyReport(){
  var el=document.getElementById('rptxt'); if(!el) return;
  var txt=el.textContent||el.innerText||'';
  var done=function(){
    var b=document.getElementById('copybtn');
    if(b){ var o=b.textContent; b.textContent='COPIED'; setTimeout(function(){b.textContent=o;},1400); }
  };
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(txt).then(done,function(){fallbackCopy(txt,done);});
  } else fallbackCopy(txt,done);
}
function fallbackCopy(txt,done){
  var ta=document.createElement('textarea');
  ta.value=txt; ta.style.position='fixed'; ta.style.opacity='0';
  document.body.appendChild(ta); ta.select();
  try{ document.execCommand('copy'); done(); }catch(e){}
  document.body.removeChild(ta);
}
function dlReport(){
  var el=document.getElementById('rptxt'); if(!el) return;
  var b=new Blob([el.textContent],{type:'text/plain'});
  var a=document.createElement('a'); a.href=URL.createObjectURL(b);
  a.download='proplab_report_'+new Date().toISOString().slice(0,10)+'.txt'; a.click();
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

        def _auth_ok(self):
            cookie = self.headers.get("Cookie", "")
            for part in cookie.split(";"):
                key, sep, value = part.partition("=")
                if sep and key.strip() == "prop_lab_auth" and value.strip() == "true":
                    return True
            return False

        def _require_auth(self):
            if self._auth_ok():
                return True
            self._send(401, json.dumps({"ok": False, "error": "UNAUTHORIZED",
                                       "message": "Login required."}))
            return False

        def do_GET(self):
            if self.path in ("/", "/login"):
                if self.path == "/" and self._auth_ok():
                    return self._send(200, PAGE, "text/html; charset=utf-8")
                return self._send(200, LOGIN_PAGE, "text/html; charset=utf-8")
            if self.path == "/logout":
                self.send_response(200)
                self.send_header("Set-Cookie", "prop_lab_auth=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT")
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(LOGIN_PAGE.encode("utf-8"))
                return
            if not self.path.startswith("/api/"):
                self._send(404, "{}")
                return
            if not self._require_auth():
                return
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
            raw = self.rfile.read(ln) or b"{}"
            content_type = self.headers.get("Content-Type", "")
            try:
                if "application/x-www-form-urlencoded" in content_type:
                    from urllib.parse import parse_qs
                    body = {k: v[0] if isinstance(v, list) and len(v) == 1 else v
                            for k, v in parse_qs(raw.decode("utf-8")).items()}
                else:
                    body = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                body = {}

            if self.path == "/api/login":
                username = str(body.get("username", "")).strip()
                password = str(body.get("password", "")).strip()
                if username == LOGIN_USERNAME and password == LOGIN_PASSWORD:
                    self.send_response(200)
                    self.send_header("Set-Cookie", "prop_lab_auth=true; Path=/; HttpOnly; SameSite=Lax")
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
                    return
                return self._send(401, json.dumps({"ok": False, "error": "UNAUTHORIZED",
                                                 "message": "Invalid username or password."}))

            if not self._require_auth():
                return
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
