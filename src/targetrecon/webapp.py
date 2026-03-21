"""TargetRecon Flask web application."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from pathlib import Path

from targetrecon import __version__ as _version

from flask import Flask, jsonify, redirect, render_template_string, request, url_for

app = Flask(
    __name__,
    static_folder=str(Path(__file__).parent / "static"),
    static_url_path="/static",
)
app.secret_key = os.urandom(24)

# Unique ID generated once at startup — clients use it to detect server restarts
import uuid as _boot_uuid
_BOOT_ID = str(_boot_uuid.uuid4())

# ── AI Agent Chat Panel (injected into both INDEX_HTML and REPORT_HTML) ──────
_CHAT_PANEL_HTML = r"""
<!-- marked.js optional enhancement; built-in renderer used as fallback -->
<script src="https://cdn.jsdelivr.net/npm/marked@4.3.0/marked.min.js" async></script>

<!-- AI Agent toggle button -->
<button id="chatToggleBtn" onclick="toggleChat()" style="position:fixed;bottom:1.4rem;right:1.4rem;z-index:9999;padding:.6rem 1.1rem;font-size:13px;font-weight:600;border-radius:50px;box-shadow:0 4px 20px rgba(31,111,235,.5)">
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:.35rem"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>AI Agent
</button>

<!-- Report overlay panel (iframe — keeps chat JS state alive) -->
<div id="reportOverlay" style="display:none;position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,.6);backdrop-filter:blur(2px)">
  <div style="position:absolute;inset:2rem;background:#0d1117;border:1px solid #30363d;border-radius:10px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 8px 40px rgba(0,0,0,.6)">
    <div style="display:flex;align-items:center;justify-content:space-between;padding:.6rem 1rem;border-bottom:1px solid #30363d;flex-shrink:0">
      <span style="font-size:13px;font-weight:600;color:#e6edf3">Full Report</span>
      <button onclick="closeReport()" style="background:none;border:1px solid #30363d;border-radius:5px;color:#8b949e;font-size:13px;padding:.2rem .7rem;cursor:pointer">&#10005; Close</button>
    </div>
    <iframe id="reportFrame" src="" style="flex:1;border:none;width:100%;background:#0d1117"></iframe>
  </div>
</div>

<!-- AI Agent Chat Panel -->
<div id="agentChatPanel" class="chat-hidden">
  <!-- Resize handles -->
  <div id="chatRzTop"  style="position:absolute;top:0;left:6px;right:6px;height:5px;cursor:ns-resize;z-index:10"></div>
  <div id="chatRzLeft" style="position:absolute;top:6px;left:0;bottom:6px;width:5px;cursor:ew-resize;z-index:10"></div>
  <div id="chatRzCorner" style="position:absolute;top:0;left:0;width:10px;height:10px;cursor:nwse-resize;z-index:11"></div>

  <!-- Header -->
  <div class="chat-hdr" onclick="if(_minimized)chatMinimize()" style="cursor:default" title="Click to restore when minimised">
    <div class="chat-hdr-title">
      <div class="chat-live-dot"></div>
      <span id="chatModelBadge" style="font-size:11px;background:#21262d;border:1px solid #30363d;border-radius:4px;padding:.1rem .45rem;color:#8b949e;font-weight:500;cursor:pointer" onclick="toggleSettings()">claude-sonnet-4-6</span>
      AI Agent
    </div>
    <div class="chat-hdr-btns">
      <button id="chatStopBtn" onclick="chatStop()" title="Stop generation" style="display:none;color:#f85149;border-color:#f8514944">&#9632; Stop</button>
      <button onclick="toggleSettings()" title="Model &amp; API key">&#9881;</button>
      <button onclick="newChat()" title="New conversation">&#8635;</button>
      <button id="chatMinBtn" onclick="chatMinimize()" title="Minimise">&#8212;</button>
      <button onclick="toggleChat()" title="Close">&#10005;</button>
    </div>
  </div>

  <!-- Settings panel (hidden by default) -->
  <div id="chatSettings" style="display:none;flex-shrink:0;border-bottom:1px solid #30363d;background:#0d1117;padding:.75rem 1rem;">
    <div style="font-size:11.5px;font-weight:600;color:#8b949e;text-transform:uppercase;letter-spacing:.06em;margin-bottom:.6rem">Model &amp; API Key</div>

    <!-- Provider tabs -->
    <div style="display:flex;gap:.35rem;margin-bottom:.6rem" id="providerTabs">
      <button class="prov-tab active" data-prov="anthropic" onclick="selProv('anthropic',this)">Anthropic</button>
      <button class="prov-tab" data-prov="openai"    onclick="selProv('openai',this)">OpenAI</button>
      <button class="prov-tab" data-prov="groq"      onclick="selProv('groq',this)">Groq</button>
    </div>

    <!-- Model select -->
    <select id="chatModelSel" style="width:100%;background:#21262d;border:1px solid #30363d;border-radius:5px;color:#e6edf3;font-size:12px;padding:.35rem .5rem;margin-bottom:.5rem;outline:none">
    </select>

    <!-- API Key -->
    <div style="display:flex;gap:.4rem;align-items:center">
      <div style="position:relative;flex:1">
        <input id="chatApiKey" type="password" placeholder="Paste your API key here"
          style="width:100%;background:#21262d;border:1px solid #30363d;border-radius:5px;color:#e6edf3;font-size:12px;padding:.35rem .5rem;outline:none;transition:border-color .15s"
          oninput="onKeyInput()" onfocus="this.style.borderColor='#58a6ff'" onblur="this.style.borderColor='#30363d'">
      </div>
      <button id="testKeyBtn" onclick="testKey()"
        style="background:#21262d;border:1px solid #30363d;border-radius:5px;color:#8b949e;font-size:11px;padding:.32rem .7rem;cursor:pointer;white-space:nowrap;transition:border-color .15s,color .15s;flex-shrink:0">
        Test
      </button>
    </div>
    <div id="keyStatusBar" style="font-size:11px;margin-top:.35rem;min-height:1.2em"></div>
    <div style="font-size:10.5px;color:#484f58;margin-top:.1rem">Key stored in your browser only — never sent anywhere except directly to the AI provider.</div>
  </div>

  <!-- Messages -->
  <div class="chat-msgs" id="chatMsgs"></div>

  <!-- Input -->
  <div class="chat-input-area">
    <textarea id="chatTa" placeholder="Ask about targets, ligands, structures…" rows="1"
      onkeydown="chatKey(event)" oninput="autoH(this)"></textarea>
    <button class="chat-send-btn" id="chatSendBtn" onclick="chatSend()" title="Send (Enter)">
      <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
    </button>
  </div>
</div>

