from pathlib import Path

ROOT = Path('/mnt/data/doom_v113_work')
APP = ROOT/'app'
STATIC = APP/'static'

# 1) Add multimodal configuration
p = APP/'config.py'
s = p.read_text()
s = s.replace('    google_client_id: str = ""\n\n    # Doom Safety & Legal Engine v1.8', '    google_client_id: str = ""\n\n    # Doom Multimodal v1.13\n    multimodal_enabled: bool = True\n    vision_max_file_mb: int = 10\n    openai_vision_model: str | None = None\n    openrouter_vision_model: str | None = None\n    ollama_vision_model: str | None = None\n\n    # Doom Safety & Legal Engine v1.8')
p.write_text(s)

# 2) Add multimodal service
(APP/'multimodal.py').write_text(r'''"""Doom v1.13 multimodal services: image understanding + provider routing."""
from __future__ import annotations

import base64
import mimetypes
import re
from dataclasses import dataclass

import httpx

from .config import get_settings
from .personality import DOOM_PERSONALITY

settings = get_settings()

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


class VisionError(RuntimeError):
    pass


@dataclass(frozen=True)
class VisionResult:
    reply: str
    provider: str
    model: str


def normalize_mime(mime_type: str, filename: str = "") -> str:
    mime = (mime_type or "").strip().lower()
    if mime in ALLOWED_IMAGE_TYPES:
        return mime
    guessed, _ = mimetypes.guess_type(filename or "")
    if guessed in ALLOWED_IMAGE_TYPES:
        return guessed
    raise VisionError("Formato de imagem não suportado. Use JPG, PNG, WebP ou GIF.")


def validate_image(image_bytes: bytes, mime_type: str, filename: str = "") -> str:
    if not settings.multimodal_enabled:
        raise VisionError("A camada multimodal está desativada no servidor.")
    if not image_bytes:
        raise VisionError("A imagem enviada está vazia.")
    max_bytes = max(1, settings.vision_max_file_mb) * 1024 * 1024
    if len(image_bytes) > max_bytes:
        raise VisionError(f"A imagem excede o limite de {settings.vision_max_file_mb} MB.")
    return normalize_mime(mime_type, filename)


def _clean(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    if not text:
        raise VisionError("O modelo de visão respondeu sem conteúdo.")
    return text


def _prompt(user_prompt: str, context_text: str | None = None, knowledge_text: str | None = None) -> str:
    safe_context = context_text or "Nenhum contexto adicional foi recuperado."
    knowledge = knowledge_text or "Nenhuma fonte de conhecimento foi recuperada."
    return (
        DOOM_PERSONALITY
        + "\n\nMODO MULTIMODAL — VISÃO\n"
        + "Analise somente a imagem enviada e a solicitação atual do usuário. "
          "O contexto abaixo é apenas apoio e nunca substitui a solicitação atual. "
          "Não invente detalhes que não estejam visíveis. Se não puder determinar algo, diga claramente.\n"
        + "\nSOLICITAÇÃO ATUAL:\n" + user_prompt.strip()
        + "\n\nCONTEXTO DE APOIO:\n" + safe_context
        + "\n\nCONHECIMENTO DE APOIO:\n" + knowledge
    )


def _ask_openai(image_data_url: str, prompt: str) -> VisionResult:
    if not settings.openai_api_key:
        raise VisionError("OPENAI_API_KEY não foi configurada.")
    from openai import OpenAI
    model = settings.openai_vision_model or settings.openai_model
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": image_data_url, "detail": "auto"},
                ],
            }
        ],
        store=False,
    )
    return VisionResult(_clean(response.output_text), "openai", model)


def _ask_openrouter(image_data_url: str, prompt: str) -> VisionResult:
    if not settings.openrouter_api_key:
        raise VisionError("OPENROUTER_API_KEY não foi configurada.")
    from openai import OpenAI
    model = settings.openrouter_vision_model or settings.openrouter_model
    headers = {}
    if settings.openrouter_site_url:
        headers["HTTP-Referer"] = settings.openrouter_site_url
    if settings.openrouter_site_name:
        headers["X-Title"] = settings.openrouter_site_name
    client = OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        default_headers=headers or None,
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            }
        ],
    )
    return VisionResult(_clean(response.choices[0].message.content or ""), "openrouter", model)


def _ask_ollama(image_b64: str, prompt: str) -> VisionResult:
    model = settings.ollama_vision_model or settings.ollama_model
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.4},
    }
    try:
        with httpx.Client(timeout=300.0) as client:
            response = client.post(f"{settings.ollama_base_url.rstrip('/')}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        raise VisionError(f"Ollama não conseguiu analisar a imagem: {exc}") from exc
    return VisionResult(_clean(data.get("message", {}).get("content", "")), "ollama", model)


def analyze_image(image_bytes: bytes, mime_type: str, prompt: str, context_text: str | None = None, knowledge_text: str | None = None) -> VisionResult:
    mime = validate_image(image_bytes, mime_type)
    data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    prepared_prompt = _prompt(prompt, context_text=context_text, knowledge_text=knowledge_text)
    selected = settings.provider
    if selected == "openai":
        return _ask_openai(data_url, prepared_prompt)
    if selected == "openrouter":
        return _ask_openrouter(data_url, prepared_prompt)
    if selected == "ollama":
        return _ask_ollama(data_url.split(',', 1)[1], prepared_prompt)
    raise VisionError(f"Provedor desconhecido para visão: {selected}")


def status() -> dict:
    providers = []
    if settings.openai_api_key:
        providers.append({"provider": "openai", "model": settings.openai_vision_model or settings.openai_model})
    if settings.openrouter_api_key:
        providers.append({"provider": "openrouter", "model": settings.openrouter_vision_model or settings.openrouter_model})
    if settings.ollama_base_url:
        providers.append({"provider": "ollama", "model": settings.ollama_vision_model or settings.ollama_model})
    return {
        "enabled": bool(settings.multimodal_enabled),
        "vision": bool(settings.multimodal_enabled),
        "voice_input": True,
        "voice_output": True,
        "max_image_mb": settings.vision_max_file_mb,
        "providers": providers,
    }
''')

