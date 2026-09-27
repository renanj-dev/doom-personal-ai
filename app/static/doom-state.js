// Doom Memory Engine v1.1 — conversation history
const DOOM_MEMORY_ENGINE = { version: '1.1.0' };


window.DOOM_CODEX={
 online:{label:'ONLINE',className:'state-online',rune:11},
 thinking:{label:'ANALISANDO',className:'state-thinking',rune:2},
 error:{label:'ERRO',className:'state-error',rune:3},
 success:{label:'SUCESSO',className:'state-success',rune:4},
 warning:{label:'AVISO',className:'state-warning',rune:5},
 info:{label:'INFO',className:'state-info',rune:6},
 analysis:{label:'ANÁLISE / POSSIBILIDADES',className:'state-analysis',rune:7},
 creation:{label:'CRIAÇÃO',className:'state-creation',rune:8},
 execution:{label:'EXECUÇÃO',className:'state-execution',rune:9},
 memory:{label:'MEMÓRIA',className:'state-memory',rune:10},
 study:{label:'ESTUDO',className:'state-study',rune:11},
 offline:{label:'OFFLINE',className:'state-offline',rune:12},
 speculation:{label:'ESPECULAÇÃO',className:'state-speculation',rune:13}
};

const $=s=>document.querySelector(s);
const root=document.documentElement, shell=$('#doomShell'), stateLabel=$('#stateLabel'), stateDot=$('#stateDot'), engineValue=$('#engineValue'), engineNote=$('#engineNote'), modeNote=$('#modeNote');
const key=$('#key'), input=$('#input'), msgs=$('#messages'), form=$('#form'), send=$('#send');
key.value=localStorage.getItem('doom_key')||'';
function setTheme(theme){root.dataset.theme=theme;localStorage.setItem('doom_theme',theme);$('#themeBtn').textContent=theme==='dark'?'☼':'◐';}
setTheme(localStorage.getItem('doom_theme')||'dark');
$('#themeBtn').onclick=()=>setTheme(root.dataset.theme==='dark'?'light':'dark');
function setState(name){const s=window.DOOM_CODEX[name]||window.DOOM_CODEX.online;Object.values(window.DOOM_CODEX).forEach(x=>shell.classList.remove(x.className));shell.classList.add(s.className);stateLabel.textContent=s.label;$('#systemState').textContent=s.label;stateDot.className='doom-dot';modeNote.textContent=s.label;document.querySelectorAll('.doom-rune').forEach((el,i)=>el.classList.toggle('active',i+1===s.rune));}
function inferLocalState(text){const t=(text||'').toLowerCase();if(/(erro|falha|não funciona|problema)/.test(t))return'error';if(/(quem sou eu|o que você sabe sobre mim|o que sabe sobre mim|memória|lembra|lembrar|esquecer)/.test(t))return'memory';if(/(estud|aprender|exercício|matemática|enem|aula)/.test(t))return'study';if(/(analise|análise|possibil|compare|cenário|hipótese)/.test(t))return'analysis';if(/(crie|criar|escreva|desenhe|ideia|projeto)/.test(t))return'creation';if(/(execute|executar|abra|rodar|rode|faça isso)/.test(t))return'execution';if(/(talvez|especul|e se|hipotetic)/.test(t))return'speculation';return'thinking';}
function addMessage(role,text){if(msgs.querySelector('.doom-empty'))msgs.innerHTML='';const row=document.createElement('div');row.className=`doom-msg ${role}`;const bubble=document.createElement('div');bubble.className='doom-bubble';bubble.textContent=text;row.appendChild(bubble);msgs.appendChild(row);msgs.scrollTop=msgs.scrollHeight;}
$('#saveKey').onclick=()=>{localStorage.setItem('doom_key',key.value.trim());refreshHistory();setState('success');setTimeout(()=>setState('online'),900);};
async function health(){try{const r=await fetch('/health');const d=await r.json();engineValue.textContent='CORTEX';engineNote&&(engineNote.textContent=`${d.name} v${d.version}`);$('#linkValue').textContent='ONLINE';setState('online');}catch{engineValue.textContent='indisponível';$('#linkValue').textContent='OFFLINE';setState('offline');}}
form.onsubmit=async e=>{e.preventDefault();const text=input.value.trim();if(!text)return;if(!key.value.trim())return alert('Digite sua Chave Doom primeiro.');addMessage('user',text);input.value='';send.disabled=true;setState(inferLocalState(text));try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Doom-Key':key.value.trim()},body:JSON.stringify({session_id:currentSessionId(),message:text})});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Erro');addMessage('doom',d.reply);if(engineValue)engineValue.textContent=d.brain?d.brain.toUpperCase():'CORTEX';if(engineNote)engineNote.textContent=d.model?(d.model+(d.fallback_count?` · fallback ${d.fallback_count}`:'')):'Roteamento automático.';setState(d.mode||'success');refreshHistory();setTimeout(()=>setState('online'),1700);}catch(err){addMessage('doom','Não consegui concluir a solicitação: '+err.message);setState('error');}finally{send.disabled=false;input.focus();}};

