
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
const root=document.documentElement, shell=$('#doomShell'), stateLabel=$('#stateLabel'), stateDot=$('#stateDot'), engineValue=$('#engineValue'), modeNote=$('#modeNote');
const key=$('#key'), input=$('#input'), msgs=$('#messages'), form=$('#form'), send=$('#send');
key.value=localStorage.getItem('doom_key')||'';
function setTheme(theme){root.dataset.theme=theme;localStorage.setItem('doom_theme',theme);$('#themeBtn').textContent=theme==='dark'?'☼':'◐';}
setTheme(localStorage.getItem('doom_theme')||'dark');
$('#themeBtn').onclick=()=>setTheme(root.dataset.theme==='dark'?'light':'dark');
function setState(name){const s=window.DOOM_CODEX[name]||window.DOOM_CODEX.online;Object.values(window.DOOM_CODEX).forEach(x=>shell.classList.remove(x.className));shell.classList.add(s.className);stateLabel.textContent=s.label;$('#systemState').textContent=s.label;stateDot.className='doom-dot';modeNote.textContent=s.label;document.querySelectorAll('.doom-rune').forEach((el,i)=>el.classList.toggle('active',i+1===s.rune));}
function inferLocalState(text){const t=(text||'').toLowerCase();if(/(erro|falha|não funciona|problema)/.test(t))return'error';if(/(quem sou eu|o que você sabe sobre mim|o que sabe sobre mim|memória|lembra|lembrar|esquecer)/.test(t))return'memory';if(/(estud|aprender|exercício|matemática|enem|aula)/.test(t))return'study';if(/(analise|análise|possibil|compare|cenário|hipótese)/.test(t))return'analysis';if(/(crie|criar|escreva|desenhe|ideia|projeto)/.test(t))return'creation';if(/(execute|executar|abra|rodar|rode|faça isso)/.test(t))return'execution';if(/(talvez|especul|e se|hipotetic)/.test(t))return'speculation';return'thinking';}
function addMessage(role,text){if(msgs.querySelector('.doom-empty'))msgs.innerHTML='';const row=document.createElement('div');row.className=`doom-msg ${role}`;const bubble=document.createElement('div');bubble.className='doom-bubble';bubble.textContent=text;row.appendChild(bubble);msgs.appendChild(row);msgs.scrollTop=msgs.scrollHeight;}
$('#saveKey').onclick=()=>{localStorage.setItem('doom_key',key.value.trim());setState('success');setTimeout(()=>setState('online'),900);};
async function health(){try{const r=await fetch('/health');const d=await r.json();engineValue.textContent=`${d.name} v${d.version}`;$('#linkValue').textContent='ONLINE';setState('online');}catch{engineValue.textContent='indisponível';$('#linkValue').textContent='OFFLINE';setState('offline');}}
form.onsubmit=async e=>{e.preventDefault();const text=input.value.trim();if(!text)return;if(!key.value.trim())return alert('Digite sua Chave Doom primeiro.');addMessage('user',text);input.value='';send.disabled=true;setState(inferLocalState(text));try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Doom-Key':key.value.trim()},body:JSON.stringify({session_id:'main',message:text})});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Erro');addMessage('doom',d.reply);setState(d.mode||'success');setTimeout(()=>setState('online'),1700);}catch(err){addMessage('doom','Não consegui concluir a solicitação: '+err.message);setState('error');}finally{send.disabled=false;input.focus();}};
health();