# 3) Schemas
p = APP/'schemas.py'
s = p.read_text()
s = s.replace('    knowledge_sources: list[KnowledgeSourceOut] = Field(default_factory=list)\n\n\nclass ChatCancelRequest', '    knowledge_sources: list[KnowledgeSourceOut] = Field(default_factory=list)\n    vision_used: bool = False\n    vision_provider: str | None = None\n    vision_model: str | None = None\n\n\nclass ChatCancelRequest')
p.write_text(s)

# 4) main imports/version/routes
p = APP/'main.py'
s = p.read_text()
s = s.replace('from .knowledge_engine import KNOWLEDGE_ENGINE\n', 'from .knowledge_engine import KNOWLEDGE_ENGINE\nfrom .multimodal import analyze_image, status as multimodal_status, VisionError, validate_image\n')
s = s.replace('app = FastAPI(title="Doom Personal AI", version="1.12.0")', 'app = FastAPI(title="Doom Personal AI", version="1.13.0")')
s = s.replace('    BreakGlassRegisterOut, ChatCancelRequest, ExternalIntegrationCreate', '    BreakGlassRegisterOut, ChatCancelRequest, ExternalIntegrationCreate')
# add route before /api/cortex
needle='@app.get("/api/cortex", dependencies=[Depends(auth)])\ndef cortex_status() -> dict:\n'
route='''@app.get("/api/multimodal/status", dependencies=[Depends(auth)])\ndef multimodal_status() -> dict:\n    return multimodal_status()\n\n\n@app.post("/api/chat/vision", response_model=ChatResponse, dependencies=[Depends(auth)])\nasync def vision_chat(\n    message: str = Form(default="Analise esta imagem e explique o que é relevante para mim."),\n    session_id: str = Form(default="main"),\n    request_id: str = Form(default=""),\n    image: UploadFile = File(...),\n    db: Session = Depends(get_db),\n):\n    rid = request_id.strip() or __import__("uuid").uuid4().hex\n    CANCELLATIONS.start(rid, session_id)\n    safety = assess_request(message)\n    if safety.decision == SafetyDecision.BLOCKED:\n        reply = "Não posso executar essa solicitação porque ela acionou um bloqueio absoluto do Safety & Legal Engine."\n        CANCELLATIONS.finish(rid)\n        return ChatResponse(request_id=rid, session_id=session_id, reply=reply, mode="safety_blocked", brain="safety-engine", task="safety", safety_decision=safety.decision.value, safety_category=safety.category, safety_reason=safety.reason)\n    try:\n        data = await image.read()\n        mime = validate_image(data, image.content_type or "", image.filename or "")\n        bundle = build_context(db, session_id, message)\n        if CANCELLATIONS.is_cancelled(rid):\n            return ChatResponse(request_id=rid, session_id=session_id, reply="Raciocínio interrompido.", mode="interrupted", brain="doom-core", task="interrupt", interrupted=True)\n        context_text = (bundle.memory_text or "") + "\\n\\n" + (bundle.profile_text or "")\n        result = analyze_image(data, mime, message, context_text=context_text, knowledge_text=bundle.knowledge_text)\n        if CANCELLATIONS.is_cancelled(rid):\n            return ChatResponse(request_id=rid, session_id=session_id, reply="Raciocínio interrompido.", mode="interrupted", brain="doom-vision", task="interrupt", interrupted=True)\n        get_or_create_conversation(db, session_id, message)\n        db.add(Message(session_id=session_id, role="user", content=message.strip() + " [imagem anexada]"))\n        db.add(Message(session_id=session_id, role="assistant", content=result.reply))\n        db.commit(); touch_conversation(db, session_id)\n        return ChatResponse(\n            request_id=rid, session_id=session_id, reply=result.reply, mode="vision", brain="doom-vision", task="analysis",\n            context_strategy=bundle.strategy, context_recent=bundle.recent_count, context_recalled=bundle.recalled_count,\n            memories_used=bundle.memory_count, knowledge_used=bundle.knowledge_count,\n            knowledge_sources=bundle.knowledge_hits, vision_used=True, vision_provider=result.provider, vision_model=result.model,\n        )\n    except VisionError as exc:\n        raise HTTPException(status_code=400, detail=str(exc)) from exc\n    finally:\n        CANCELLATIONS.finish(rid)\n\n\n'''
s=s.replace(needle, route+needle)
# add vision fields to normal response in main near return ChatResponse. We'll add defaults by schema so not needed.
p.write_text(s)