function currentSessionId(){let sid=localStorage.getItem('doom_session_id');if(!sid){sid='main';localStorage.setItem('doom_session_id',sid);}return sid;}
function openHistory(){const d=$('#historyDrawer');const b=$('#historyBackdrop');if(!d||!b)return;d.classList.add('open');b.classList.add('open');d.setAttribute('aria-hidden','false');refreshHistory();}
function closeHistory(){const d=$('#historyDrawer');const b=$('#historyBackdrop');if(!d||!b)return;d.classList.remove('open');b.classList.remove('open');d.setAttribute('aria-hidden','true');}
function formatHistoryDate(iso){try{return new Intl.DateTimeFormat('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(iso));}catch{return ''}}
function renderHistory(items){const list=$('#historyList');if(!list)return;$('#historyCount').textContent=`${items.length} ${items.length===1?'conversa':'conversas'}`;if(!items.length){list.innerHTML='<div class="doom-history-empty">Nenhuma conversa registrada ainda.<br>Inicie uma nova conversa para construir seu histórico.</div>';return;}list.innerHTML=items.map(x=>`<button class="doom-history-item ${x.session_id===currentSessionId()?'active':''}" data-session="${x.session_id}"><div class="doom-history-title">${escapeHtml(x.title)}</div><div class="doom-history-meta"><span>${x.message_count} mensagens</span><span>${formatHistoryDate(x.updated_at)}</span></div></button>`).join('');list.querySelectorAll('.doom-history-item').forEach(el=>el.onclick=()=>loadConversation(el.dataset.session));}
function escapeHtml(s){return String(s).replace(/[&<>'"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','\'':'&#39;','"':'&quot;'}[ch]));}
async function loadCurrentConversation(){const sid=currentSessionId();if(sid&&sid!=='main'){await loadConversation(sid);}}
async function refreshHistory(){const k=key.value.trim();if(!k)return;try{const r=await fetch('/api/conversations',{headers:{'X-Doom-Key':k}});if(!r.ok)throw new Error('Não foi possível carregar o histórico.');renderHistory(await r.json());}catch(e){if($('#historyList'))$('#historyList').innerHTML='<div class="doom-history-empty">Falha ao carregar o histórico.</div>';}}
async function loadConversation(sid){const k=key.value.trim();if(!k)return;try{const r=await fetch(`/api/conversations/${encodeURIComponent(sid)}`,{headers:{'X-Doom-Key':k}});if(!r.ok)throw new Error('Conversa não encontrada.');const d=await r.json();localStorage.setItem('doom_session_id',sid);msgs.innerHTML='';for(const m of d.messages)addMessage(m.role==='assistant'?'doom':m.role,m.content);setState('online');closeHistory();refreshHistory();input.focus();}catch(e){setState('error');addMessage('doom','Não consegui abrir esta conversa: '+e.message);}}
async function newConversation(){const k=key.value.trim();if(!k)return alert('Digite sua Chave Doom primeiro.');try{const r=await fetch('/api/conversations',{method:'POST',headers:{'Content-Type':'application/json','X-Doom-Key':k},body:JSON.stringify({title:'Nova conversa'})});if(!r.ok)throw new Error('Não foi possível criar a conversa.');const d=await r.json();localStorage.setItem('doom_session_id',d.session_id);msgs.innerHTML='<div class="doom-empty"><div><div class="core-symbol">◉</div><strong>Doom está pronta.</strong><span>Nova conversa iniciada.</span></div></div>';setState('success');setTimeout(()=>setState('online'),700);refreshHistory();closeHistory();input.focus();}catch(e){setState('error');addMessage('doom','Não consegui criar uma nova conversa: '+e.message);}}
async function searchHistory(){const k=key.value.trim();const q=($('#historySearch')?.value||'').trim();if(!k||!q){return refreshHistory();}try{const r=await fetch(`/api/history/search?q=${encodeURIComponent(q)}`,{headers:{'X-Doom-Key':k}});if(!r.ok)throw new Error();const rows=await r.json();const grouped={};for(const m of rows){if(!grouped[m.session_id])grouped[m.session_id]={session_id:m.session_id,title:'Conversa '+m.session_id.slice(0,6),updated_at:m.created_at,message_count:0};grouped[m.session_id].message_count++;}renderHistory(Object.values(grouped));}catch{if($('#historyList'))$('#historyList').innerHTML='<div class="doom-history-empty">Falha na busca.</div>';}}
$('#historyBtn')?.addEventListener('click',openHistory);$('#historyClose')?.addEventListener('click',closeHistory);$('#historyBackdrop')?.addEventListener('click',closeHistory);$('#newConversation')?.addEventListener('click',newConversation);$('#historySearch')?.addEventListener('input',()=>{clearTimeout(window.__doomHistoryTimer);window.__doomHistoryTimer=setTimeout(searchHistory,250);});

health().then(loadCurrentConversation);