<style>
.prov-tab{background:none;border:1px solid #30363d;border-radius:5px;color:#8b949e;font-size:11px;padding:.22rem .65rem;cursor:pointer;transition:border-color .15s,color .15s,background .15s}
.prov-tab:hover{border-color:#58a6ff55;color:#e6edf3}
.prov-tab.active{background:#1f6feb22;border-color:#58a6ff;color:#58a6ff}
</style>

<script>
(function(){
var MODELS={
  anthropic:['claude-opus-4-6','claude-sonnet-4-6','claude-haiku-4-5-20251001'],
  openai:['gpt-4o','gpt-4o-mini'],
  groq:['llama-3.3-70b-versatile','llama-3.1-8b-instant','mixtral-8x7b-32768']
};
var _cid='c'+Math.random().toString(36).slice(2,7);
var _ctx=window.RECON_QUERY||null;
var _open=false,_busy=false,_minimized=false,_curDiv=null,_curTxt='',_cards={},_partial='',_xhr=null;
var _prov='anthropic',_model='claude-sonnet-4-6',_apiKey='';
// ── Boot ID check — wipe session state if server was restarted ────────
(function(){
  fetch('/api/boot_id').then(function(r){return r.json();}).then(function(d){
    var storedBoot=sessionStorage.getItem('tr_boot_id');
    if(storedBoot && storedBoot!==d.boot_id){
      // Server restarted — clear all session state
      sessionStorage.clear();
    }
    sessionStorage.setItem('tr_boot_id',d.boot_id);
    // Now init session ID
    window._sid=sessionStorage.getItem('tr_session_id')||'';
    if(!window._sid){
      window._sid='xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,function(c){
        var r=Math.random()*16|0,v=c=='x'?r:(r&0x3|0x8);return v.toString(16);
      });
      sessionStorage.setItem('tr_session_id',window._sid);
    }
  }).catch(function(){
    // Server unreachable — still init sid from storage
    window._sid=sessionStorage.getItem('tr_session_id')||'';
  });
})();

/* Built-in markdown renderer — handles headers, bold, italic, code, tables, lists */
function _inl(t){
  t=t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  t=t.replace(/\*\*\*(.+?)\*\*\*/g,'<strong><em>$1</em></strong>');
  t=t.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  t=t.replace(/\*(.+?)\*/g,'<em>$1</em>');
  t=t.replace(/`([^`\n]+)`/g,'<code>$1</code>');
  t=t.replace(/!\[([^\]]*)\]\(([^)]+)\)/g,'<a href="$2" target="_blank">$1</a>');
  t=t.replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank">$1</a>');
  return t;
}
function _md(text){
  if(typeof marked!=='undefined'){try{return marked.parse(text)}catch(e){}}
  if(!text)return '';
  var lines=text.split('\n'),out='',inTbl=false,inUl=false,inOl=false;
  function closeLists(){if(inUl){out+='</ul>';inUl=false;}if(inOl){out+='</ol>';inOl=false;}}
  function closeTable(){if(inTbl){out+='</tbody></table>';inTbl=false;}}
  for(var i=0;i<lines.length;i++){
    var l=lines[i];
    /* Table row */
    if(/^\|/.test(l)){
      var cells=l.split('|').slice(1,-1);
      if(!inTbl){
        /* peek at next line for separator */
        var sep=lines[i+1]||'';
        if(/^\|[\s\-|:]+\|/.test(sep)){
          closeLists();
          out+='<table class="md-tbl"><thead><tr>';
          cells.forEach(function(c){out+='<th>'+_inl(c.trim())+'</th>';});
          out+='</tr></thead><tbody>';
          inTbl=true;i++;continue;
        }
      }
      if(inTbl){
        if(/^[\|\s\-:]+$/.test(l))continue;
        out+='<tr>';cells.forEach(function(c){out+='<td>'+_inl(c.trim())+'</td>';});out+='</tr>';continue;
      }
    } else { closeTable(); }
    /* Heading */
    var hm=l.match(/^(#{1,4})\s+(.+)/);
    if(hm){closeLists();var hl=hm[1].length+1;out+='<h'+hl+'>'+_inl(hm[2])+'</h'+hl+'>';continue;}
    /* HR */
    if(/^---+$/.test(l.trim())){closeLists();out+='<hr>';continue;}
    /* Unordered list */
    var um=l.match(/^[\-\*]\s+(.*)/);
    if(um){closeTable();if(!inUl){if(inOl){out+='</ol>';inOl=false;}out+='<ul>';inUl=true;}out+='<li>'+_inl(um[1])+'</li>';continue;}
    /* Ordered list */
    var om=l.match(/^\d+\.\s+(.*)/);
    if(om){closeTable();if(!inOl){if(inUl){out+='</ul>';inUl=false;}out+='<ol>';inOl=true;}out+='<li>'+_inl(om[1])+'</li>';continue;}
    /* Close lists on blank/normal line */
    closeLists();
    if(!l.trim()){out+='<br>';continue;}
    out+='<p>'+_inl(l)+'</p>';
  }
  closeLists();closeTable();
  return out;
}

function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function $id(id){return document.getElementById(id);}
function msgs(){return $id('chatMsgs');}
function scroll(){var m=msgs();if(m)m.scrollTop=m.scrollHeight;}

// ── Settings ─────────────────────────────────────────────────────────────
function loadSettings(){
  try{
    var s=JSON.parse(localStorage.getItem('tr_agent_prefs')||'{}');
    _prov=s.provider||'anthropic';
    _model=s.model||'claude-sonnet-4-6';
    /* API key is never persisted — must be entered each page load */
  }catch(e){}
}
function saveSettings(){
  _apiKey=($id('chatApiKey').value||'').trim();
  var sel=$id('chatModelSel');
  if(sel)_model=sel.value;
  try{
    /* Provider + model persist across sessions; key is never stored */
    var s=JSON.parse(localStorage.getItem('tr_agent_prefs')||'{}');
    s.provider=_prov;s.model=_model;
    localStorage.setItem('tr_agent_prefs',JSON.stringify(s));
  }catch(e){}
  updateBadge();
}
function updateBadge(){
  var b=$id('chatModelBadge');if(b)b.textContent=_model;
}
function setKeyStatus(ok,msg){
  var bar=$id('keyStatusBar');if(!bar)return;
  if(ok===null){bar.innerHTML='<span style="color:#8b949e">'+msg+'</span>';return;}
  bar.innerHTML=ok
    ?'<span style="color:#3fb950">&#10003; '+msg+'</span>'
    :'<span style="color:#f85149">&#10007; '+msg+'</span>';
  updateBadge();
}
window.onKeyInput=function(){saveSettings();setKeyStatus(null,'');};
window.testKey=function(){
  var key=($id('chatApiKey').value||'').trim();
  if(!key){setKeyStatus(false,'Enter an API key first');return;}
  var btn=$id('testKeyBtn');
  if(btn){btn.disabled=true;btn.textContent='Testing…';}
  setKeyStatus(null,'Contacting '+_prov+'…');
  fetch('/agent/test_key',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({provider:_prov,model:_model,api_key:key})
  }).then(function(r){return r.json();}).then(function(d){
    if(d.ok){
      setKeyStatus(true,'Key accepted by '+_prov);
      _apiKey=key;saveSettings();
    } else {
      setKeyStatus(false,d.error||'Key rejected');
    }
  }).catch(function(e){
    setKeyStatus(false,'Request failed: '+e.message);
  }).finally(function(){
    if(btn){btn.disabled=false;btn.textContent='Test';}
  });
};
window.selProv=function(prov,btn){
  _prov=prov;
  document.querySelectorAll('.prov-tab').forEach(function(t){t.classList.remove('active');});
  if(btn)btn.classList.add('active');
  // Key is not persisted — clear field when switching provider
  _apiKey='';
  var ki=$id('chatApiKey');if(ki)ki.value='';
  // Update model dropdown
  var sel=$id('chatModelSel');
  if(sel){
    var ms=MODELS[prov]||[];
    sel.innerHTML=ms.map(function(m){return'<option value="'+m+'">'+m+'</option>';}).join('');
    // restore saved model if valid
    try{
      var saved=JSON.parse(localStorage.getItem('tr_agent_settings')||'{}');
      if(saved.provider===prov&&saved.model&&ms.indexOf(saved.model)>=0)sel.value=saved.model;
    }catch(e){}
    _model=sel.value;
  }
  saveSettings();
  updateBadge();updateKeyStatus();
};
window.toggleSettings=function(){
  var s=$id('chatSettings');
  if(!s)return;
  var shown=s.style.display!=='none';
  s.style.display=shown?'none':'block';
  if(!shown){
    loadSettings();
    // Sync UI
    document.querySelectorAll('.prov-tab').forEach(function(t){
      t.classList.toggle('active',t.dataset.prov===_prov);
    });
    var sel=$id('chatModelSel');
    if(sel){
      var ms=MODELS[_prov]||[];
      sel.innerHTML=ms.map(function(m){return'<option value="'+m+'">'+m+'</option>';}).join('');
      if(ms.indexOf(_model)>=0)sel.value=_model;
    }
    var ki=$id('chatApiKey');if(ki)ki.value=_apiKey;
    if(_apiKey) setKeyStatus(null,'Key entered — click Test to verify');
    else setKeyStatus(null,'Enter your API key');
  }
};
// Keep model in sync when select changes
document.addEventListener('DOMContentLoaded',function(){
  var sel=$id('chatModelSel');
  if(sel)sel.addEventListener('change',function(){_model=this.value;saveSettings();});
});

// ── State persistence across page navigations ────────────────────────────
function saveState(){
  try{
    var m=msgs();
    sessionStorage.setItem('tr_chat_html',m?m.innerHTML:'');
    sessionStorage.setItem('tr_chat_cid',_cid);
    sessionStorage.setItem('tr_chat_open',_open&&!_minimized?'1':'0');
    sessionStorage.setItem('tr_chat_ctx',_ctx||'');
  }catch(e){}
}
function restoreState(){
  try{
    var html=sessionStorage.getItem('tr_chat_html');
    var cid=sessionStorage.getItem('tr_chat_cid');
    var wasOpen=sessionStorage.getItem('tr_chat_open');
    if(html&&cid){
      var m=msgs();if(m)m.innerHTML=html;
      _cid=cid;
      /* Re-attach run-btn handlers (onclick already in HTML, no extra work) */
      if(wasOpen==='1'){
        _open=true;
        var p=$id('agentChatPanel'),b=$id('chatToggleBtn');
        if(p)p.classList.remove('chat-hidden');
        if(b)b.style.display='none';
      }
      return true;
    }
  }catch(e){}
  return false;
}
/* Global navigation helper — saves chat state before replacing page */
window.navTo=function(html){saveState();document.open();document.write(html);document.close();};

// ── Stop ─────────────────────────────────────────────────────────────────
window.chatStop=function(){
  if(_xhr){_xhr.abort();_xhr=null;}
  _busy=false;rmTyping();
  var sb=$id('chatSendBtn');if(sb)sb.disabled=false;
  var stb=$id('chatStopBtn');if(stb)stb.style.display='none';
  if(_curDiv&&_curTxt)_curDiv.innerHTML=_injectRunBtns(_md(_curTxt));
  _curDiv=null;scroll();saveState();
};

// ── Minimize ─────────────────────────────────────────────────────────────
var _savedW='430px',_savedH='590px';
window.chatMinimize=function(){
  var panel=$id('agentChatPanel');
  _minimized=!_minimized;
  if(_minimized){
    /* Save current dimensions before collapsing */
    _savedW=panel.style.width||panel.offsetWidth+'px';
    _savedH=panel.style.height||panel.offsetHeight+'px';
    /* Hide everything except the header */
    ['chatSettings','chatMsgs'].forEach(function(id){var e=$id(id);if(e)e.style.display='none';});
    var ia=panel.querySelector('.chat-input-area');if(ia)ia.style.display='none';
    var rz=panel.querySelector('#chatRzTop,#chatRzLeft,#chatRzCorner');
    panel.querySelectorAll('#chatRzTop,#chatRzLeft,#chatRzCorner').forEach(function(e){e.style.display='none';});
    panel.style.height='auto';
    panel.style.width='240px';
    panel.style.bottom='1.25rem';
    var btn=$id('chatMinBtn');if(btn)btn.innerHTML='&#9650;';
    var tb=$id('chatToggleBtn');if(tb)tb.style.display='none'; /* keep hidden */
  } else {
    /* Restore saved dimensions */
    panel.style.width=_savedW;
    panel.style.height=_savedH;
    ['chatSettings','chatMsgs'].forEach(function(id){
      var e=$id(id);
      /* only restore chatMsgs, keep settings hidden unless it was open */
      if(id==='chatMsgs'&&e)e.style.display='';
    });
    var ia=panel.querySelector('.chat-input-area');if(ia)ia.style.display='';
    panel.querySelectorAll('#chatRzTop,#chatRzLeft,#chatRzCorner').forEach(function(e){e.style.display='';});
    var btn=$id('chatMinBtn');if(btn)btn.innerHTML='&#8212;';
    $id('chatTa').focus();
  }
};

// ── Resize ───────────────────────────────────────────────────────────────
(function(){
  var panel=$id('agentChatPanel');
  if(!panel)return;
  var _rz=null; // {type:'top'|'left'|'corner', startX, startY, startW, startH}
  var RIGHT_GAP=20,BOTTOM_GAP=20,MIN_W=320,MIN_H=300,MAX_W=800;

  function startRz(type,e){
    var r=panel.getBoundingClientRect();
    _rz={type:type,sx:e.clientX,sy:e.clientY,sw:r.width,sh:r.height};
    document.body.style.userSelect='none';
    e.preventDefault();
  }
  var top=$id('chatRzTop'),left=$id('chatRzLeft'),corner=$id('chatRzCorner');
  if(top)   top.addEventListener('mousedown',function(e){startRz('top',e);});
  if(left)  left.addEventListener('mousedown',function(e){startRz('left',e);});
  if(corner)corner.addEventListener('mousedown',function(e){startRz('corner',e);});

  document.addEventListener('mousemove',function(e){
    if(!_rz)return;
    var dx=_rz.sx-e.clientX, dy=_rz.sy-e.clientY;
    if(_rz.type==='top'||_rz.type==='corner'){
      var nh=Math.max(MIN_H,_rz.sh+dy);
      var maxH=window.innerHeight-BOTTOM_GAP-20;
      panel.style.height=Math.min(nh,maxH)+'px';
    }
    if(_rz.type==='left'||_rz.type==='corner'){
      var nw=Math.max(MIN_W,_rz.sw+dx);
      panel.style.width=Math.min(nw,MAX_W)+'px';
    }
  });
  document.addEventListener('mouseup',function(){
    if(_rz){_rz=null;document.body.style.userSelect='';}
  });
})();

// ── Chat ──────────────────────────────────────────────────────────────────
window.openReport=function(url){
  var o=$id('reportOverlay'),f=$id('reportFrame');
  if(!o||!f)return;
  f.src=url;
  o.style.display='block';
};
window.closeReport=function(){
  var o=$id('reportOverlay'),f=$id('reportFrame');
  if(o)o.style.display='none';
  if(f)f.src='';
};
window.toggleChat=function(){
  var p=$id('agentChatPanel'),b=$id('chatToggleBtn');
  /* If panel is minimized, restore it */
  if(_minimized){window.chatMinimize();return;}
  _open=!_open;
  if(_open){
    loadSettings();
    p.classList.remove('chat-hidden');
    if(b)b.style.display='none';
    $id('chatTa').focus();
    if(!msgs().children.length)showWelcome();
  }else{
    p.classList.add('chat-hidden');
    if(b)b.style.display='';
    saveState();
  }
};
window.newChat=function(){
  _cid='c'+Math.random().toString(36).slice(2,7);
  msgs().innerHTML='';showWelcome();
  saveState();
};
function showWelcome(){
  var sug=_ctx?[
    'What are the top 10 most potent ligands for '+_ctx+'?',
    'Show PDB structures with bound ligands for '+_ctx,
    'What diseases is '+_ctx+' associated with?',
    'Compare '+_ctx+' druggability to EGFR'
  ]:[
    'Search EGFR and show the best IC50 compounds',
    'Compare BRAF vs KRAS druggability side by side',
    'What approved drugs target CDK2?',
    'Find kinase inhibitors with pChEMBL above 9'
  ];
  msgs().innerHTML='<div class="chat-welcome">'
    +'<div class="chat-welcome-icon">&#129516;</div>'
    +'<strong>AI Drug Discovery Agent</strong>'
    +'<div style="font-size:12px;margin-top:.2rem">UniProt &bull; PDB &bull; ChEMBL &bull; BindingDB &bull; STRING-DB</div>'
    +'<div class="chat-welcome-suggestions">'
    +sug.map(function(s){return'<button class="chat-suggestion" onclick="chatUseSug(this)">'+esc(s)+'</button>';}).join('')
    +'</div></div>';
}
window.chatUseSug=function(btn){$id('chatTa').value=btn.textContent;chatSend();};
window.chatKey=function(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();chatSend();}};
window.autoH=function(ta){ta.style.height='auto';ta.style.height=Math.min(ta.scrollHeight,120)+'px';};
window.chatSend=function(){
  if(_busy)return;
  var ta=$id('chatTa'),msg=(ta.value||'').trim();
  if(!msg)return;
  ta.value='';ta.style.height='auto';
  var w=msgs().querySelector('.chat-welcome');if(w)w.remove();
  addUser(msg);stream(msg);
};
function addUser(txt){
  var d=document.createElement('div');d.className='chat-bubble-user';d.textContent=txt;
  msgs().appendChild(d);scroll();saveState();
}
function addTyping(){
  var d=document.createElement('div');d.className='typing-dots';d.id='chatTyping';
  d.innerHTML='<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
  msgs().appendChild(d);scroll();
}
function rmTyping(){var t=$id('chatTyping');if(t)t.remove();}
function addToolCard(tid,name,disp){
  var d=document.createElement('div');
  d.className='tool-card tc-running';d.id='tc'+tid;
  d.innerHTML='<div class="tc-spinner"></div><span class="tc-txt">'+esc(disp)+'...</span>';
  msgs().appendChild(d);_cards[tid]=d;scroll();
}
function doneToolCard(tid,elapsed,err,links){
  var d=_cards[tid];if(!d)return;
  d.className='tool-card '+(err?'tc-error':'tc-done');
  var sp=d.querySelector('.tc-txt');
  var label=sp?sp.textContent.replace(/\.\.\.$/,''):'';
  var et=elapsed?' ('+elapsed+'s)':'';
  d.innerHTML='<span class="tc-icon">'+(err?'&#10007;':'&#10003;')+'</span><span>'+esc(label)+et+'</span>';
  if(links&&links.length){
    var ld=document.createElement('div');ld.className='chat-action-links';
    links.forEach(function(lk){
      var a=document.createElement('a');a.className='chat-action-link';a.textContent=lk.label;
      if(lk.report){a.href='#';a.onclick=function(e){e.preventDefault();openReport(lk.href);};}
      else if(lk.is_image){a.href=lk.href;a.target='_blank';}
      else{(function(href,label){a.href='#';a.onclick=function(e){e.preventDefault();var tmp=document.createElement('a');tmp.href=href;tmp.download=label;document.body.appendChild(tmp);tmp.click();document.body.removeChild(tmp);};})(lk.href,lk.label);}
      ld.appendChild(a);
    });
    msgs().appendChild(ld);
  }
  scroll();
}
function agentDiv(){
  if(!_curDiv){rmTyping();var d=document.createElement('div');d.className='chat-bubble-agent';msgs().appendChild(d);_curDiv=d;}
  return _curDiv;
}
function stream(msg){
  _busy=true;_curDiv=null;_curTxt='';_cards={};_partial='';
  var sb=$id('chatSendBtn');if(sb)sb.disabled=true;
  var stb=$id('chatStopBtn');if(stb)stb.style.display='';
  addTyping();
  _xhr=new XMLHttpRequest();
  _xhr.open('POST','/agent/chat/stream',true);
  _xhr.setRequestHeader('Content-Type','application/json');
  var lastPos=0;
  _xhr.onreadystatechange=function(){
    if(_xhr.readyState>=3){var ch=_xhr.responseText.slice(lastPos);lastPos=_xhr.responseText.length;if(ch)proc(ch);}
    if(_xhr.readyState===4){
      _busy=false;_xhr=null;rmTyping();
      if(sb)sb.disabled=false;
      if(stb)stb.style.display='none';
      _curDiv=null;scroll();saveState();
    }
  };
  _xhr.send(JSON.stringify({message:msg,conv_id:_cid,context_query:_ctx,provider:_prov,model:_model,api_key:_apiKey,session_id:window._sid||''}));
}
function proc(chunk){
  var txt=_partial+chunk;_partial='';
  var lines=txt.split('\n');_partial=lines.pop();
  lines.forEach(function(line){
    if(!line.startsWith('data: '))return;
    var js=line.slice(6).trim();if(!js)return;
    try{handle(JSON.parse(js));}catch(e){}
  });
}
/* Convert tool_name("arg") / tool_name(["a","b"]) in code spans to run buttons */
function _injectRunBtns(html){
  var TOOLS=['search_target','get_top_ligands','get_pdb_structures','compare_targets',
             'get_protein_info','get_protein_interactions','search_compound','filter_bioactivities'];
  var pat=new RegExp('(<code>)((?:'+TOOLS.join('|')+')\\([^)]{1,120}\\))(</code>)','g');
  return html.replace(pat,function(_,o,call,c){
    var safe=call.replace(/"/g,'&quot;');
    var query=call.replace(/^[^(]+\(["'\[]?/,'').replace(/["'\]]\).*$/,'');
    /* build natural language prompt from tool call */
    var prompt=call;
    return o+safe+c+'<button class="chat-run-btn" onclick="chatRunTool(\''+safe.replace(/'/g,"\\'")+'\')" title="Run this">&#9654; Run</button>';
  });
}
window.chatRunTool=function(call){
  /* turn tool_name("X") into a natural language message */
  var m=call.match(/^(\w+)\((.*)\)$/);
  if(!m)return;
  var tool=m[1],args=m[2];
  var q=(args.match(/"([^"]+)"/)||args.match(/'([^']+)'/)||['',''])[1]||args.replace(/['"[\]]/g,'').trim();
  var prompts={
    'search_target':'Search and analyse the target: '+q,
    'get_top_ligands':'Show the top ligands for: '+q,
    'get_pdb_structures':'List PDB structures for: '+q,
    'compare_targets':'Compare these targets: '+q,
    'get_protein_info':'Get detailed protein info for: '+q,
    'get_protein_interactions':'Show protein interactions for: '+q,
    'search_compound':'Search for compound: '+q,
    'filter_bioactivities':'Filter bioactivities for: '+q
  };
  var msg=prompts[tool]||call;
  var ta=$id('chatTa');if(ta){ta.value=msg;}
  chatSend();
};

function handle(ev){
  if(ev.type==='text_delta'){rmTyping();_curTxt+=ev.delta;agentDiv().innerHTML=_injectRunBtns(_md(_curTxt));scroll();}
  else if(ev.type==='tool_start'){rmTyping();addToolCard(ev.tool_id,ev.tool_name,ev.display_message);}
  else if(ev.type==='tool_result'){doneToolCard(ev.tool_id,ev.elapsed,!!(ev.content&&ev.content.error),ev.action_links||[]);}
  else if(ev.type==='done'){rmTyping();if(_curDiv&&_curTxt)_curDiv.innerHTML=_injectRunBtns(_md(_curTxt));_curDiv=null;scroll();}
  else if(ev.type==='error'){
    rmTyping();var d=document.createElement('div');d.className='chat-bubble-agent';
    d.style.color='#f85149';d.textContent='Error: '+(ev.message||'Unknown');msgs().appendChild(d);scroll();
  }
}

try{sessionStorage.removeItem('tr_agent_keys');}catch(e){}
loadSettings();
restoreState();
})();
</script>
"""

# ── Jinja2 helpers ───────────────────────────────────────────────────────────
def _pchembl_class(val):
    if val is None: return "pchembl-na"
    if val >= 9:    return "pchembl-hi"
    if val >= 7:    return "pchembl-md"
    return "pchembl-lo"

app.jinja_env.globals["pchembl_class"] = _pchembl_class


# ── Landing page ─────────────────────────────────────────────────────────────
INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TargetRecon</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>

<nav class="topnav">
  <div class="topnav-inner">
    <a class="topnav-brand" href="/">Target<span>Recon</span></a>
  </div>
</nav>

<div class="app-layout">

<!-- ── Sidebar ── -->
<aside class="sidebar">
  <div class="sb-section">
    <span class="sb-label">Search</span>
    <form action="/recon" method="get" id="sbForm">
      <div style="display:flex;justify-content:center;gap:1rem;margin-bottom:.4rem">
        <label class="db-check"><input type="checkbox" id="cbChembl" checked onchange="document.getElementById('hUseChembl').value=this.checked?'1':'0'"> ChEMBL</label>
        <label class="db-check"><input type="checkbox" id="cbBdb" checked onchange="document.getElementById('hUseBdb').value=this.checked?'1':'0'"> BindingDB</label>
      </div>
      <input class="sb-input" name="q" id="sbQ" placeholder="EGFR · P00533 · BRAF"
             autofocus autocomplete="off" spellcheck="false">
      <input type="hidden" name="max_res" id="hMaxRes" value="4.0">
      <input type="hidden" name="min_pc"  id="hMinPc"  value="0">
      <input type="hidden" name="max_bio" id="hMaxBio" value="1000">
      <input type="hidden" name="use_chembl" id="hUseChembl" value="1">
      <input type="hidden" name="use_bindingdb" id="hUseBdb" value="1">
      <button type="submit" class="sb-btn sb-btn-primary" id="searchBtn" onclick="showSearchSpinner(this)">Search</button>
    </form>
    <a href="/sketcher" class="sb-btn sb-btn-outline"
       style="display:flex;align-items:center;justify-content:center;gap:.4rem;text-decoration:none;margin-top:.5rem">
      <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
      Draw structure
    </a>
  </div>

  <hr class="sb-divider">

  <div class="sb-section">
    <span class="sb-label">Filters</span>

    <span class="sb-sublabel">Max PDB resolution (Å)</span>
    <input type="range" class="sb-range" id="rMaxRes" min="1" max="6" step="0.5" value="4.0"
           oninput="upd('hMaxRes','vMaxRes',this.value)">
    <div class="sb-range-row">
      <span>1.0</span><span class="sb-range-val" id="vMaxRes">4.0 Å</span><span>6.0</span>
    </div>

    <span class="sb-sublabel">Min pChEMBL</span>
    <input type="range" class="sb-range" id="rMinPc" min="0" max="12" step="0.5" value="0"
           oninput="upd('hMinPc','vMinPc',this.value)">
    <div class="sb-range-row">
      <span>0</span><span class="sb-range-val" id="vMinPc">0</span><span>12</span>
    </div>

    <span class="sb-sublabel">Max bioactivities <span style="color:var(--muted);font-weight:400">per DB</span></span>
    <input type="range" class="sb-range" id="rMaxBio" min="100" max="5000" step="100" value="1000"
           oninput="updBio('hMaxBio','vMaxBio',this.value)">
    <div class="sb-range-row">
      <span>100</span><span class="sb-range-val" id="vMaxBio">1000</span><span>All</span>
    </div>
  </div>

  <div class="sb-version">TargetRecon v{{ version }}</div>
</aside>

<!-- ── Main content ── -->
<div class="main-content" style="position:relative;overflow:hidden">
  <canvas id="bgCanvas" style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0"></canvas>
  <div class="landing-inner" style="position:relative;z-index:1">
    <div class="landing-logo">Target<span>Recon</span></div>
    <p class="landing-sub">
      Drug target intelligence in one search.<br>
      Aggregates UniProt · PDB · AlphaFold · ChEMBL · BindingDB.
    </p>
    <div class="examples">
      {% for ex in ["EGFR","BRAF","CDK2","ABL1","JAK2","TP53"] %}
      <button class="example-btn"
        onclick="document.getElementById('sbQ').value='{{ ex }}';showSearchOverlay('{{ ex }}');document.getElementById('sbForm').submit()">{{ ex }}</button>
      {% endfor %}
    </div>
    <div class="sources-line">
      Enter a gene name, UniProt accession, or ChEMBL target ID in the search box on the left.
    </div>
  </div>
</div>

</div><!-- end .app-layout -->

<script>
function upd(hiddenId, displayId, val) {
  document.getElementById(hiddenId).value = val;
  var el = document.getElementById(displayId);
  if (el) el.textContent = hiddenId.includes('Res') ? val + ' Å' : val;
}
function updBio(hiddenId, displayId, val) {
  var v = parseInt(val);
  document.getElementById(hiddenId).value = v >= 5000 ? 10000 : v;
  var el = document.getElementById(displayId);
  if (el) el.textContent = v >= 5000 ? 'All' : val;
}

function _showSpinner() {
  var btn = document.querySelector('#sbForm button[type=submit]');
  if (!btn) return;
  btn.disabled = true;
  btn.innerHTML = '<span class="spin" style="width:13px;height:13px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:5px"></span>Searching';
}

function _getParams(q) {
  return new URLSearchParams({
    q: q,
    max_res: document.getElementById('hMaxRes').value,
    min_pc:  document.getElementById('hMinPc').value,
    max_bio: document.getElementById('hMaxBio').value,
    use_chembl:    document.getElementById('hUseChembl').value,
    use_bindingdb: document.getElementById('hUseBdb').value,
  });
}

function _doSearch(q) {
  if (!q) return;
  _showSpinner();
  var params = _getParams(q);
  fetch('/recon/run?' + params.toString())
    .then(function(r){ return r.text(); })
    .then(function(html){ if(window.navTo)window.navTo(html);else{document.open();document.write(html);document.close();} })
    .catch(function(){ window.location.href = '/recon/run?' + params.toString(); });
}

document.addEventListener('DOMContentLoaded', function() {
  document.getElementById('sbForm').addEventListener('submit', function(e) {
    e.preventDefault();
    var q = (document.getElementById('sbQ').value || '').trim();
    _doSearch(q);
  });
});

/* called by example buttons */
function showSearchOverlay(q) { _doSearch(q); }
function showSearchSpinner() {}

/* ── Molecular network backdrop ── */
(function(){
  var canvas = document.getElementById('bgCanvas');
  if (!canvas) return;
  var ctx = canvas.getContext('2d');
  var W, H, nodes;
  var LINK_DIST = 160, NUM = 70;

  var COLORS = ['#58a6ff','#3fb950','#d29922','#bc8cff','#ff7b72','#79c0ff','#56d364','#ffa657'];

  function Node() {
    this.x  = Math.random() * W;
    this.y  = Math.random() * H;
    this.vx = (Math.random() - 0.5) * 0.35;
    this.vy = (Math.random() - 0.5) * 0.35;
    this.r  = Math.random() < 0.15 ? 6 + Math.random()*5 : 3 + Math.random()*2.5;
    this.color = COLORS[Math.floor(Math.random()*COLORS.length)];
    this.pulse = Math.random() * Math.PI * 2;
    this.hub = this.r > 7;
  }

  function hex2rgb(h) {
    return parseInt(h.slice(1,3),16)+','+parseInt(h.slice(3,5),16)+','+parseInt(h.slice(5,7),16);
  }

  function resize() {
    var rect = canvas.parentElement.getBoundingClientRect();
    W = canvas.width  = rect.width  || window.innerWidth;
    H = canvas.height = rect.height || window.innerHeight;
    nodes = Array.from({length: NUM}, function(){ return new Node(); });
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);

    /* links */
    for (var i = 0; i < nodes.length; i++) {
      for (var j = i+1; j < nodes.length; j++) {
        var a = nodes[i], b = nodes[j];
        var dx = a.x - b.x, dy = a.y - b.y;
        var d = Math.sqrt(dx*dx + dy*dy);
        if (d < LINK_DIST) {
          var alpha = (1 - d/LINK_DIST) * 0.4;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.strokeStyle = 'rgba(88,166,255,' + alpha + ')';
          ctx.lineWidth = 0.9;
          ctx.stroke();
        }
      }
    }

    /* nodes */
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      n.pulse += 0.018;
      var pr = n.r + (n.hub ? Math.sin(n.pulse)*2.5 : 0);
      var rgb = hex2rgb(n.color);

      if (n.hub) {
        var grd = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, pr*5);
        grd.addColorStop(0, 'rgba('+rgb+',0.15)');
        grd.addColorStop(1, 'rgba('+rgb+',0)');
        ctx.beginPath();
        ctx.arc(n.x, n.y, pr*4, 0, Math.PI*2);
        ctx.fillStyle = grd;
        ctx.fill();
      }

      /* glow ring */
      ctx.shadowColor = n.color;
      ctx.shadowBlur = n.hub ? 10 : 4;
      ctx.beginPath();
      ctx.arc(n.x, n.y, pr, 0, Math.PI*2);
      ctx.fillStyle = n.hub ? n.color : 'rgba('+rgb+',0.85)';
      ctx.fill();
      ctx.shadowBlur = 0;

      n.x += n.vx; n.y += n.vy;
      if (n.x < -20) n.x = W+20;
      if (n.x > W+20) n.x = -20;
      if (n.y < -20) n.y = H+20;
      if (n.y > H+20) n.y = -20;
    }

    requestAnimationFrame(draw);
  }

  resize();
  window.addEventListener('resize', resize);
  draw();
})();
</script>
{{ chat_panel | safe }}
</body>
</html>
"""

LOADING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="0;url=/recon/run?q={{ q }}&max_res={{ max_res }}&min_pc={{ min_pc }}&max_bio={{ max_bio }}&use_chembl={{ use_chembl }}&use_bindingdb={{ use_bindingdb }}">
<script>(function(){var sid='';try{sid=sessionStorage.getItem('tr_session_id')||'';}catch(e){}var url='/recon/run?q={{ q }}&max_res={{ max_res }}&min_pc={{ min_pc }}&max_bio={{ max_bio }}&use_chembl={{ use_chembl }}&use_bindingdb={{ use_bindingdb }}'+(sid?'&sid='+encodeURIComponent(sid):'');window.location.replace(url);})();</script>
<title>Searching {{ q }} — TargetRecon</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;background:#0d1117;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
body{display:flex;align-items:center;justify-content:center;flex-direction:column;gap:2rem}

/* Logo */
.logo{font-size:1.6rem;font-weight:700;color:#e6edf3;letter-spacing:-.02em}
.logo span{color:#58a6ff}

/* Spoke spinner */
.spoke-ring{position:relative;width:72px;height:72px}
.spoke-ring .spoke{
  position:absolute;left:50%;top:50%;
  width:3px;height:18px;margin-left:-1.5px;
  border-radius:2px;background:#58a6ff;
  transform-origin:50% 36px;
  animation:spoke-fade 1s linear infinite;
}
.spoke-ring .spoke:nth-child(1) {transform:rotate(0deg);  animation-delay:-0.875s}
.spoke-ring .spoke:nth-child(2) {transform:rotate(45deg); animation-delay:-0.75s}
.spoke-ring .spoke:nth-child(3) {transform:rotate(90deg); animation-delay:-0.625s}
.spoke-ring .spoke:nth-child(4) {transform:rotate(135deg);animation-delay:-0.5s}
.spoke-ring .spoke:nth-child(5) {transform:rotate(180deg);animation-delay:-0.375s}
.spoke-ring .spoke:nth-child(6) {transform:rotate(225deg);animation-delay:-0.25s}
.spoke-ring .spoke:nth-child(7) {transform:rotate(270deg);animation-delay:-0.125s}
.spoke-ring .spoke:nth-child(8) {transform:rotate(315deg);animation-delay:0s}
@keyframes spoke-fade{0%{opacity:1}100%{opacity:.1}}

/* Text */
.search-label{font-size:1.1rem;font-weight:600;color:#e6edf3;letter-spacing:.01em}
.search-query{font-size:.9rem;color:#58a6ff;font-family:'SF Mono',monospace}
.search-sources{font-size:.75rem;color:#484f58;margin-top:-.5rem;letter-spacing:.03em}
</style>
</head>
<body>
  <div class="logo">Target<span>Recon</span></div>
  <div class="spoke-ring">
    <div class="spoke"></div><div class="spoke"></div><div class="spoke"></div><div class="spoke"></div>
    <div class="spoke"></div><div class="spoke"></div><div class="spoke"></div><div class="spoke"></div>
  </div>
  <div style="text-align:center;display:flex;flex-direction:column;gap:.4rem;align-items:center">
    <div class="search-label">Searching</div>
    <div class="search-query">{{ q }}</div>
  </div>
  <div class="search-sources">UniProt &nbsp;·&nbsp; PDB &nbsp;·&nbsp; AlphaFold &nbsp;·&nbsp; ChEMBL &nbsp;·&nbsp; BindingDB</div>
</body>
</html>
"""

# ── Compound disambiguation page ─────────────────────────────────────────────
DISAMBIG_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ compound_id }} — Select target — TargetRecon</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<nav class="topnav">
  <div class="topnav-inner">
    <a class="topnav-brand" href="/">Target<span>Recon</span></a>
  </div>
</nav>

<div style="max-width:820px;margin:3rem auto;padding:0 1.5rem">

  <div style="margin-bottom:1.5rem">
    <div style="font-size:22px;font-weight:700;color:#e6edf3;margin-bottom:.4rem">
      {{ compound_id }} is a <span style="color:#d29922">compound</span>, not a target
    </div>
    <div style="font-size:13.5px;color:#b1bac4;line-height:1.7">
      This molecule has been tested against {{ targets|length }} protein target{{ 's' if targets|length != 1 else '' }}.
      Select the target you want to analyse:
    </div>
  </div>

  <table class="data-table" style="width:100%">
    <thead><tr>
      <th>Gene</th>
      <th>Target name</th>
      <th>UniProt</th>
      <th>Organism</th>
      <th class="r">Best pChEMBL</th>
      <th class="r">Assays</th>
      <th></th>
    </tr></thead>
    <tbody>
    {% for t in targets %}
    <tr>
      <td style="font-weight:700;color:#e6edf3;font-size:13px">{{ t.gene_name or "—" }}</td>
      <td style="font-size:12.5px;color:#b1bac4;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
        {{ t.target_name }}
      </td>
      <td>
        {% if t.uniprot_id %}
        <a href="https://www.uniprot.org/uniprot/{{ t.uniprot_id }}" target="_blank"
           class="mono" style="font-size:11.5px;color:#58a6ff">{{ t.uniprot_id }}</a>
        {% else %}<span style="color:#484f58">—</span>{% endif %}
      </td>
      <td style="font-size:11.5px;color:#b1bac4">{{ t.organism[:22] }}{% if t.organism|length > 22 %}…{% endif %}</td>
      <td class="r mono" style="font-size:12px;color:{% if t.best_pchembl and t.best_pchembl >= 9 %}#3fb950{% elif t.best_pchembl and t.best_pchembl >= 7 %}#d29922{% else %}#b1bac4{% endif %}">
        {% if t.best_pchembl %}{{ "%.2f"|format(t.best_pchembl) }}{% else %}—{% endif %}
      </td>
      <td class="r" style="font-size:12px;color:#b1bac4">{{ t.num_activities }}</td>
      <td style="text-align:right">
        {% if t.gene_name or t.uniprot_id %}
        <button class="btn btn-primary" style="font-size:12px;padding:.3rem .8rem"
          onclick="analyseTarget('{{ t.gene_name or t.uniprot_id }}','{{ max_res }}','{{ min_pc }}','{{ max_bio }}',this)">
          Analyse →
        </button>
        {% else %}
        <button class="btn btn-default" style="font-size:12px;padding:.3rem .8rem"
          onclick="analyseTarget('{{ t.target_chembl_id }}','{{ max_res }}','{{ min_pc }}','{{ max_bio }}',this)">
          Analyse →
        </button>
        {% endif %}
      </td>
    </tr>
    {% endfor %}
    </tbody>
  </table>

  <div style="margin-top:1rem;font-size:11.5px;color:#484f58">
    Data from <a href="https://www.ebi.ac.uk/chembl" target="_blank" style="color:#58a6ff">ChEMBL</a> · Sorted by best pChEMBL (most potent first)
  </div>

  <a href="/" class="btn btn-default" style="margin-top:1.5rem;display:inline-block">← Back to search</a>
</div>
<script>
function analyseTarget(q, maxRes, minPc, maxBio, btn) {
  btn.disabled = true;
  var orig = btn.textContent;
  btn.textContent = '⏳ Loading…';
  var sid = window._sid || (sessionStorage ? sessionStorage.getItem('tr_session_id') : '') || '';
  var url = '/recon/run?q=' + encodeURIComponent(q) + '&max_res=' + encodeURIComponent(maxRes) + '&min_pc=' + encodeURIComponent(minPc) + '&max_bio=' + encodeURIComponent(maxBio) + (sid ? '&sid=' + encodeURIComponent(sid) : '');
  fetch(url)
    .then(function(r){ return r.text(); })
    .then(function(html){
      if(window.navTo){ window.navTo(html); }
      else { document.open(); document.write(html); document.close(); }
    })
    .catch(function(e){
      btn.disabled = false;
      btn.textContent = orig;
      alert('Failed: ' + e.message);
    });
}
</script>
</body>
</html>
"""

# ── Main report template ─────────────────────────────────────────────────────
REPORT_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ gene }} — TargetRecon</title>
<link rel="stylesheet" href="/static/style.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js" defer></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/3Dmol/2.1.0/3Dmol-min.js" defer></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.28.1/cytoscape.min.js" defer></script>
<script src="https://unpkg.com/smiles-drawer@1.0.10/dist/smiles-drawer.min.js"></script>
</head>
<body>

<!-- SMILES 2D tooltip -->
<div id="smilesPopup" style="
  display:none; position:fixed; z-index:9999;
  background:#161b22; border:1px solid #30363d; border-radius:8px;
  padding:8px; box-shadow:0 8px 24px rgba(0,0,0,.6); pointer-events:none;
  width:238px;">
  <canvas id="smilesCanvas" width="220" height="180"></canvas>
  <div id="smilesLabel" style="font-size:10px;color:#768390;text-align:center;margin-top:4px;
    max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></div>
</div>

<!-- ── Top nav ── -->
<nav class="topnav">
  <div class="topnav-inner">
    <a class="topnav-brand" href="/">Target<span>Recon</span></a>
    <div class="topnav-search">
      <form action="/recon" method="get" id="navForm">
        <input name="q" placeholder="Search another target…" value="{{ query }}" autocomplete="off" id="navQ">
        <button type="submit" class="btn btn-primary" style="padding:.4rem .9rem;font-size:12.5px">Go</button>
      </form>
    </div>
    <div class="topnav-actions">
      <a href="/export/json?q={{ query }}" class="btn btn-default">⬇ JSON</a>
      <a href="/export/html?q={{ query }}" class="btn btn-default">⬇ HTML</a>
      {% if has_sdf %}<a href="/export/sdf?q={{ query }}" class="btn btn-default">⬇ SDF</a>{% endif %}
    </div>
  </div>
</nav>

<!-- ── App layout ── -->
<div class="app-layout">

<!-- ── Sidebar ── -->
<aside class="sidebar">

  <!-- New search -->
  <div class="sb-section">
    <span class="sb-label">Search</span>
    <form action="/recon" method="get" id="sbForm">
      <div style="display:flex;justify-content:center;gap:1rem;margin-bottom:.4rem">
        <label class="db-check"><input type="checkbox" id="cbChembl" {% if use_chembl %}checked{% endif %} onchange="document.getElementById('hUseChembl').value=this.checked?'1':'0'"> ChEMBL</label>
        <label class="db-check"><input type="checkbox" id="cbBdb" {% if use_bindingdb %}checked{% endif %} onchange="document.getElementById('hUseBdb').value=this.checked?'1':'0'"> BindingDB</label>
      </div>
      <input class="sb-input" name="q" id="sbQ" placeholder="EGFR · P00533 · BRAF"
             value="{{ query }}" autocomplete="off" spellcheck="false">
      <!-- Filters hidden in form -->
      <input type="hidden" name="max_res" id="hMaxRes" value="{{ max_res }}">
      <input type="hidden" name="min_pc"  id="hMinPc"  value="{{ min_pc }}">
      <input type="hidden" name="max_bio" id="hMaxBio" value="{{ max_bio }}">
      <input type="hidden" name="use_chembl" id="hUseChembl" value="{{ '1' if use_chembl else '0' }}">
      <input type="hidden" name="use_bindingdb" id="hUseBdb" value="{{ '1' if use_bindingdb else '0' }}">
      <button type="submit" class="sb-btn sb-btn-primary" onclick="showSearchSpinner(this)">Search</button>
    </form>
    <a href="/sketcher" class="sb-btn sb-btn-outline"
       style="display:flex;align-items:center;justify-content:center;gap:.4rem;text-decoration:none;margin-top:.5rem">
      <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
      Draw structure
    </a>
  </div>

  <hr class="sb-divider">

  <!-- Filters -->
  <div class="sb-section">
    <span class="sb-label">Filters</span>

    <span class="sb-label" style="text-transform:none;letter-spacing:0;font-size:11.5px;color:var(--muted)">
      Max PDB resolution (Å)
    </span>
    <input type="range" class="sb-range" id="rMaxRes" min="1" max="6" step="0.5" value="{{ max_res }}"
           oninput="upd('hMaxRes','vMaxRes',this.value)">
    <div class="sb-range-row">
      <span>1.0</span><span class="sb-range-val" id="vMaxRes">{{ max_res }} Å</span><span>6.0</span>
    </div>

    <span class="sb-label" style="text-transform:none;letter-spacing:0;font-size:11.5px;color:var(--muted)">
      Min pChEMBL
    </span>
    <input type="range" class="sb-range" id="rMinPc" min="0" max="12" step="0.5" value="{{ min_pc }}"
           oninput="upd('hMinPc','vMinPc',this.value)">
    <div class="sb-range-row">
      <span>0</span><span class="sb-range-val" id="vMinPc">{{ min_pc }}</span><span>12</span>
    </div>

    <span class="sb-label" style="text-transform:none;letter-spacing:0;font-size:11.5px;color:var(--muted)">
      Max bioactivities <span style="font-weight:400">per DB</span>
    </span>
    <input type="range" class="sb-range" id="rMaxBio" min="100" max="5000" step="100" value="{{ max_bio }}"
           oninput="updBio('hMaxBio','vMaxBio',this.value)">
    <div class="sb-range-row">
      <span>100</span><span class="sb-range-val" id="vMaxBio">{{ max_bio if max_bio|int < 5000 else 'All' }}</span><span>All</span>
    </div>
  </div>

  <hr class="sb-divider">

  <!-- Target metadata -->
  <div class="sb-section">
    <span class="sb-label">Target</span>
    <div class="sb-meta-row"><span>UniProt</span>
      <strong><a href="https://www.uniprot.org/uniprot/{{ u.uniprot_id }}" target="_blank"
         style="color:var(--blue);font-family:var(--mono);font-size:11.5px">{{ u.uniprot_id }}</a></strong></div>
    {% if u.chembl_id %}
    <div class="sb-meta-row"><span>ChEMBL</span>
      <strong><a href="https://www.ebi.ac.uk/chembl/target_report_card/{{ u.chembl_id }}" target="_blank"
         style="color:var(--blue);font-family:var(--mono);font-size:11.5px">{{ u.chembl_id }}</a></strong></div>
    {% endif %}
    <div class="sb-meta-row"><span>Length</span>
      <strong>{{ "{:,}".format(u.sequence_length) }} aa</strong></div>
    <div class="sb-meta-row"><span>Organism</span>
      <strong style="font-size:11px">{{ u.organism }}</strong></div>
  </div>

  <hr class="sb-divider">

  <!-- Export -->
  <div class="sb-section">
    <span class="sb-label">Export</span>
    <a href="/export/json?q={{ query }}" class="sb-btn sb-btn-outline" style="text-align:center;display:block;text-decoration:none">⬇ JSON data</a>
    <a href="/export/html?q={{ query }}" class="sb-btn sb-btn-outline" style="text-align:center;display:block;text-decoration:none">⬇ HTML report</a>
    {% if has_sdf %}
    <a href="/export/sdf?q={{ query }}"  class="sb-btn sb-btn-outline" style="text-align:center;display:block;text-decoration:none">⬇ SDF ligands</a>
    {% endif %}
  </div>

  <div class="sb-version">TargetRecon v{{ version }}</div>
</aside>

<!-- ── Main content ── -->
<div class="main-content">
<div>

  <!-- ── Target header ── -->
  <div class="target-header">
    <div class="target-name">{{ gene }}</div>
    <div class="target-protein">{{ u.protein_name }}</div>
    <div class="meta-row">
      <span>UniProt
        <a href="https://www.uniprot.org/uniprot/{{ u.uniprot_id }}" target="_blank">{{ u.uniprot_id }}</a>
      </span>
      {% if u.chembl_id %}
      <span>ChEMBL
        <a href="https://www.ebi.ac.uk/chembl/target_report_card/{{ u.chembl_id }}" target="_blank">{{ u.chembl_id }}</a>
      </span>
      {% endif %}
      <span>Organism <strong style="color:#e6edf3;font-weight:500">{{ u.organism }}</strong></span>
      <span>{{ u.sequence_length | int | format_int }} aa</span>
    </div>
  </div>

  <!-- ── Stats ── -->
  <div class="stats-grid">
    <div class="stat">
      <div class="stat-val" style="color:#58a6ff">{{ report.num_pdb_structures }}</div>
      <div class="stat-key">PDB Structures</div>
    </div>
    <div class="stat">
      <div class="stat-val" style="color:#3fb950">{{ report.num_bioactivities | format_int }}</div>
      <div class="stat-key">Bioactivities</div>
    </div>
    <div class="stat">
      <div class="stat-val" style="color:#d29922">{{ report.num_unique_ligands | format_int }}</div>
      <div class="stat-key">Unique Ligands</div>
    </div>
    <div class="stat">
      <div class="stat-val" style="color:#bc8cff">
        {% if report.best_ligand and report.best_ligand.best_pchembl %}
          {{ "%.2f"|format(report.best_ligand.best_pchembl) }}
        {% else %}—{% endif %}
      </div>
      <div class="stat-key">Best pChEMBL</div>
    </div>
    <div class="stat">
      <div class="stat-val" style="color:{% if report.alphafold %}#58a6ff{% else %}#484f58{% endif %}">
        {% if report.alphafold %}✓{% else %}—{% endif %}
      </div>
      <div class="stat-key">AlphaFold</div>
    </div>
  </div>

  <!-- ── Tabs ── -->
  <div class="section">
    <div class="tabs">
      <button class="tab-btn active" onclick="switchTab(this,'overview')">Overview</button>
      <button class="tab-btn" onclick="switchTab(this,'structure')">3D Structure</button>
      <button class="tab-btn" onclick="switchTab(this,'bioactivity')">Bioactivity</button>
      <button class="tab-btn" onclick="switchTab(this,'ligands')">
        Ligands <span class="badge" style="background:rgba(210,153,34,.15);color:#d29922;margin-left:4px">{{ report.num_unique_ligands }}</span>
      </button>
      <button class="tab-btn" onclick="switchTab(this,'pdb')">
        PDB <span class="badge" style="background:rgba(88,166,255,.12);color:#58a6ff;margin-left:4px">{{ report.num_pdb_structures }}</span>
      </button>
      <button class="tab-btn" onclick="switchTab(this,'interactome')">
        Interactome <span class="badge" style="background:rgba(63,185,80,.12);color:#3fb950;margin-left:4px">{{ report.interactions|length }}</span>
      </button>
    </div>

    <!-- Overview -->
    <div id="tab-overview" class="tab-panel active">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.25rem">

        <div style="display:flex;flex-direction:column;gap:1rem">

          {% if u.function_description %}
          <div>
            <div class="info-key" style="margin-bottom:.5rem">Function</div>
            <div style="font-size:13.5px;color:#e6edf3;line-height:1.75">{{ u.function_description }}</div>
          </div>
          {% endif %}

          {% if u.subcellular_locations %}
          <div>
            <div class="info-key" style="margin-bottom:.4rem">Subcellular location</div>
            {% for loc in u.subcellular_locations %}
            <span class="tag tag-blue">{{ loc }}</span>
            {% endfor %}
          </div>
          {% endif %}

          {% if u.disease_associations %}
          <div>
            <div class="info-key" style="margin-bottom:.4rem">Disease associations</div>
            {% for d in u.disease_associations[:8] %}
            <div style="font-size:13px;color:#b1bac4;padding:2px 0;line-height:1.5">· {{ d }}</div>
            {% endfor %}
          </div>
          {% endif %}

        </div>

        <div style="display:flex;flex-direction:column;gap:1rem">

          {% if u.keywords %}
          <div>
            <div class="info-key" style="margin-bottom:.4rem">Keywords</div>
            {% for kw in u.keywords[:20] %}
            <span class="tag tag-purple">{{ kw }}</span>
            {% endfor %}
          </div>
          {% endif %}

          {% if go_by_cat %}
          <div>
            <div class="info-key" style="margin-bottom:.6rem">Gene Ontology</div>
            {% for cat, terms in go_by_cat.items() %}
            <div style="margin-bottom:.6rem">
              <div style="font-size:10.5px;color:#768390;text-transform:uppercase;letter-spacing:.06em;font-weight:600;margin-bottom:.3rem">
                {{ cat.replace('_',' ') }}
              </div>
              {% set tag_cls = {"molecular_function":"tag-green","biological_process":"tag-blue","cellular_component":"tag-purple"} %}
              {% for t in terms[:10] %}
              <span class="tag {{ tag_cls.get(cat,'tag-gray') }}">{{ t }}</span>
              {% endfor %}
            </div>
            {% endfor %}
          </div>
          {% endif %}

        </div>
      </div>
    </div>

    <!-- 3D Structure -->
    <div id="tab-structure" class="tab-panel">
      <div class="viewer-controls">
        <select id="structureSelect" onchange="loadStructure()">
          {% if report.alphafold %}
          <option value="{{ af_url }}" data-af="1">
            AlphaFold prediction{% if report.alphafold.mean_plddt %} — pLDDT {{ "%.0f"|format(report.alphafold.mean_plddt) }}{% endif %}
          </option>
          {% endif %}
          {% for s in report.pdb_structures %}
          <option value="https://files.rcsb.org/download/{{ s.pdb_id }}.pdb" data-af="0">
            {{ s.pdb_id }} — {{ s.method.value }}{% if s.resolution %} ({{ "%.1f"|format(s.resolution) }} Å){% endif %}
          </option>
          {% endfor %}
        </select>
        <button class="style-btn active" onclick="setStyle(this,'cartoon')">Cartoon</button>
        <button class="style-btn" onclick="setStyle(this,'surface')">Surface</button>
        <button class="style-btn" onclick="setStyle(this,'stick')">Stick</button>
      </div>

      <div id="mol-viewer">
        <div id="viewer-loading">
          <div class="spin"></div>
          <span>Loading structure…</span>
        </div>
      </div>

      <!-- Chain / Ligand selector + Download -->
      <div id="chainLigandPanel" style="display:none;margin-top:.75rem;padding:.65rem .75rem;
           background:#0d1117;border:1px solid #21262d;border-radius:7px">
        <div style="display:flex;align-items:flex-start;gap:1.5rem;flex-wrap:wrap">

          <div id="chainBlock">
            <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;
                 color:var(--muted);margin-bottom:.4rem">Chains</div>
            <div id="chainChecks" style="display:flex;gap:.4rem;flex-wrap:wrap"></div>
          </div>

          <div id="ligandBlock" style="display:none">
            <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;
                 color:var(--muted);margin-bottom:.4rem">Ligands</div>
            <div id="ligandChecks" style="display:flex;gap:.4rem;flex-wrap:wrap"></div>
          </div>

          <button class="btn btn-default btn-sm" onclick="downloadStructure()"
                  style="margin-top:auto;margin-left:auto;white-space:nowrap">⬇ Download PDB</button>
        </div>
      </div>

      <div class="plddt-legend" id="plddt-legend" style="display:none">
        <span><span class="plddt-dot" style="background:#0053d6"></span>Very high (&gt;90)</span>
        <span><span class="plddt-dot" style="background:#65cbf3"></span>Confident (70–90)</span>
        <span><span class="plddt-dot" style="background:#ffdb13"></span>Low (50–70)</span>
        <span><span class="plddt-dot" style="background:#ff7d45"></span>Very low (&lt;50)</span>
      </div>
    </div>

    <!-- Bioactivity -->
    <div id="tab-bioactivity" class="tab-panel">
      <div class="chart-grid">
        <div class="chart-card">
          <div class="chart-title">pChEMBL Value Distribution</div>
          <div class="chart-wrap"><canvas id="pchemblChart"></canvas></div>
        </div>
        <div class="chart-card">
          <div class="chart-title">Experimental Methods</div>
          <div class="chart-wrap"><canvas id="methodChart"></canvas></div>
        </div>
      </div>
      <div class="source-row">
        {% for src, cnt in source_counts.items() %}
        <div class="source-chip">
          <strong>{{ "{:,}".format(cnt) }}</strong>
          <span>{{ src }}</span>
        </div>
        {% endfor %}
        {% for atype, cnt in atype_top.items() %}
        <div class="source-chip">
          <strong>{{ "{:,}".format(cnt) }}</strong>
          <span>{{ atype }}</span>
        </div>
        {% endfor %}
      </div>
    </div>

    <!-- Ligands -->
    <div id="tab-ligands" class="tab-panel no-pad">
      {% if report.ligand_summary %}

      <!-- Ligand filter toolbar -->
      <div class="lig-toolbar">

        <!-- Row 1: filters -->
        <div class="lig-filters">
          <div class="lig-filter-group">
            <label class="lig-filter-label">Min pChEMBL</label>
            <input type="number" id="ligMinPc" class="lig-filter-input" placeholder="≥ e.g. 7.0"
                   min="0" max="12" step="0.5" value="" oninput="filterLigands()"
                   title="pChEMBL 7 ≈ 100nM · pChEMBL 9 ≈ 1nM">
          </div>
          <div class="lig-filter-group">
            <label class="lig-filter-label">Max IC50 (nM)</label>
            <input type="number" id="ligMaxIc50" class="lig-filter-input" placeholder="≤ e.g. 100"
                   min="0" step="1" value="" oninput="filterLigands()"
                   title="Only IC50 assays ≤ this value">
          </div>
          <div class="lig-filter-group">
            <label class="lig-filter-label">Max Ki (nM)</label>
            <input type="number" id="ligMaxKi" class="lig-filter-input" placeholder="≤ e.g. 50"
                   min="0" step="1" value="" oninput="filterLigands()"
                   title="Only Ki assays ≤ this value">
          </div>
          <div class="lig-filter-group">
            <label class="lig-filter-label">Assay type</label>
            <select id="ligActType" class="lig-filter-select" onchange="filterLigands()">
              <option value="">All types</option>
              {% for atype in report.ligand_summary | map(attribute='best_activity_type') | select | unique | sort %}
              <option value="{{ atype }}">{{ atype }}</option>
              {% endfor %}
            </select>
          </div>
          <div class="lig-filter-group">
            <label class="lig-filter-label">Source</label>
            <select id="ligSource" class="lig-filter-select" onchange="filterLigands()">
              <option value="">All sources</option>
              <option value="chembl">ChEMBL only</option>
              <option value="bindingdb">BindingDB only</option>
            </select>
          </div>
          <div class="lig-filter-group">
            <label class="lig-filter-label">Show</label>
            <select id="ligLimit" class="lig-filter-select" onchange="onLimitChange()">
              <option value="10" selected>Top 10</option>
              <option value="25">Top 25</option>
              <option value="50">Top 50</option>
              <option value="0">All</option>
            </select>
          </div>
        </div>

        <!-- Row 2: count + downloads -->
        <div class="lig-actions">
          <span class="lig-count" id="ligCount"></span>
          <div class="lig-dl-group">
            <span class="lig-filter-label">Download filtered:</span>
            <button class="btn btn-default btn-sm" onclick="downloadLigands('csv')">CSV</button>
            <button class="btn btn-default btn-sm" onclick="downloadLigands('tsv')">TSV</button>
            <button class="btn btn-default btn-sm" onclick="downloadSDF()">⬇ SDF</button>
          </div>
        </div>
      </div>

      <!-- Ligand table -->
      <div style="overflow-x:auto">
      <table class="data-table" id="ligTable">
        <thead><tr>
          <th style="width:36px">#</th>
          <th>Name</th>
          <th>ChEMBL</th>
          <th>Type</th>
          <th class="r">nM</th>
          <th class="r">pChEMBL</th>
          <th class="c">Assays</th>
          <th>Sources</th>
          <th>SMILES</th>
        </tr></thead>
        <tbody id="ligTbody">
        {% for lig in report.ligand_summary %}
        <tr class="lig-row"
            data-pc="{{ lig.best_pchembl or '' }}"
            data-nm="{{ lig.best_activity_value_nM or '' }}"
            data-atype="{{ lig.best_activity_type or '' }}"
            data-source="{{ lig.sources | join(',') | lower }}">
          <td class="lig-rank" style="color:#768390;font-size:12px">{{ loop.index }}</td>
          <td><div style="color:#e6edf3;font-size:13px">{{ lig.name or "—" }}</div></td>
          <td>
            {% if lig.chembl_id %}
            <a href="https://www.ebi.ac.uk/chembl/compound_report_card/{{ lig.chembl_id }}"
               target="_blank" class="mono" style="font-size:11.5px">{{ lig.chembl_id }}</a>
            {% else %}<span style="color:#768390">—</span>{% endif %}
          </td>
          <td>
            {% if lig.best_activity_type %}
            <span class="tag tag-blue" style="font-size:11px">{{ lig.best_activity_type }}</span>
            {% else %}<span style="color:#768390">—</span>{% endif %}
          </td>
          <td class="r mono" style="font-size:12px">
            {% if lig.best_activity_value_nM %}{{ "%.2f"|format(lig.best_activity_value_nM) }}{% else %}—{% endif %}
          </td>
          <td class="r {{ pchembl_class(lig.best_pchembl) }}">
            {% if lig.best_pchembl %}{{ "%.2f"|format(lig.best_pchembl) }}{% else %}—{% endif %}
          </td>
          <td class="c" style="color:#b1bac4">{{ lig.num_assays }}</td>
          <td>{% for s in lig.sources %}<span class="tag tag-green" style="font-size:10.5px">{{ s }}</span>{% endfor %}</td>
          <td class="mono smiles-cell" style="font-size:10.5px;color:#58a6ff;max-width:220px;cursor:pointer"
              data-smiles="{{ lig.smiles }}"
              data-smiles-label="{{ lig.name or lig.chembl_id or '' }}"
              data-expanded="0"
              title="Click to expand • Hover to preview structure"
              onclick="toggleSmiles(this)">
            <span class="smiles-short" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block">{{ lig.smiles[:45] }}{% if lig.smiles|length > 45 %}…{% endif %}</span>
            <span class="smiles-full" style="display:none;white-space:pre-wrap;word-break:break-all">{{ lig.smiles }}</span>
            <span class="smiles-copy" style="display:none;font-size:10px;color:#8b949e;margin-left:4px" onclick="event.stopPropagation();navigator.clipboard.writeText('{{ lig.smiles }}')">📋 copy</span>
          </td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
      </div>
      {% else %}
      <div style="padding:2rem;text-align:center;color:#768390">No ligand data.</div>
      {% endif %}
    </div>

    <!-- PDB -->
    <div id="tab-pdb" class="tab-panel no-pad">
      {% if report.pdb_structures %}
      <div style="overflow-x:auto">
      <table class="data-table" id="pdbTable">
        <thead><tr>
          <th>PDB ID</th><th>Method</th><th class="r">Resolution</th>
          <th>Date</th><th>Ligands</th><th>Title</th>
        </tr></thead>
        <tbody>
        {% for s in report.pdb_structures %}
        {% set mcls = {"X-RAY DIFFRACTION":"tag-blue","ELECTRON MICROSCOPY":"tag-purple","SOLUTION NMR":"tag-green"} %}
        <tr class="pdb-row{% if loop.index > 10 %} pdb-extra" style="display:none{% endif %}">
          <td>
            <a href="https://www.rcsb.org/structure/{{ s.pdb_id }}" target="_blank"
               class="mono" style="font-weight:600;font-size:13px">{{ s.pdb_id }}</a>
          </td>
          <td><span class="tag {{ mcls.get(s.method.value,'tag-gray') }}" style="font-size:11px">{{ s.method.value }}</span></td>
          <td class="r mono" style="font-size:12px">
            {% if s.resolution %}{{ "%.2f"|format(s.resolution) }} Å{% else %}—{% endif %}
          </td>
          <td style="font-size:12px;color:#e6edf3">{{ s.release_date or "—" }}</td>
          <td>
            {% for l in s.ligands %}
            <span class="tag tag-orange" style="font-size:10.5px">{{ l.ligand_id }}</span>
            {% else %}<span style="color:#e6edf3">—</span>
            {% endfor %}
          </td>
          <td style="font-size:12px;color:#e6edf3;max-width:340px;overflow:hidden;
              text-overflow:ellipsis;white-space:nowrap">{{ s.title[:100] }}{% if s.title|length > 100 %}…{% endif %}</td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
      </div>
      {% if report.pdb_structures|length > 10 %}
      <div style="text-align:center;padding:.75rem 0 1rem">
        <button id="pdbExpandBtn" class="btn btn-default btn-sm" onclick="togglePdbRows()">
          Show all {{ report.pdb_structures|length }} structures ▼
        </button>
      </div>
      {% endif %}
      {% else %}
      <div style="padding:2rem;text-align:center;color:#768390">No PDB structures found.</div>
      {% endif %}
    </div>

    <!-- Interactome -->
    <div id="tab-interactome" class="tab-panel">
      {% if report.interactions %}
      <div class="interactome-layout">

        <!-- Network canvas -->
        <div class="interactome-graph-wrap">
          <div id="cy"></div>
          <div class="interactome-legend">
            <div class="il-item"><span class="il-dot" style="background:#58a6ff"></span>Query target</div>
            <div class="il-item"><span class="il-dot" style="background:#3fb950"></span>Score ≥ 0.9</div>
            <div class="il-item"><span class="il-dot" style="background:#d29922"></span>Score 0.7–0.9</div>
            <div class="il-item"><span class="il-dot" style="background:#8b949e"></span>Score &lt; 0.7</div>
          </div>
        </div>

        <!-- Side panel: table + node info -->
        <div class="interactome-side">
          <div id="nodeInfo" class="node-info-box" style="display:none"></div>

          <div class="interactome-table-wrap">
            <table class="data-table" id="interactomeTable">
              <thead><tr>
                <th>Partner</th>
                <th class="r">Score</th>
                <th class="r">Experimental</th>
                <th class="r">Database</th>
                <th class="r">Text Mining</th>
              </tr></thead>
              <tbody>
              {% for ix in report.interactions %}
              <tr class="ix-row" data-gene="{{ ix.gene_b }}" style="cursor:pointer"
                  onclick="highlightNode('{{ ix.gene_b }}')">
                <td style="font-weight:600;color:#e6edf3">{{ ix.gene_b }}</td>
                <td class="r mono" style="color:{% if ix.score >= 0.9 %}#3fb950{% elif ix.score >= 0.7 %}#d29922{% else %}#b1bac4{% endif %}">
                  {{ "%.3f"|format(ix.score) }}
                </td>
                <td class="r mono" style="color:#b1bac4">{{ "%.3f"|format(ix.experimental) if ix.experimental else "—" }}</td>
                <td class="r mono" style="color:#b1bac4">{{ "%.3f"|format(ix.database) if ix.database else "—" }}</td>
                <td class="r mono" style="color:#b1bac4">{{ "%.3f"|format(ix.textmining) if ix.textmining else "—" }}</td>
              </tr>
              {% endfor %}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div style="margin-top:.75rem;font-size:11.5px;color:#768390">
        Data from <a href="https://string-db.org" target="_blank">STRING DB</a> · Click a node to inspect · Click a table row to highlight
      </div>
      {% else %}
      <div style="padding:2rem;text-align:center;color:#768390">No interaction data available.</div>
      {% endif %}
    </div>

  </div><!-- /tabs section -->

  <div style="text-align:center;font-size:11.5px;color:#30363d;margin-top:2rem;padding-top:1.5rem;border-top:1px solid #21262d">
    TargetRecon v{{ version }} &nbsp;·&nbsp; UniProt · RCSB PDB · AlphaFold DB · ChEMBL · BindingDB
  </div>

</div><!-- /main-content inner -->
</div><!-- /main-content -->
</div><!-- /app-layout -->

<!-- ── Data ── -->
<script>
var PCHEMBL_VALS = {{ pchembl_json | safe }};
var METHOD_COUNTS = {{ method_json | safe }};
var AF_URL = {{ af_url_json | safe }};
var QUERY = {{ query_json | safe }};
var INTERACTIONS = {{ interactions_json | safe }};
var GENE = {{ gene_json | safe }};
</script>

<!-- ── JS ── -->
<script>
// ── Tabs ──────────────────────────────────────────────────────────────────
function switchTab(btn, id) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + id).classList.add('active');
  if (id === 'structure') initViewer();
  if (id === 'bioactivity') initCharts();
  if (id === 'interactome') initInteractome();
}

// ── 3D viewer ────────────────────────────────────────────────────────────
var viewer = null, viewerReady = false, currentStyle = 'cartoon';
var _currentPDB = null, _currentPDBName = 'structure';

function initViewer() {
  if (viewerReady) return;
  if (typeof $3Dmol === 'undefined') { setTimeout(initViewer, 200); return; }
  viewer = $3Dmol.createViewer(document.getElementById('mol-viewer'),
    { backgroundColor: '#030508', antialias: true });
  viewerReady = true;
  loadStructure();
}

function loadStructure() {
  if (!viewerReady) return;
  var sel = document.getElementById('structureSelect');
  var url = sel.value;
  var isAF = sel.options[sel.selectedIndex].dataset.af === '1';
  var label = sel.options[sel.selectedIndex].text.trim().split(' ')[0];
  _currentPDBName = label || 'structure';
  document.getElementById('plddt-legend').style.display = isAF ? 'flex' : 'none';
  var ld = document.getElementById('viewer-loading');
  if (ld) { ld.style.opacity = '1'; ld.style.display = 'flex'; }
  viewer.clear();
  fetch(url)
    .then(r => r.text())
    .then(pdb => {
      _currentPDB = pdb;
      viewer.addModel(pdb, 'pdb');
      applyStyle(isAF);
      viewer.zoomTo(); viewer.render();
      if (ld) { ld.style.opacity = '0'; setTimeout(() => ld && (ld.style.display = 'none'), 300); }
      populateChainLigand(pdb);
    })
    .catch(() => { if (ld) ld.innerHTML = '<span style="color:#f85149">Failed to load structure</span>'; });
}

function populateChainLigand(pdb) {
  var chains = new Set(), ligands = new Set();
  pdb.split('\n').forEach(line => {
    var rec = line.substring(0, 6).trim();
    if (rec === 'ATOM') {
      var ch = line[21]; if (ch && ch.trim()) chains.add(ch.trim());
    } else if (rec === 'HETATM') {
      var ch = line[21]; if (ch && ch.trim()) chains.add(ch.trim());
      var res = line.substring(17, 20).trim();
      if (res && res !== 'HOH' && res !== 'DOD') ligands.add(res);
    }
  });

  // Chains
  var cc = document.getElementById('chainChecks');
  cc.innerHTML = '';
  [...chains].sort().forEach(ch => {
    var lbl = document.createElement('label');
    lbl.style.cssText = 'display:flex;align-items:center;gap:4px;font-size:12px;color:#e6edf3;cursor:pointer;' +
      'background:#21262d;border:1px solid #30363d;border-radius:5px;padding:2px 8px';
    lbl.innerHTML = '<input type="checkbox" checked style="accent-color:#58a6ff"> ' + ch;
    cc.appendChild(lbl);
  });

  // Ligands
  var lc = document.getElementById('ligandChecks');
  lc.innerHTML = '';
  var ligBlock = document.getElementById('ligandBlock');
  if (ligands.size > 0) {
    [...ligands].sort().forEach(res => {
      var lbl = document.createElement('label');
      lbl.style.cssText = 'display:flex;align-items:center;gap:4px;font-size:12px;color:#e6edf3;cursor:pointer;' +
        'background:#21262d;border:1px solid #30363d;border-radius:5px;padding:2px 8px';
      lbl.innerHTML = '<input type="checkbox" checked style="accent-color:#d29922"> ' + res;
      lc.appendChild(lbl);
    });
    ligBlock.style.display = '';
  } else {
    ligBlock.style.display = 'none';
  }

  document.getElementById('chainLigandPanel').style.display = '';
}

function downloadStructure() {
  if (!_currentPDB) return;

  // Collect selected chains and ligands
  var selChains = new Set();
  document.querySelectorAll('#chainChecks input[type=checkbox]:checked').forEach(cb => {
    selChains.add(cb.parentElement.textContent.trim());
  });
  var selLigands = new Set();
  document.querySelectorAll('#ligandChecks input[type=checkbox]:checked').forEach(cb => {
    selLigands.add(cb.parentElement.textContent.trim());
  });

  var lines = _currentPDB.split('\n').filter(line => {
    var rec = line.substring(0, 6).trim();
    if (rec === 'ATOM') {
      var ch = (line[21] || '').trim();
      return selChains.has(ch);
    }
    if (rec === 'HETATM') {
      var ch = (line[21] || '').trim();
      var res = line.substring(17, 20).trim();
      if (res === 'HOH' || res === 'DOD') return selChains.has(ch);
      return selChains.has(ch) && selLigands.has(res);
    }
    return true; // keep HEADER, REMARK, TER, END, etc.
  });

  var blob = new Blob([lines.join('\n')], { type: 'chemical/x-pdb' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = _currentPDBName + '_filtered.pdb';
  a.click();
  URL.revokeObjectURL(a.href);
}

function applyStyle(isAF) {
  viewer.setStyle({}, {});
  if (currentStyle === 'surface') {
    viewer.addSurface($3Dmol.SurfaceType.VDW, { opacity: 0.75, colorscheme: 'ssJmol' }, {});
    return;
  }
  if (currentStyle === 'stick') {
    viewer.setStyle({}, { stick: { colorscheme: 'Jmol', radius: 0.15 } });
  } else {
    if (isAF) {
      viewer.setStyle({}, { cartoon: { colorfunc: function(a) {
        var b = a.b;
        return b > 90 ? '#0053d6' : b > 70 ? '#65cbf3' : b > 50 ? '#ffdb13' : '#ff7d45';
      }}});
    } else {
      viewer.setStyle({}, { cartoon: { colorscheme: 'ssJmol' }});
      viewer.setStyle({ hetflag: true }, { stick: { colorscheme: 'greenCarbon', radius: 0.14 }});
    }
  }
}

function setStyle(btn, style) {
  document.querySelectorAll('.style-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  currentStyle = style;
  if (!viewerReady) return;
  var sel = document.getElementById('structureSelect');
  var isAF = sel.options[sel.selectedIndex].dataset.af === '1';
  viewer.removeAllSurfaces();
  applyStyle(isAF);
  viewer.render();
}

// ── Charts ────────────────────────────────────────────────────────────────
var chartsInit = false;
var _chartRetries = 0;
function initCharts() {
  if (chartsInit) return;
  if (typeof Chart === 'undefined') {
    if (_chartRetries++ < 30) { setTimeout(initCharts, 300); }
    else {
      ['pchemblChart','methodChart'].forEach(id => {
        var w = document.getElementById(id);
        if (w) { w.parentNode.innerHTML = '<div class="chart-nodata">Chart.js failed to load.</div>'; }
      });
    }
    return;
  }
  chartsInit = true;

  Chart.defaults.color = '#b1bac4';
  Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';

  // ── pChEMBL histogram ──────────────────────────────────────────────────
  var pWrap = document.getElementById('pchemblChart');
  if (!pWrap) return;
  if (!PCHEMBL_VALS || PCHEMBL_VALS.length === 0) {
    pWrap.parentNode.innerHTML = '<div class="chart-nodata">No pChEMBL data available for this target.</div>';
  } else {
    var bins = {};
    PCHEMBL_VALS.forEach(v => {
      var b = (Math.floor(v * 2) / 2).toFixed(1);
      bins[b] = (bins[b] || 0) + 1;
    });
    var bL = Object.keys(bins).sort((a,b) => +a - +b);
    var bD = bL.map(k => bins[k]);
    var bC = bL.map(v => +v >= 9 ? '#3fb950' : +v >= 7 ? '#d29922' : '#58a6ff');
    new Chart(pWrap, {
      type: 'bar',
      data: { labels: bL, datasets: [{ data: bD, backgroundColor: bC,
        borderRadius: 3, borderSkipped: false, barPercentage: .88 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { backgroundColor: '#1c2128', titleColor: '#e6edf3',
            bodyColor: '#b1bac4', borderColor: '#30363d', borderWidth: 1 }
        },
        scales: {
          x: { title: { display: true, text: 'pChEMBL value', color: '#b1bac4', font: { size: 11 } },
               ticks: { font: { size: 10 }, maxRotation: 0, color: '#b1bac4' },
               grid: { display: false }, border: { color: '#30363d' } },
          y: { title: { display: true, text: 'Count', color: '#b1bac4', font: { size: 11 } },
               ticks: { font: { size: 10 }, color: '#b1bac4' }, border: { color: '#30363d' } }
        }
      }
    });
  }

  // ── Experimental methods doughnut ──────────────────────────────────────
  var mWrap = document.getElementById('methodChart');
  if (!mWrap) return;
  var mKeys = Object.keys(METHOD_COUNTS);
  if (!mKeys.length) {
    mWrap.parentNode.innerHTML = '<div class="chart-nodata">No experimental method data available.</div>';
  } else {
    new Chart(mWrap, {
      type: 'doughnut',
      data: {
        labels: mKeys,
        datasets: [{ data: Object.values(METHOD_COUNTS),
          backgroundColor: ['#58a6ff','#bc8cff','#3fb950','#d29922','#f85149'],
          borderWidth: 0, hoverOffset: 5 }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '58%',
        plugins: {
          legend: { position: 'right', labels: { color: '#b1bac4', font: { size: 11 }, boxWidth: 12, padding: 12 } },
          tooltip: { backgroundColor: '#1c2128', titleColor: '#e6edf3',
            bodyColor: '#b1bac4', borderColor: '#30363d', borderWidth: 1 }
        }
      }
    });
  }
}

// ── AI Agent ─────────────────────────────────────────────────────────────
function runAI() {
  var question = document.getElementById('aiQuestion').value.trim();
  var btn = document.getElementById('aiBtn');
  var status = document.getElementById('aiStatus');
  btn.disabled = true;
  btn.textContent = 'Asking Claude…';
  status.textContent = '';
  document.getElementById('aiResult').style.display = 'none';

  fetch('/ai', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: QUERY, question: question })
  })
  .then(r => r.json())
  .then(data => {
    btn.disabled = false;
    btn.textContent = 'Analyse with Claude';
    if (data.error) {
      status.style.color = '#f85149';
      status.textContent = data.error;
      return;
    }
    document.getElementById('aiLabel').textContent = 'Claude analysis';
    document.getElementById('aiText').textContent = data.result;
    document.getElementById('aiResult').style.display = 'block';
  })
  .catch(e => {
    btn.disabled = false;
    btn.textContent = 'Analyse with Claude';
    status.style.color = '#f85149';
    status.textContent = 'Request failed: ' + e.message;
  });
}

// Keyboard shortcut: Enter in AI textarea
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('aiQuestion')?.addEventListener('keydown', e => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) runAI();
  });
});

// ── Interactome (Cytoscape.js) ───────────────────────────────────────────────
var cy = null, cyInit = false;

function initInteractome() {
  if (cyInit) return;
  if (typeof cytoscape === 'undefined') { setTimeout(initInteractome, 300); return; }
  cyInit = true;

  if (!INTERACTIONS || !INTERACTIONS.length) return;

  // Build score lookup first
  var scoreMap = {};
  INTERACTIONS.forEach(function(ix) { scoreMap[ix.gene_b] = ix.score; });

  // Build elements
  var elements = [];

  // Center node
  elements.push({ data: {
    id: GENE, label: GENE,
    isCenter: true,
    color: '#58a6ff',
    border: '#58a6ff',
    size: 50,
  }});

  // Partner nodes — color by score
  INTERACTIONS.forEach(function(ix) {
    var s = ix.score;
    var col = s >= 0.9 ? '#3fb950' : s >= 0.7 ? '#d29922' : '#8b949e';
    elements.push({ data: {
      id: ix.gene_b, label: ix.gene_b,
      isCenter: false,
      color: col,
      border: col,
      size: 28 + Math.round(s * 10),
    }});
  });

  INTERACTIONS.forEach(function(ix) {
    var score = ix.score;
    elements.push({ data: {
      id: GENE + '--' + ix.gene_b,
      source: GENE,
      target: ix.gene_b,
      score: score,
      width: Math.max(1, score * 6),
      color: score >= 0.9 ? '#3fb950' : score >= 0.7 ? '#d29922' : '#484f58',
    }});
  });

  cy = cytoscape({
    container: document.getElementById('cy'),
    elements: elements,
    style: [
      { selector: 'node', style: {
        'background-color': 'data(color)',
        'label': 'data(label)',
        'color': '#e6edf3',
        'font-size': '11px',
        'font-family': 'Inter, system-ui, sans-serif',
        'text-valign': 'bottom',
        'text-margin-y': '4px',
        'width': 'data(size)',
        'height': 'data(size)',
        'border-width': '2px',
        'border-color': 'data(border)',
        'border-opacity': 0.6,
        'text-outline-width': '2px',
        'text-outline-color': '#0d1117',
      }},
      { selector: 'node[?isCenter]', style: {
        'border-opacity': 1,
        'border-width': '3px',
        'font-weight': '700',
        'font-size': '13px',
      }},
      { selector: 'node:selected', style: {
        'border-color': '#f0883e',
        'border-width': '3px',
      }},
      { selector: 'edge', style: {
        'width': 'data(width)',
        'line-color': 'data(color)',
        'opacity': 0.7,
        'curve-style': 'bezier',
      }},
    ],
    layout: { name: 'cose', idealEdgeLength: 120, nodeOverlap: 20, padding: 20, animate: false },
    userZoomingEnabled: true,
    userPanningEnabled: true,
  });

  // Node click → show info + highlight table row
  cy.on('tap', 'node', function(evt) {
    var gene = evt.target.id();
    showNodeInfo(gene);
    highlightTableRow(gene);
  });
}

function showNodeInfo(gene) {
  var box = document.getElementById('nodeInfo');
  if (!box) return;
  if (gene === GENE) {
    box.style.display = 'block';
    box.innerHTML = '<div class="ni-gene">' + gene + '</div><div class="ni-sub">Query target</div>' +
      '<a href="https://www.uniprot.org/uniprot/' + encodeURIComponent(gene) + '" target="_blank" class="ni-link">UniProt ↗</a>';
    return;
  }
  var ix = INTERACTIONS.find(function(i){ return i.gene_b === gene; });
  if (!ix) return;
  var scoreColor = ix.score >= 0.9 ? '#3fb950' : ix.score >= 0.7 ? '#d29922' : '#b1bac4';
  box.style.display = 'block';
  box.innerHTML =
    '<div class="ni-gene">' + gene + '</div>' +
    '<div class="ni-score" style="color:' + scoreColor + '">STRING score: ' + ix.score.toFixed(3) + '</div>' +
    '<div class="ni-row"><span>Experimental</span><span>' + (ix.experimental||0).toFixed(3) + '</span></div>' +
    '<div class="ni-row"><span>Database</span><span>' + (ix.database||0).toFixed(3) + '</span></div>' +
    '<div class="ni-row"><span>Text mining</span><span>' + (ix.textmining||0).toFixed(3) + '</span></div>' +
    '<div class="ni-links">' +
    '<a href="/recon?q=' + encodeURIComponent(gene) + '" class="ni-link">Recon ↗</a>' +
    '<a href="https://string-db.org/network/' + encodeURIComponent(ix.string_id_b) + '" target="_blank" class="ni-link">STRING ↗</a>' +
    '</div>';
}

function highlightNode(gene) {
  if (!cy) return;
  cy.$(':selected').unselect();
  cy.$('#' + gene).select();
  cy.animate({ fit: { eles: cy.$('#' + GENE + ', #' + gene), padding: 60 }, duration: 400 });
  showNodeInfo(gene);
}

function highlightTableRow(gene) {
  document.querySelectorAll('.ix-row').forEach(function(r){
    r.style.background = r.dataset.gene === gene ? 'rgba(88,166,255,.08)' : '';
  });
}

// ── SMILES 2D hover popup ─────────────────────────────────────────────────────
var _sdDrawer = null;
var _sdHideTimer = null;

function _getDrawer() {
  if (_sdDrawer) return _sdDrawer;
  if (typeof SmilesDrawer === 'undefined') return null;
  _sdDrawer = new SmilesDrawer.Drawer({
    width: 220, height: 180,
    bondThickness: 1.2,
    atomVisualization: 'default',
    themes: {
      custom: {
        C: '#e6edf3', O: '#f85149', N: '#58a6ff', S: '#d29922',
        P: '#bc8cff', F: '#3fb950', Cl: '#3fb950', Br: '#d29922',
        I: '#bc8cff', H: '#b1bac4', DEFAULT: '#e6edf3',
        background: '#161b22', bonds: '#8b949e',
      }
    }
  });
  return _sdDrawer;
}

function showSmilesPopup(el, smiles, label) {
  clearTimeout(_sdHideTimer);
  var drawer = _getDrawer();
  if (!drawer || !smiles) return;
  var popup = document.getElementById('smilesPopup');
  var canvas = document.getElementById('smilesCanvas');
  document.getElementById('smilesLabel').textContent = label || smiles;

  SmilesDrawer.parse(smiles, function(tree) {
    drawer.draw(tree, canvas, 'custom', false);
  }, function() {
    // parse error — show raw SMILES only
    var ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  });

  // Use fixed positioning (viewport coords, no scroll math needed)
  popup.style.display = 'block';
  var rect = el.getBoundingClientRect();
  var pw = popup.offsetWidth  || 238;
  var ph = popup.offsetHeight || 220;

  var left = rect.left;
  var top  = rect.bottom + 6;

  // Flip left if overflows right edge
  if (left + pw > window.innerWidth - 8)  left = window.innerWidth - pw - 8;
  if (left < 8) left = 8;

  // Flip above if overflows bottom edge
  if (top + ph > window.innerHeight - 8) top = rect.top - ph - 6;
  if (top < 8) top = 8;

  popup.style.left = left + 'px';
  popup.style.top  = top  + 'px';
}

function hideSmilesPopup() {
  _sdHideTimer = setTimeout(function() {
    document.getElementById('smilesPopup').style.display = 'none';
  }, 120);
}

// Attach hover to all SMILES cells (called after table renders / filters)
function attachSmilesHover() {
  document.querySelectorAll('[data-smiles]').forEach(function(el) {
    el.addEventListener('mouseenter', function() {
      showSmilesPopup(el, el.dataset.smiles, el.dataset.smilesLabel);
    });
    el.addEventListener('mouseleave', hideSmilesPopup);
  });
}
document.addEventListener('DOMContentLoaded', attachSmilesHover);

// ── Sidebar range sliders ────────────────────────────────────────────────────
function upd(hiddenId, displayId, val) {
  document.getElementById(hiddenId).value = val;
  var el = document.getElementById(displayId);
  if (el) el.textContent = hiddenId.includes('Res') ? val + ' Å' : val;
}
function updBio(hiddenId, displayId, val) {
  var v = parseInt(val);
  document.getElementById(hiddenId).value = v >= 5000 ? 10000 : v;
  var el = document.getElementById(displayId);
  if (el) el.textContent = v >= 5000 ? 'All' : val;
}

// ── Ligand table filter + download ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', filterLigands);

function onLimitChange() {
  filterLigands();
}

function filterLigands() {
  var minPc    = parseFloat(document.getElementById('ligMinPc')?.value)    || 0;
  var maxIc50  = parseFloat(document.getElementById('ligMaxIc50')?.value)  || Infinity;
  var maxKi    = parseFloat(document.getElementById('ligMaxKi')?.value)    || Infinity;
  var atype    = (document.getElementById('ligActType')?.value || '').toLowerCase();
  var srcFilt  = (document.getElementById('ligSource')?.value  || '').toLowerCase();
  var limit    = parseInt(document.getElementById('ligLimit')?.value)      || 10;

  var rows = document.querySelectorAll('#ligTbody .lig-row');
  var shown = 0;
  rows.forEach(function(row) {
    var pc  = parseFloat(row.dataset.pc)    || 0;
    var nm  = parseFloat(row.dataset.nm)    || Infinity;
    var at  = (row.dataset.atype  || '').toLowerCase();
    var src = (row.dataset.source || '').toLowerCase();

    var pass = true;
    if (minPc > 0 && pc < minPc) pass = false;

    // IC50 cutoff: only applies when this row IS an IC50 measurement
    if (maxIc50 < Infinity && at === 'ic50' && nm > maxIc50) pass = false;
    // Ki cutoff: only applies when this row IS a Ki measurement
    if (maxKi < Infinity && at === 'ki' && nm > maxKi) pass = false;
    // If a specific assay type cutoff is set but this row is a DIFFERENT type, skip it
    if (maxIc50 < Infinity && at !== 'ic50' && maxKi === Infinity) pass = false;
    if (maxKi < Infinity && at !== 'ki' && maxIc50 === Infinity) pass = false;

    if (atype && at !== atype) pass = false;

    // Source filter: check if the selected source appears in the comma-joined sources
    if (srcFilt && !src.split(',').some(s => s.trim() === srcFilt)) pass = false;

    if (limit > 0 && shown >= limit) pass = false;

    row.style.display = pass ? '' : 'none';
    if (pass) {
      shown++;
      row.querySelector('.lig-rank').textContent = shown;
    }
  });

  var countEl = document.getElementById('ligCount');
  if (countEl) countEl.textContent = 'Showing ' + shown + ' of ' + rows.length;
}

function downloadSDF() {
  var minPc   = document.getElementById('ligMinPc')?.value   || '';
  var maxIc50 = document.getElementById('ligMaxIc50')?.value || '';
  var maxKi   = document.getElementById('ligMaxKi')?.value   || '';
  var atype   = document.getElementById('ligActType')?.value  || '';
  var limit   = document.getElementById('ligLimit')?.value    || '0';

  var visible = document.querySelectorAll('#ligTbody .lig-row:not([style*="display: none"])').length;
  if (visible === 0) { alert('No ligands match the current filters.'); return; }

  // Use the tightest nM cutoff that applies
  var maxNm = '';
  if (maxIc50 && !maxKi) maxNm = maxIc50;
  else if (maxKi && !maxIc50) maxNm = maxKi;
  else if (maxIc50 && maxKi) maxNm = Math.min(parseFloat(maxIc50), parseFloat(maxKi));

  var params = new URLSearchParams({ q: QUERY });
  if (minPc)  params.set('min_pc', minPc);
  if (maxNm)  params.set('max_nm', maxNm);
  if (atype)  params.set('atype', atype);
  if (limit && parseInt(limit) > 0) params.set('top_n', limit);
  params.set('sid', window._sid||'');

  window.location.href = '/export/sdf?' + params.toString();
}

function toggleSmiles(td) {
  var expanded = td.getAttribute('data-expanded') === '1';
  td.querySelector('.smiles-short').style.display = expanded ? 'block' : 'none';
  td.querySelector('.smiles-full').style.display  = expanded ? 'none'  : 'block';
  td.querySelector('.smiles-copy').style.display  = expanded ? 'none'  : 'inline';
  td.setAttribute('data-expanded', expanded ? '0' : '1');
}
function togglePdbRows() {
  var extras = document.querySelectorAll('.pdb-extra');
  var btn = document.getElementById('pdbExpandBtn');
  var total = document.querySelectorAll('.pdb-row').length;
  var hidden = extras[0] && extras[0].style.display === 'none';
  extras.forEach(function(r){ r.style.display = hidden ? '' : 'none'; });
  if (btn) btn.textContent = hidden ? 'Show fewer ▲' : 'Show all ' + total + ' structures ▼';
}

function downloadLigands(fmt) {
  var rows = document.querySelectorAll('#ligTbody .lig-row');
  var headers = ['Rank','Name','ChEMBL','ActivityType','nM','pChEMBL','Assays','Sources','SMILES'];
  var sep = fmt === 'tsv' ? '\t' : ',';
  var lines = [headers.join(sep)];

  var rank = 0;
  rows.forEach(function(row) {
    if (row.style.display === 'none') return;
    rank++;
    var cells = row.querySelectorAll('td');
    var name   = cells[1]?.textContent.trim() || '';
    var chembl = cells[2]?.textContent.trim() || '';
    var atype  = cells[3]?.textContent.trim() || '';
    var nm     = cells[4]?.textContent.trim() || '';
    var pc     = cells[5]?.textContent.trim() || '';
    var assays = cells[6]?.textContent.trim() || '';
    var srcs   = cells[7]?.textContent.trim().replace(/\s+/g,' ') || '';
    var smiles = row.querySelector('td:last-child')?.title || cells[8]?.textContent.trim() || '';
    var vals = [rank, name, chembl, atype, nm, pc, assays, srcs, smiles];
    if (fmt === 'csv') vals = vals.map(v => '"' + String(v).replace(/"/g,'""') + '"');
    lines.push(vals.join(sep));
  });

  var blob = new Blob([lines.join('\n')], {type: fmt === 'tsv' ? 'text/tab-separated-values' : 'text/csv'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = QUERY + '_ligands.' + fmt;
  a.click();
}
</script>
<script>
function _showSpinner() {
  var btn = document.querySelector('#sbForm button[type=submit]');
  if (!btn) return;
  btn.disabled = true;
  btn.innerHTML = '<span class="spin" style="width:13px;height:13px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:5px"></span>Searching';
}
function _getParams(q) {
  return new URLSearchParams({
    q: q,
    max_res: document.getElementById('hMaxRes').value,
    min_pc:  document.getElementById('hMinPc').value,
    max_bio: document.getElementById('hMaxBio').value,
    use_chembl:    document.getElementById('hUseChembl').value,
    use_bindingdb: document.getElementById('hUseBdb').value,
    sid:     window._sid||'',
  });
}
function _doSearch(q) {
  if (!q) return;
  _showSpinner();
  var params = _getParams(q);
  fetch('/recon/run?' + params.toString())
    .then(function(r){ return r.text(); })
    .then(function(html){ if(window.navTo)window.navTo(html);else{document.open();document.write(html);document.close();} })
    .catch(function(){ window.location.href = '/recon/run?' + params.toString(); });
}
document.addEventListener('DOMContentLoaded', function() {
  document.getElementById('sbForm').addEventListener('submit', function(e) {
    e.preventDefault();
    var q = (document.getElementById('sbQ').value || '').trim();
    _doSearch(q);
  });
});
function showSearchSpinner() {}
function showSearchOverlay(q) { _doSearch(q); }
</script>
<script>window.RECON_QUERY = {{ query_json | safe }};</script>
<script>
(function(){
  var sid='';
  try{
    var urlSid=new URLSearchParams(window.location.search).get('sid')||'';
    sid=urlSid||window._sid||sessionStorage.getItem('tr_session_id')||'';
  }catch(e){}
  if(sid){document.querySelectorAll('a[href^="/export/"]').forEach(function(a){
    if(a.href.indexOf('sid=')===-1)a.href+=(a.href.indexOf('?')===-1?'?':'&')+'sid='+encodeURIComponent(sid);
  });}
})();
</script>
{{ chat_panel | safe }}
</body>
</html>
"""


# ── Sketcher page ─────────────────────────────────────────────────────────────
SKETCHER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Draw Structure — TargetRecon</title>
<link rel="stylesheet" href="/static/style.css">
<style>
.sk-wrap { display:flex; flex-direction:column; height:calc(100vh - 56px); }
.sk-toolbar {
  display:flex; align-items:center; gap:.75rem;
  padding:.6rem 1rem; background:#0d1117;
  border-bottom:1px solid #21262d; flex-shrink:0;
}
.sk-hint { font-size:12px; color:#768390; margin-left:.25rem }
#ketcherFrame {
  flex:1; border:none; width:100%; background:#0d1117;
  filter: invert(1) hue-rotate(180deg);
}
.sk-result {
  padding:.75rem 1rem; background:#0d1117; border-top:1px solid #21262d;
  flex-shrink:0; display:none;
}
.sk-result-inner { display:flex; align-items:center; gap:1rem; flex-wrap:wrap }
.sk-smiles { font-family:var(--mono); font-size:11.5px; color:#58a6ff;
  background:#161b22; border:1px solid #30363d; border-radius:5px;
  padding:4px 10px; max-width:500px; overflow:hidden; text-overflow:ellipsis;
  white-space:nowrap; }
.sk-match-count { font-size:12px; color:#b1bac4 }
.sk-matches { margin-top:.6rem; overflow-x:auto }
</style>
</head>
<body>
<nav class="topnav">
  <div class="topnav-inner">
    <a class="topnav-brand" href="/">Target<span>Recon</span></a>
    <span style="font-size:13px;color:#768390;margin-left:.5rem">/ Draw Structure</span>
  </div>
</nav>

<div class="sk-wrap">
  <div class="sk-toolbar">
    <button class="btn btn-primary" onclick="searchExact()">🔍 Exact match</button>
    <button class="btn btn-default" onclick="searchSimilar(80)">~ Similarity ≥ 80%</button>
    <button class="btn btn-default" onclick="searchSimilar(70)">~ Similarity ≥ 70%</button>
    <span class="sk-hint" id="skHint">Loading Ketcher…</span>
    <a href="/" class="btn btn-default" style="margin-left:auto">← Back</a>
  </div>

  <iframe id="ketcherFrame" src="/static/ketcher2/index.html"></iframe>

  <div class="sk-result" id="skResult">
    <div class="sk-result-inner">
      <div>
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:3px">SMILES</div>
        <div class="sk-smiles" id="skSmiles"></div>
      </div>
      <span class="sk-match-count" id="skMatchCount"></span>
    </div>
    <div class="sk-matches" id="skMatches"></div>
  </div>
</div>

<script>
// Poll every 200ms until ketcher is available on the iframe window
var _ketcherPoll = setInterval(function() {
  try {
    var frame = document.getElementById('ketcherFrame');
    if (frame && frame.contentWindow && frame.contentWindow.ketcher) {
      clearInterval(_ketcherPoll);
      var hint = document.getElementById('skHint');
      if (hint) hint.textContent = 'Draw a molecule then click a search button';
    }
  } catch(e) { /* ignore cross-origin errors during load */ }
}, 200);

function getKetcher() {
  try {
    var frame = document.getElementById('ketcherFrame');
    return frame && frame.contentWindow && frame.contentWindow.ketcher;
  } catch(e) { return null; }
}

function showResultPanel(msg, isError) {
  var result = document.getElementById('skResult');
  var mc = document.getElementById('skMatchCount');
  var mm = document.getElementById('skMatches');
  if (result) result.style.display = 'block';
  if (mc) { mc.textContent = msg; mc.style.color = isError ? '#f85149' : '#b1bac4'; }
  if (mm && isError) mm.innerHTML = '';
}

function withTimeout(promise, ms, msg) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error(msg || 'Timed out')), ms))
  ]);
}

async function getMoleculeSmiles() {
  var hint = document.getElementById('skHint');
  var k = getKetcher();
  if (!k) {
    showResultPanel('Ketcher not ready — please wait and try again.', true);
    if (hint) hint.textContent = 'Ketcher not ready yet…';
    return null;
  }
  if (hint) hint.textContent = 'Reading molecule…';
  try {
    // Use getSmiles with timeout; fall back to getMolfile if it fails
    var smiles;
    try {
      smiles = await withTimeout(k.getSmiles(), 6000, 'timeout');
    } catch(e) {
      // getSmiles timed out or failed; try getMolfile as fallback
      try {
        var molfile = await withTimeout(k.getMolfile(), 3000, 'timeout');
        // Send molfile to server to convert to SMILES
        var r = await fetch('/search/molfile_to_smiles', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ molfile: molfile })
        });
        var d = await r.json();
        smiles = d.smiles || null;
      } catch(e2) {
        showResultPanel('Could not read molecule: ' + e.message, true);
        if (hint) hint.textContent = 'Error — try again';
        return null;
      }
    }
    if (hint) hint.textContent = 'Draw a molecule then click a search button';
    return smiles;
  } catch(e) {
    showResultPanel('Could not read molecule: ' + e.message, true);
    if (hint) hint.textContent = 'Error — try again';
    return null;
  }
}

async function searchExact() {
  var smiles = await getMoleculeSmiles();
  if (smiles == null) return;
  if (!smiles || smiles.trim() === '') { showResultPanel('Please draw a molecule first.', true); return; }
  document.getElementById('skSmiles').textContent = smiles;
  showResultPanel('Searching…', false);
  document.getElementById('skMatches').innerHTML = '';
  try {
    const resp = await fetch('/search/smiles', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ smiles: smiles, mode: 'exact' })
    });
    const data = await resp.json();
    renderResults(data);
  } catch(e) {
    showResultPanel('Search failed: ' + e.message, true);
  }
}

async function searchSimilar(threshold) {
  var smiles = await getMoleculeSmiles();
  if (smiles == null) return;
  if (!smiles || smiles.trim() === '') { showResultPanel('Please draw a molecule first.', true); return; }
  document.getElementById('skSmiles').textContent = smiles;
  showResultPanel('Searching…', false);
  document.getElementById('skMatches').innerHTML = '';
  try {
    const resp = await fetch('/search/smiles', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ smiles: smiles, mode: 'similarity', threshold: threshold })
    });
    const data = await resp.json();
    renderResults(data);
  } catch(e) {
    showResultPanel('Search failed: ' + e.message, true);
  }
}

function renderResults(data) {
  var mc = document.getElementById('skMatchCount');
  var mm = document.getElementById('skMatches');

  if (data.error) {
    mc.textContent = 'Error: ' + data.error;
    mc.style.color = '#f85149';
    return;
  }

  var hits = data.hits || [];
  mc.style.color = '#b1bac4';
  if (!hits.length) {
    mc.textContent = 'No matches found in ChEMBL.';
    return;
  }
  mc.textContent = hits.length + ' match' + (hits.length > 1 ? 'es' : '') + ' found';

  var rows = hits.map((h, i) =>
    '<tr>' +
    '<td class="mono" style="font-size:11.5px"><a href="https://www.ebi.ac.uk/chembl/compound_report_card/' + h.chembl_id + '" target="_blank" style="color:#58a6ff">' + h.chembl_id + '</a></td>' +
    '<td style="font-size:13px;color:#e6edf3">' + (h.name || '—') + '</td>' +
    '<td class="r mono" style="font-size:11.5px;color:#b1bac4">' + (h.similarity != null ? (h.similarity * 100).toFixed(0) + '%' : '—') + '</td>' +
    '<td style="text-align:right"><button class="btn btn-primary" data-cid="' + h.chembl_id + '" data-idx="' + i + '" style="font-size:12px;padding:.3rem .8rem" onclick="findTargets(this)">Find targets →</button></td>' +
    '</tr>'
  ).join('');

  mm.innerHTML = '<table class="data-table" style="width:100%;margin-top:.5rem">' +
    '<thead><tr><th>ChEMBL ID</th><th>Name</th><th class="r">Similarity</th><th></th></tr></thead>' +
    '<tbody>' + rows + '</tbody></table>' +
    '<div id="targetResults" style="margin-top:1rem"></div>';
}

function findTargets(btn) {
  var chemblId = btn.getAttribute('data-cid');
  btn.disabled = true;
  btn.innerHTML = '<span class="spin" style="width:11px;height:11px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:4px"></span>Loading\u2026';
  fetch('/disambiguate/run?q=' + encodeURIComponent(chemblId))
    .then(function(r){ return r.text(); })
    .then(function(html){
      if(window.navTo)window.navTo(html);
      else{document.open();document.write(html);document.close();}
    })
    .catch(function(e){
      btn.disabled = false;
      btn.innerHTML = 'Find targets \u2192';
      alert('Failed: ' + e.message);
    });
}
</script>
</body>
</html>
"""

def _max_bio_to_limit(max_bio: int):
    """Convert UI max_bio integer to recon_async limit (None = unlimited)."""
    return None if max_bio >= 10000 else max_bio


# ── Shared report render helper ───────────────────────────────────────────
def _render_report(report, q, max_res=4.0, min_pc=0.0, use_chembl=True, use_bindingdb=True, max_bio=1000):
    u    = report.uniprot
    gene = (u.gene_name if u else None) or q

    af_url = ""
    if report.alphafold and u:
        af_url = (report.alphafold.pdb_url or
                  f"https://alphafold.ebi.ac.uk/files/AF-{u.uniprot_id}-F1-model_v4.pdb")

    go_by_cat: dict = {}
    if u:
        for go in u.go_terms:
            go_by_cat.setdefault(go.category, []).append(go.term)

    pchembl_vals = [r.pchembl_value for r in report.bioactivities if r.pchembl_value]
    method_counts: dict = {}
    for s in report.pdb_structures:
        method_counts[s.method.value] = method_counts.get(s.method.value, 0) + 1
    source_counts: dict = {}
    for r in report.bioactivities:
        source_counts[r.source] = source_counts.get(r.source, 0) + 1
    atype_counts: dict = {}
    for r in report.bioactivities:
        if r.activity_type:
            atype_counts[r.activity_type] = atype_counts.get(r.activity_type, 0) + 1
    atype_top = dict(sorted(atype_counts.items(), key=lambda x: -x[1])[:5])

    return render_template_string(
        REPORT_HTML,
        report=report,
        u=u,
        gene=gene,
        query=q,
        go_by_cat=go_by_cat,
        af_url=af_url,
        af_url_json=json.dumps(af_url),
        pchembl_json=json.dumps(pchembl_vals[:3000]),
        method_json=json.dumps(method_counts),
        query_json=json.dumps(q),
        source_counts=source_counts,
        atype_top=atype_top,
        has_sdf=bool(report.ligand_summary),
        max_res=max_res,
        min_pc=min_pc,
        max_bio=max_bio,
        use_chembl=use_chembl,
        use_bindingdb=use_bindingdb,
        interactions_json=json.dumps([i.model_dump() for i in report.interactions]),
        gene_json=json.dumps(gene),
        chat_panel=_CHAT_PANEL_HTML,
        version=_version,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Routes
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template_string(INDEX_HTML, chat_panel=_CHAT_PANEL_HTML, version=_version)


@app.route("/disambiguate/run")
def disambiguate_run():
    """Like /disambiguate but always returns HTML — never redirects to loading screen."""
    q = request.args.get("q", "").strip().upper()
    if not q:
        return redirect(url_for("index"))

    max_res = float(request.args.get("max_res", 4.0))
    min_pc  = float(request.args.get("min_pc", 0.0))
    max_bio = int(request.args.get("max_bio", 1000))

    from targetrecon.resolver import classify_query, QueryType, fetch_compound_targets

    qtype = classify_query(q)

    if qtype == QueryType.CHEMBL:
        import httpx
        try:
            resp = httpx.get(
                f"https://www.ebi.ac.uk/chembl/api/data/target/{q}.json",
                timeout=10, follow_redirects=True,
            )
            tdata = resp.json() if resp.status_code == 200 else {}
        except Exception:
            tdata = {}

        is_molecule = not any(
            xref.get("xref_src_db") in ("UniProt", "UniProtKB")
            for comp in tdata.get("target_components", [])
            for xref in comp.get("target_component_xrefs", [])
        )

        if not is_molecule:
            # It's a target — run recon directly
            from targetrecon.core import recon_async
            try:
                report = asyncio.run(recon_async(q, max_pdb_resolution=max_res,
                    max_bioactivities=_max_bio_to_limit(max_bio),
                    min_pchembl=min_pc if min_pc > 0 else None, verbose=False))
            except Exception as exc:
                return f"<html><body><p>Error: {exc}</p></body></html>", 500
            sid = request.args.get("sid", "").strip()
            _session_reports(sid)[q.upper()] = report
            return _render_report(report, q, max_res=max_res, min_pc=min_pc, max_bio=max_bio)

        # It's a compound — show target selection table
        targets = asyncio.run(fetch_compound_targets(q, limit=20))
        targets = [t for t in targets if t.uniprot_id]
        if not targets:
            return render_template_string("""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>No targets found</title>
<link rel="stylesheet" href="/static/style.css"></head><body>
<div class="error-box" style="margin-top:4rem">
  <h2>No protein targets found</h2>
  <p><strong>{{ q }}</strong> is a compound but no protein targets with UniProt IDs were found in ChEMBL.</p>
  <a href="/" class="btn btn-default" style="display:inline-block;margin-top:1rem">← Back to search</a>
</div></body></html>""", q=q)

        return render_template_string(DISAMBIG_HTML,
            compound_id=q, targets=targets,
            max_res=str(max_res), min_pc=str(min_pc), max_bio=str(max_bio))

    # Not a CHEMBL query — run recon directly
    from targetrecon.core import recon_async
    try:
        report = asyncio.run(recon_async(q, max_pdb_resolution=max_res,
            max_bioactivities=_max_bio_to_limit(max_bio),
            min_pchembl=min_pc if min_pc > 0 else None, verbose=False))
    except Exception as exc:
        return f"<html><body><p>Error: {exc}</p></body></html>", 500
    sid = request.args.get("sid", "").strip()
    _session_reports(sid)[q.upper()] = report
    return _render_report(report, q, max_res=max_res, min_pc=min_pc, max_bio=max_bio)


@app.route("/disambiguate")
def disambiguate_page():
    q = request.args.get("q", "").strip().upper()
    if not q:
        return redirect(url_for("index"))

    max_res = request.args.get("max_res", "4.0")
    min_pc  = request.args.get("min_pc",  "0")

    from targetrecon.resolver import classify_query, QueryType, fetch_compound_targets

    qtype = classify_query(q)

    # Check if it's actually a target (has UniProt xref) — if so, skip disambiguation
    if qtype == QueryType.CHEMBL:
        # Detect molecule vs target: targets have UniProt xrefs on the target endpoint
        import httpx
        try:
            resp = httpx.get(
                f"https://www.ebi.ac.uk/chembl/api/data/target/{q}.json",
                timeout=10, follow_redirects=True,
            )
            tdata = resp.json() if resp.status_code == 200 else {}
        except Exception:
            tdata = {}

        is_molecule = not any(
            xref.get("xref_src_db") in ("UniProt", "UniProtKB")
            for comp in tdata.get("target_components", [])
            for xref in comp.get("target_component_xrefs", [])
        )

        if not is_molecule:
            # It's a proper target — go straight to recon
            return redirect(url_for(
                "recon_page", q=q,
                max_res=max_res, min_pc=min_pc,
            ))

        # It's a compound — fetch all targets (only keep ones with a UniProt ID)
        targets = asyncio.run(fetch_compound_targets(q, limit=20))
        targets = [t for t in targets if t.uniprot_id]
        if not targets:
            return redirect(url_for(
                "recon_page", q=q,
                max_res=max_res, min_pc=min_pc,
            ))

        return render_template_string(DISAMBIG_HTML,
            compound_id=q,
            targets=targets,
            max_res=max_res, min_pc=min_pc,
        )

    # Not a CHEMBL query — go straight to recon
    return redirect(url_for("recon_page", q=q,
        max_res=max_res, min_pc=min_pc))


@app.route("/recon")
def recon_page():
    """Show loading screen immediately, then meta-refresh to /recon/run."""
    q = request.args.get("q", "").strip()
    if not q:
        return redirect(url_for("index"))

    max_res = float(request.args.get("max_res", 4.0))
    min_pc  = float(request.args.get("min_pc", 0.0))
    max_bio = int(request.args.get("max_bio", 1000))
    use_chembl    = request.args.get("use_chembl", "1") == "1"
    use_bindingdb = request.args.get("use_bindingdb", "1") == "1"

    return render_template_string(LOADING_HTML, q=q,
        max_res=max_res, min_pc=min_pc, max_bio=max_bio,
        use_chembl="1" if use_chembl else "0",
        use_bindingdb="1" if use_bindingdb else "0",
    )


@app.route("/recon/run")
def recon_run():
    """Do the actual work after the loading screen."""
    q = request.args.get("q", "").strip()
    if not q:
        return redirect(url_for("index"))

    max_res = float(request.args.get("max_res", 4.0))
    min_pc  = float(request.args.get("min_pc", 0.0))
    max_bio = int(request.args.get("max_bio", 1000))
    use_chembl    = request.args.get("use_chembl", "1") == "1"
    use_bindingdb = request.args.get("use_bindingdb", "1") == "1"

    # If the query is a CHEMBL ID it could be a compound — disambiguate first
    from targetrecon.resolver import classify_query, QueryType
    if classify_query(q) == QueryType.CHEMBL:
        return redirect(url_for(
            "disambiguate_page", q=q.upper(),
            max_res=max_res, min_pc=min_pc, max_bio=max_bio,
        ))

    # Check session cache first (agent may have already run this query)
    sid = request.args.get("sid", "").strip()
    cached = _session_reports(sid).get(q.upper())
    if cached:
        return _render_report(cached, q, max_res=max_res, min_pc=min_pc, max_bio=max_bio,
                              use_chembl=use_chembl, use_bindingdb=use_bindingdb)

    # Run recon
    from targetrecon.core import recon_async
    try:
        report = asyncio.run(recon_async(
            q,
            max_pdb_resolution=max_res,
            max_bioactivities=_max_bio_to_limit(max_bio),
            min_pchembl=min_pc if min_pc > 0 else None,
            use_chembl=use_chembl,
            use_bindingdb=use_bindingdb,
            verbose=False,
        ))
    except Exception as exc:
        return render_template_string("""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Error</title>
<link rel="stylesheet" href="/static/style.css"></head><body>
<div class="error-box" style="margin-top:4rem">
  <h2>Something went wrong</h2><p>{{ err }}</p>
  <a href="/" class="btn btn-default" style="display:inline-block;margin-top:1rem">← Back</a>
</div></body></html>""", err=str(exc)), 500

    if report.uniprot is None:
        return render_template_string("""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Not found</title>
<link rel="stylesheet" href="/static/style.css"></head><body>
<div class="error-box" style="margin-top:4rem">
  <h2>Target not found</h2>
  <p>Could not resolve <strong>{{ q }}</strong> to a protein target.</p>
  <p style="font-size:13px;color:#b1bac4;margin-top:.5rem">
    {% if q.startswith('CHEMBL') %}
    This looks like a <strong>compound</strong> ChEMBL ID (molecule), not a target ID.
    Target IDs look like <code>CHEMBL203</code> (EGFR), <code>CHEMBL897</code> (BRAF), <code>CHEMBL301</code> (CDK2).<br>
    Search by gene name instead: <strong>EGFR</strong>, <strong>BRAF</strong>, <strong>CDK2</strong>.
    {% else %}
    Try a gene name (EGFR, BRAF, CDK2), a UniProt accession (P00533), or a ChEMBL target ID (CHEMBL203).
    {% endif %}
  </p>
  <a href="/" class="btn btn-default" style="display:inline-block;margin-top:1rem">← Back</a>
</div></body></html>""", q=q), 404

    # Cache report per-session for exports
    _session_reports(sid)[q.upper()] = report

    return _render_report(report, q, max_res=max_res, min_pc=min_pc, max_bio=max_bio,
                          use_chembl=use_chembl, use_bindingdb=use_bindingdb)


# ── Export routes ──────────────────────────────────────────────────────────
# ── Per-user session cache ─────────────────────────────────────────────────
import threading as _thr
import time as _ti
import uuid as _uuidmod

_SESSION_TTL = 1800  # 30 min inactivity → auto-cleanup
_sessions: dict[str, dict] = {}
_sessions_lock = _thr.Lock()


def _session_reports(sid: str) -> dict:
    """Return (and touch) the report cache dict for this session."""
    with _sessions_lock:
        if sid not in _sessions:
            _sessions[sid] = {"reports": {}, "ts": _ti.time()}
        else:
            _sessions[sid]["ts"] = _ti.time()
        return _sessions[sid]["reports"]


def _start_session_cleanup() -> None:
    def _loop() -> None:
        while True:
            _ti.sleep(300)
            now = _ti.time()
            with _sessions_lock:
                expired = [s for s, d in list(_sessions.items()) if now - d["ts"] > _SESSION_TTL]
                for s in expired:
                    _sessions.pop(s, None)
            # Also clean up any script output dirs for expired sessions
            from targetrecon.agent_chat import cleanup_session_workdir
            for s in expired:
                cleanup_session_workdir(s)
    _thr.Thread(target=_loop, daemon=True).start()


_start_session_cleanup()


@app.route("/api/boot_id")
def boot_id():
    return jsonify({"boot_id": _BOOT_ID})


@app.route("/api/session", methods=["POST"])
def create_session():
    sid = str(_uuidmod.uuid4())
    with _sessions_lock:
        _sessions[sid] = {"reports": {}, "ts": _ti.time()}
    return jsonify({"session_id": sid})


@app.route("/sketcher")
def sketcher_page():
    return render_template_string(SKETCHER_HTML)


@app.route("/api/compound_targets")
def api_compound_targets():
    q = request.args.get("q", "").strip().upper()
    if not q:
        return jsonify({"error": "No ChEMBL ID provided"}), 400
    from targetrecon.resolver import fetch_compound_targets
    try:
        targets = asyncio.run(fetch_compound_targets(q, limit=20))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    import dataclasses
    return jsonify({"targets": [dataclasses.asdict(t) for t in targets]})


@app.route("/search/smiles", methods=["POST"])
def search_smiles():
    data = request.get_json(force=True)
    smiles   = (data.get("smiles") or "").strip()
    mode     = data.get("mode", "exact")       # "exact" or "similarity"
    threshold = int(data.get("threshold", 80)) # for similarity

    if not smiles:
        return jsonify({"error": "No SMILES provided"}), 400

    import urllib.parse
    import httpx

    # Canonicalize SMILES with RDKit so ChEMBL API can parse it reliably
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol is not None:
            smiles = Chem.MolToSmiles(mol)
    except Exception:
        pass  # Use original SMILES if RDKit unavailable

    encoded = urllib.parse.quote(smiles, safe="")
    hits = []

    try:
        if mode == "exact":
            url = f"https://www.ebi.ac.uk/chembl/api/data/molecule.json?smiles={encoded}&limit=10"
            resp = httpx.get(url, timeout=20, follow_redirects=True)
            resp.raise_for_status()
            molecules = resp.json().get("molecules", [])
            for m in molecules:
                hits.append({
                    "chembl_id": m.get("molecule_chembl_id"),
                    "name": m.get("pref_name"),
                    "similarity": 1.0,
                })
        else:
            url = f"https://www.ebi.ac.uk/chembl/api/data/similarity/{encoded}/{threshold}.json?limit=20"
            resp = httpx.get(url, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            molecules = resp.json().get("molecules", [])
            for m in molecules:
                raw_sim = m.get("similarity")
                # ChEMBL returns similarity on 0-100 scale (sometimes as string); normalise to 0-1
                try:
                    sim = float(raw_sim) / 100.0 if raw_sim is not None else None
                except (TypeError, ValueError):
                    sim = None
                hits.append({
                    "chembl_id": m.get("molecule_chembl_id"),
                    "name": m.get("pref_name"),
                    "similarity": sim,
                })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify({"hits": hits})


@app.route("/search/molfile_to_smiles", methods=["POST"])
def molfile_to_smiles():
    """Convert a molfile to SMILES using RDKit (fallback when Ketcher getSmiles hangs)."""
    data = request.get_json(force=True)
    molfile = (data.get("molfile") or "").strip()
    if not molfile:
        return jsonify({"error": "No molfile provided"}), 400
    try:
        from rdkit import Chem
        mol = Chem.MolFromMolBlock(molfile, sanitize=True)
        if mol is None:
            return jsonify({"error": "Could not parse molfile"}), 400
        smiles = Chem.MolToSmiles(mol)
        return jsonify({"smiles": smiles})
    except ImportError:
        return jsonify({"error": "RDKit not available"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/export/json")
def export_json():
    q = request.args.get("q","").strip().upper()
    sid = request.args.get("sid", "").strip()
    report = _session_reports(sid).get(q)
    if not report:
        return "Run a search first", 400
    from flask import Response
    gene = (report.uniprot.gene_name if report.uniprot else q) or q
    return Response(
        report.model_dump_json(indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment;filename="{gene}_report.json"'},
    )

@app.route("/export/html")
def export_html_route():
    q = request.args.get("q","").strip().upper()
    sid = request.args.get("sid", "").strip()
    report = _session_reports(sid).get(q)
    if not report:
        return "Run a search first", 400
    from flask import Response
    from targetrecon.report import render_html
    gene = (report.uniprot.gene_name if report.uniprot else q) or q
    return Response(
        render_html(report),
        mimetype="text/html",
        headers={"Content-Disposition": f'attachment;filename="{gene}_report.html"'},
    )

@app.route("/export/sdf")
def export_sdf_route():
    import tempfile
    q           = request.args.get("q", "").strip().upper()
    min_pc      = request.args.get("min_pc", "")
    max_nm      = request.args.get("max_nm", "")
    atype       = request.args.get("atype", "").strip()
    top_n       = request.args.get("top_n", "")
    sid         = request.args.get("sid", "").strip()

    report = _session_reports(sid).get(q)
    if not report:
        return "Run a search first", 400

    from flask import Response
    from targetrecon.core import save_sdf

    gene = (report.uniprot.gene_name if report.uniprot else q) or q

    kwargs = {}
    try: kwargs["min_pchembl"]  = float(min_pc) if min_pc else None
    except ValueError: pass
    try: kwargs["max_nm"]       = float(max_nm) if max_nm else None
    except ValueError: pass
    if atype:
        kwargs["activity_type"] = atype
    try: kwargs["top_n"]        = int(top_n) if top_n else 0
    except ValueError: pass

    with tempfile.NamedTemporaryFile(suffix=".sdf", delete=False) as tmp:
        save_sdf(report, tmp.name, **kwargs)
        sdf_bytes = Path(tmp.name).read_bytes()

    # Build descriptive filename
    parts = [gene, "ligands"]
    if kwargs.get("min_pchembl"):   parts.append(f"pc{kwargs['min_pchembl']}")
    if kwargs.get("max_nm"):        parts.append(f"nm{kwargs['max_nm']}")
    if kwargs.get("activity_type"): parts.append(kwargs["activity_type"])
    fname = "_".join(parts) + ".sdf"

    return Response(
        sdf_bytes,
        mimetype="chemical/x-mdl-sdfile",
        headers={"Content-Disposition": f'attachment;filename="{fname}"'},
    )


# ── AI endpoint ────────────────────────────────────────────────────────────
# ── AI Agent streaming routes ─────────────────────────────────────────────
@app.route("/agent/chat/stream", methods=["POST"])
def agent_chat_stream():
    from flask import Response, stream_with_context
    from targetrecon.agent_chat import sse_generator

    data = request.get_json(force=True) or {}
    message = (data.get("message") or "").strip()
    conv_id = (data.get("conv_id") or "default").strip()
    context_query = (data.get("context_query") or "").strip().upper() or None
    provider = (data.get("provider") or "anthropic").strip().lower()
    model = (data.get("model") or "claude-sonnet-4-6").strip()
    api_key = (data.get("api_key") or "").strip()

    if not message:
        return jsonify({"error": "Empty message"}), 400

    if not api_key:
        err_event = 'data: {"type":"error","message":"No API key provided. Enter your key in the settings panel."}\n\n'
        return Response(err_event, mimetype="text/event-stream")

    sid = data.get("session_id", "").strip()

    def _gen():
        yield from sse_generator(message, conv_id, context_query, _session_reports(sid), provider, model, api_key, sid)

    return Response(
        stream_with_context(_gen()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.route("/agent/chat/new", methods=["POST"])
def agent_chat_new():
    import uuid
    from targetrecon.agent_chat import clear_conversation
    data = request.get_json(force=True) or {}
    old_id = data.get("conv_id")
    if old_id:
        clear_conversation(old_id)
    return jsonify({"conv_id": str(uuid.uuid4())[:8]})


@app.route("/agent/test_key", methods=["POST"])
def agent_test_key():
    """Send a tiny ping to the chosen provider to verify the API key."""
    data = request.get_json(force=True) or {}
    provider = (data.get("provider") or "anthropic").strip().lower()
    model    = (data.get("model") or "").strip()
    api_key  = (data.get("api_key") or "").strip()

    if not api_key:
        return jsonify({"ok": False, "error": "No API key provided"})

    try:
        if provider == "anthropic":
            import anthropic as _ant
            client = _ant.Anthropic(api_key=api_key)
            client.messages.create(
                model=model or "claude-haiku-4-5-20251001",
                max_tokens=5,
                messages=[{"role": "user", "content": "hi"}],
            )
        elif provider == "openai":
            import openai as _oai
            client = _oai.OpenAI(api_key=api_key)
            client.chat.completions.create(
                model=model or "gpt-4o-mini",
                max_tokens=5,
                messages=[{"role": "user", "content": "hi"}],
            )
        elif provider == "groq":
            import groq as _groq
            client = _groq.Groq(api_key=api_key)
            client.chat.completions.create(
                model=model or "llama-3.1-8b-instant",
                max_tokens=5,
                messages=[{"role": "user", "content": "hi"}],
            )
        else:
            return jsonify({"ok": False, "error": f"Unknown provider: {provider}"})
        return jsonify({"ok": True})
    except Exception as exc:
        msg = str(exc)
        # extract clean message from SDK errors
        if "message" in msg.lower():
            import re as _re
            m = _re.search(r"'message':\s*'([^']+)'", msg)
            if m:
                msg = m.group(1)
        return jsonify({"ok": False, "error": msg})


@app.route("/agent/cache/status")
def agent_cache_status():
    sid = request.args.get("sid", "").strip()
    cached = []
    for key, report in _session_reports(sid).items():
        if report and report.uniprot:
            cached.append({"key": key, "gene": report.uniprot.gene_name, "uniprot": report.uniprot.uniprot_id})
    return jsonify({"cached": cached})


@app.route("/agent/files/<sid>/<filename>")
def agent_file(sid: str, filename: str):
    """Serve a script output file from the user's session working directory."""
    import re
    from flask import send_from_directory
    from targetrecon.agent_chat import get_session_workdir
    # Basic safety: no path traversal
    if not re.match(r'^[\w\-. ]+$', filename):
        return "Invalid filename", 400
    workdir = get_session_workdir(sid)
    filepath = workdir / filename
    if not filepath.exists():
        return "File not found", 404
    ext = Path(filename).suffix.lower()
    image_exts = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"}
    as_attachment = ext not in image_exts
    return send_from_directory(str(workdir), filename, as_attachment=as_attachment)


# ── Jinja filter ──────────────────────────────────────────────────────────
@app.template_filter("format_int")
def format_int(val):
    try:
        return f"{int(val):,}"
    except Exception:
        return str(val)


def run(host="0.0.0.0", port=5000, debug=False):
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    run(debug=True)