# 5) UI version and multimodal controls
p = STATIC/'index.html'
s = p.read_text()
s=s.replace('FOREST CORE · v1.12.0','FOREST CORE · v1.13.0')
s=s.replace('<button id="knowledgeBtn" class="doom-icon-btn" type="button" aria-label="Abrir base de conhecimento">▤</button>', '<button id="knowledgeBtn" class="doom-icon-btn" type="button" aria-label="Abrir base de conhecimento">▤</button><button id="multimodalBtn" class="doom-icon-btn" type="button" aria-label="Abrir controles multimodais">◉</button>')
s=s.replace('<div class="doom-module"><div class="k">Conhecimento</div><div class="v" id="knowledgeValue">0 FONTES</div><div class="s" id="knowledgeNote">Base de Conhecimento.</div></div>', '<div class="doom-module"><div class="k">Conhecimento</div><div class="v" id="knowledgeValue">0 FONTES</div><div class="s" id="knowledgeNote">Base de Conhecimento.</div></div><div class="doom-module"><div class="k">Multimodal</div><div class="v" id="multimodalValue">ATIVO</div><div class="s" id="multimodalNote">Voz + visão.</div></div>')
old='<form id="form" class="doom-inputbar"><input id="input" class="doom-input" autocomplete="off" placeholder="Fale com Doom..." aria-label="Mensagem para Doom"><button id="send" class="doom-btn">Enviar</button><button id="stop" class="doom-stop-btn" type="button" hidden>Interromper</button></form><div class="doom-hint">A chave Doom fica somente neste navegador. Estado visual, memória e cérebro são controlados pelo servidor.</div>'
new='<form id="form" class="doom-inputbar"><input id="input" class="doom-input" autocomplete="off" placeholder="Fale com Doom..." aria-label="Mensagem para Doom"><button id="imageBtn" class="doom-icon-btn doom-inline-btn" type="button" aria-label="Anexar imagem">▧</button><button id="micBtn" class="doom-icon-btn doom-inline-btn" type="button" aria-label="Falar com Doom">◌</button><button id="voiceBtn" class="doom-icon-btn doom-inline-btn" type="button" aria-label="Ativar resposta por voz">◉</button><button id="send" class="doom-btn">Enviar</button><button id="stop" class="doom-stop-btn" type="button" hidden>Interromper</button><input id="imageInput" type="file" accept="image/jpeg,image/png,image/webp,image/gif" capture="environment" hidden></form><div id="imageAttachment" class="doom-image-attachment" hidden><img id="imagePreview" alt="Pré-visualização da imagem anexada"><span id="imageName"></span><button id="clearImage" class="doom-tool-reset" type="button">Remover</button></div><div class="doom-hint">Voz e visão da v1.13. Imagens são enviadas apenas para análise e não são armazenadas permanentemente.</div>'
s=s.replace(old,new)
# add multimodal drawer before knowledge drawer
marker='<div id="knowledgeDrawer" class="doom-knowledge-drawer" aria-hidden="true">'
drawer='''<div id="multimodalDrawer" class="doom-safety-drawer doom-multimodal-drawer" aria-hidden="true">\n      <div class="doom-history-head"><div><strong>Multimodal</strong><span id="multimodalStatus">Voz + visão</span></div><button id="multimodalClose" class="doom-icon-btn" type="button" aria-label="Fechar multimodal">×</button></div>\n      <div class="doom-safety-body">\n        <div class="doom-safety-card"><div class="k">Visão</div><div class="v" id="visionServerState">ATIVA</div><div class="s" id="visionServerNote">Análise de imagens pelo provedor configurado.</div></div>\n        <div class="doom-safety-card"><div class="k">Entrada de voz</div><div class="v" id="voiceInputState">DISPONÍVEL</div><div class="s">Usa reconhecimento de fala do navegador quando suportado.</div></div>\n        <div class="doom-safety-card"><div class="k">Saída de voz</div><div class="v" id="voiceOutputState">DISPONÍVEL</div><div class="s">Usa Speech Synthesis do navegador.</div></div>\n        <div class="doom-safety-section"><div class="doom-safety-title">Modelo de visão</div><div id="visionModelList" class="doom-safety-note">Carregando...</div></div>\n      </div>\n    </div>\n    '''+marker
s=s.replace(marker,drawer)
s=s.replace('<script src="/static/doom-state.js?v=1.12.0"></script>', '<script src="/static/doom-state.js?v=1.13.0"></script>')
p.write_text(s)

# 6) JS multimodal additions
p = STATIC/'doom-state.js'
s=p.read_text()
s=s.replace('// Doom State / UI v1.12.0', '// Doom State / UI v1.13.0')
s=s.replace("const DOOM_UI_VERSION = '1.12.0';", "const DOOM_UI_VERSION = '1.13.0';")
# insert state constants near top
insert="""\nconst DOOM_MULTIMODAL={vision:false,voiceInput:false,voiceOutput:true,listening:false,recognition:null};\nlet DOOM_IMAGE_FILE=null;\n"""
s=s.replace("const DOOM_INTERRUPT={active:false,announced:false,requestId:null,controller:null};", "const DOOM_INTERRUPT={active:false,announced:false,requestId:null,controller:null};"+insert)
# add helper functions before form handler: locate "form.onsubmit"
idx=s.find('form.onsubmit=async e=>')
helpers=r'''
function updateMultimodalUI(d){const mv=$('#multimodalValue');const mn=$('#multimodalNote');const vs=$('#visionServerState');const vn=$('#visionServerNote');const vi=$('#voiceInputState');const vo=$('#voiceOutputState');const vm=$('#visionModelList');if(mv)mv.textContent=d?.vision?'ATIVO':'LIMITADO';if(mn)mn.textContent=d?.vision?'Voz + visão':'Voz do navegador; visão indisponível.';if(vs)vs.textContent=d?.vision?'ATIVA':'INATIVA';if(vn)vn.textContent=d?.vision?`Limite ${d.max_image_mb||10} MB.`:'Configure um provedor/modelo com suporte visual.';const SpeechRecognition=window.SpeechRecognition||window.webkitSpeechRecognition;if(vi)vi.textContent=SpeechRecognition?'DISPONÍVEL':'NÃO SUPORTADA';if(vo)vo.textContent=('speechSynthesis' in window)?'DISPONÍVEL':'NÃO SUPORTADA';if(vm)vm.textContent=(d?.providers||[]).map(x=>`${x.provider} · ${x.model}`).join('\n')||'Nenhum provedor configurado.';DOOM_MULTIMODAL.vision=!!d?.vision;DOOM_MULTIMODAL.voiceInput=!!SpeechRecognition;DOOM_MULTIMODAL.voiceOutput=('speechSynthesis' in window);}
async function refreshMultimodal(){try{const r=await fetch('/api/multimodal/status',{headers:{'X-Doom-Key':key.value.trim()}});if(!r.ok)throw new Error();updateMultimodalUI(await r.json());}catch{updateMultimodalUI({vision:false,providers:[]});}}
function openMultimodal(){closeHistory();closeMemory();closeTools();closeIdentity();closeSafety();closeIntegrations();closeKnowledge();const d=$('#multimodalDrawer');const b=$('#historyBackdrop');if(!d||!b)return;d.classList.add('open');b.classList.add('open');d.setAttribute('aria-hidden','false');refreshMultimodal();}
function closeMultimodal(){const d=$('#multimodalDrawer');if(!d)return;d.classList.remove('open');d.setAttribute('aria-hidden','true');if(!document.querySelector('.doom-.*-drawer.open')){} }
function setupSpeechRecognition(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){return;}const rec=new SR();rec.lang='pt-BR';rec.interimResults=true;rec.continuous=false;rec.maxAlternatives=1;rec.onstart=()=>{DOOM_MULTIMODAL.listening=true;$('#micBtn')?.classList.add('active');setState('thinking');};rec.onresult=e=>{let text='';for(let i=e.resultIndex;i<e.results.length;i++){text+=e.results[i][0].transcript;}if(e.results[e.results.length-1].isFinal)$('#input').value=text.trim();};rec.onerror=()=>{DOOM_MULTIMODAL.listening=false;$('#micBtn')?.classList.remove('active');setState('error');setTimeout(()=>setState('online'),700);};rec.onend=()=>{DOOM_MULTIMODAL.listening=false;$('#micBtn')?.classList.remove('active');if($('#input').value.trim())$('#input').focus();};DOOM_MULTIMODAL.recognition=rec;}
function toggleListening(){if(!DOOM_MULTIMODAL.recognition)return alert('Este navegador não oferece reconhecimento de voz para o Doom.');if(DOOM_MULTIMODAL.listening){try{DOOM_MULTIMODAL.recognition.stop();}catch{}return;}try{DOOM_MULTIMODAL.recognition.start();}catch{}}
function speakDoom(text){if(!DOOM_MULTIMODAL.voiceOutput)return;window.speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(String(text||''));u.lang='pt-BR';u.rate=1;u.pitch=1;window.speechSynthesis.speak(u);}
function toggleVoiceOutput(){DOOM_MULTIMODAL.voiceOutput=!DOOM_MULTIMODAL.voiceOutput;$('#voiceBtn')?.classList.toggle('active',DOOM_MULTIMODAL.voiceOutput);if(!DOOM_MULTIMODAL.voiceOutput&&'speechSynthesis' in window)window.speechSynthesis.cancel();}
function selectImage(){if(!DOOM_MULTIMODAL.vision)return alert('A visão está indisponível no servidor.');$('#imageInput')?.click();}
function clearImage(){DOOM_IMAGE_FILE=null;const input=$('#imageInput');if(input)input.value='';const box=$('#imageAttachment');if(box)box.hidden=true;}
function previewImage(file){DOOM_IMAGE_FILE=file||null;const box=$('#imageAttachment'),img=$('#imagePreview'),name=$('#imageName');if(!file||!box||!img||!name){clearImage();return;}img.src=URL.createObjectURL(file);name.textContent=file.name||'imagem';box.hidden=false;}
async function sendVisionMessage(text){const requestId=(crypto.randomUUID?crypto.randomUUID():String(Date.now())+'-'+Math.random().toString(16).slice(2));const sid=currentSessionId();const controller=new AbortController();DOOM_INTERRUPT={...DOOM_INTERRUPT};DOOM_INTERRUPT.active=true;DOOM_INTERRUPT.announced=false;DOOM_INTERRUPT.requestId=requestId;DOOM_INTERRUPT.controller=controller;const formData=new FormData();formData.append('message',text||'Analise esta imagem.');formData.append('session_id',sid);formData.append('request_id',requestId);formData.append('image',DOOM_IMAGE_FILE);$('#send').disabled=true;$('#stop').hidden=false;setState('analysis');try{const r=await fetch('/api/chat/vision',{method:'POST',headers:{'X-Doom-Key':key.value.trim()},body:formData,signal:controller.signal});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Falha na análise visual.');if(!d.interrupted){addMessage('doom',d.reply);if(DOOM_MULTIMODAL.voiceOutput)speakDoom(d.reply);if($('#engineValue'))$('#engineValue').textContent='DOOM VISION';if($('#engineNote'))$('#engineNote').textContent=d.vision_model||'Modelo visual';if($('#knowledgeValue'))$('#knowledgeValue').textContent=`${d.knowledge_used||0} FONTES`;setState('success');refreshHistory();}}catch(e){if(e.name==='AbortError'){addMessage('doom','Análise visual interrompida.');setState('interrupted');}else{addMessage('doom','Não consegui analisar a imagem: '+e.message);setState('error');}}finally{DOOM_INTERRUPT.active=false;DOOM_INTERRUPT.controller=null;$('#send').disabled=false;$('#stop').hidden=true;clearImage();setTimeout(()=>setState('online'),1200);}}
'''
s=s[:idx]+helpers+s[idx:]
# Modify form handler: add image branch before JSON fetch. Use targeted replacement after send/stop setup
needle="setState(inferLocalState(text));try{const chatHeaders={'Content-Type':'application/json','X-Doom-Key':key.value.trim()};"
replacement="setState(inferLocalState(text));try{if(DOOM_IMAGE_FILE){await sendVisionMessage(text);return;}const chatHeaders={'Content-Type':'application/json','X-Doom-Key':key.value.trim()};"
s=s.replace(needle,replacement)
# speak normal replies when voice enabled
s=s.replace("addMessage('doom',d.reply);if(d.safety_decision", "addMessage('doom',d.reply);if(DOOM_MULTIMODAL.voiceOutput)speakDoom(d.reply);if(d.safety_decision")
# append listeners + refresh call
s=s.replace("$('#addMemory')?.addEventListener('click',addMemory);\n\nrefreshIdentity().then(refreshGoogleAuth);\nrefreshKnowledge();", "$('#addMemory')?.addEventListener('click',addMemory);$('#multimodalBtn')?.addEventListener('click',openMultimodal);$('#multimodalClose')?.addEventListener('click',closeMultimodal);$('#imageBtn')?.addEventListener('click',selectImage);$('#imageInput')?.addEventListener('change',e=>previewImage(e.target.files?.[0]));$('#clearImage')?.addEventListener('click',clearImage);$('#micBtn')?.addEventListener('click',toggleListening);$('#voiceBtn')?.addEventListener('click',toggleVoiceOutput);$('#historyBackdrop')?.addEventListener('click',closeMultimodal);$('#stop')?.addEventListener('click',interruptCurrentRequest);setupSpeechRecognition();$('#voiceBtn')?.classList.toggle('active',DOOM_MULTIMODAL.voiceOutput);\n\nrefreshIdentity().then(refreshGoogleAuth);\nrefreshKnowledge();\nrefreshMultimodal();")
# Add a safe close backdrop for multimodal if existing big listener has it already; keep as an extra call.
# ensure all version strings
s=s.replace('1.12.0','1.13.0')
p.write_text(s)

# 7) CSS
p = STATIC/'doom.css'
s=p.read_text()
s += '''\n.doom-inline-btn{min-width:40px}.doom-inputbar{display:grid;grid-template-columns:minmax(0,1fr) auto auto auto auto auto;gap:7px;align-items:center}.doom-inline-btn.active{border-color:var(--doom-state);color:var(--doom-state);box-shadow:0 0 14px var(--doom-state-soft)}.doom-image-attachment{display:flex;align-items:center;gap:8px;padding:8px 12px;border:1px solid var(--doom-line);background:var(--doom-panel-2);border-radius:12px;margin-top:7px}.doom-image-attachment img{width:48px;height:48px;object-fit:cover;border-radius:8px;border:1px solid var(--doom-line)}.doom-image-attachment span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--doom-muted);font-size:9px}.doom-multimodal-drawer{z-index:74}@media (max-width:720px){.doom-inputbar{grid-template-columns:minmax(0,1fr) repeat(3,40px) auto auto}.doom-inputbar .doom-btn{padding:0 11px}.doom-inputbar .doom-stop-btn{padding:0 10px}}\n'''
p.write_text(s)

# 8) version/changelog/docs
for fname in ['DOOM_VERSION.txt','doom_version.txt']:
    (ROOT/fname).write_text('1.13.0\n')

ch=ROOT/'CHANGELOG.md'
s=ch.read_text()
s += '''\n\n## v1.13.0\n- Doom Multimodal: visão + voz em uma única versão.\n- Vision API para análise de imagens com OpenAI, OpenRouter ou Ollama conforme configuração.\n- Entrada de voz por reconhecimento nativo do navegador.\n- Saída de voz por Speech Synthesis do navegador.\n- Anexo, pré-visualização e remoção de imagens na interface.\n- Interface, telemetria e estado visual atualizados para v1.13.0.\n- Imagens não são persistidas pelo Doom após a análise.\n'''
ch.write_text(s)

readme=ROOT/'DOOM_V1_13.md'
readme.write_text('''# Doom v1.13.0 — Multimodal (Voz + Visão)\n\nA v1.13 junta voz e visão em uma única etapa.\n\n## Visão\n- `POST /api/chat/vision` recebe imagem + solicitação.\n- Suporta JPG, PNG, WebP e GIF.\n- Limite configurável por `VISION_MAX_FILE_MB`.\n- Seleciona o provedor do Cortex configurado e usa o modelo visual específico quando definido.\n- Contexto e Knowledge são apenas apoio; a solicitação atual permanece prioritária.\n- A imagem não é gravada permanentemente pelo Doom.\n\n## Voz\n- Entrada por `SpeechRecognition` / `webkitSpeechRecognition` quando o navegador oferece suporte.\n- Saída por `speechSynthesis`.\n- Botões de microfone e resposta por voz ficam na barra de conversa.\n\n## Configuração\n```env\nMULTIMODAL_ENABLED=true\nVISION_MAX_FILE_MB=10\nOPENAI_VISION_MODEL=\nOPENROUTER_VISION_MODEL=\nOLLAMA_VISION_MODEL=\n```\n\nOs modelos visuais devem aceitar entrada de imagem.\n''')

# 9) Tests
(ROOT/'tests/test_v113_multimodal.py').write_text(r'''import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
import pytest

from app.config import get_settings
from app.multimodal import VisionError, validate_image
from app.main import app


def test_v113_version_and_ui():
    c = TestClient(app)
    h = c.get('/health')
    assert h.json()['version'] == '1.13.0'
    html = c.get('/').text
    assert 'FOREST CORE · v1.13.0' in html
    assert '/static/doom-state.js?v=1.13.0' in html
    assert 'id="imageBtn"' in html
    assert 'id="micBtn"' in html


def test_image_validation_accepts_supported_formats(monkeypatch):
    monkeypatch.setattr(get_settings(), 'multimodal_enabled', True)
    monkeypatch.setattr(get_settings(), 'vision_max_file_mb', 2)
    assert validate_image(b'123', 'image/png', 'x.png') == 'image/png'
    assert validate_image(b'123', '', 'x.webp') == 'image/webp'


def test_image_validation_rejects_unsupported_and_oversized(monkeypatch):
    monkeypatch.setattr(get_settings(), 'multimodal_enabled', True)
    monkeypatch.setattr(get_settings(), 'vision_max_file_mb', 1)
    with pytest.raises(VisionError):
        validate_image(b'123', 'text/plain', 'x.txt')
    with pytest.raises(VisionError):
        validate_image(b'x'*(1024*1024+1), 'image/png', 'x.png')


def test_multimodal_status_route_requires_auth(monkeypatch):
    c = TestClient(app)
    r = c.get('/api/multimodal/status')
    assert r.status_code == 401
''')

print('patched v1.13')
