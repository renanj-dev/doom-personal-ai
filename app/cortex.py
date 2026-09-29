from dataclasses import dataclass
from .config import get_settings
from .llm import ask_doom, build_tool_protocol
from .tools import TOOL_ENGINE

settings=get_settings()
TASK_LABELS={"chat":"CONVERSA","study":"ESTUDO","analysis":"ANÁLISE / POSSIBILIDADES","creation":"CRIAÇÃO","execution":"EXECUÇÃO","memory":"MEMÓRIA","speculation":"ESPECULAÇÃO"}

@dataclass(frozen=True)
class CortexRoute:
    task:str; task_label:str; provider:str; model:str; fallback_count:int; reason:str

def classify_task(message:str)->str:
    t=(message or '').strip().lower()
    if any(k in t for k in ("quem sou eu","o que você sabe sobre mim","o que sabe sobre mim","memória","lembra","lembrar","esquecer")): return "memory"
    if any(k in t for k in ("estud","aprender","exercício","matemática","enem","aula")): return "study"
    if any(k in t for k in ("analise","análise","possibilidade","possibilidades","compare","comparar","cenário","hipótese","avaliar")): return "analysis"
    if any(k in t for k in ("crie","criar","escreva","escrever","desenhe","ideia","projeto","roteiro")): return "creation"
    if any(k in t for k in ("execute","executar","abra","rodar","rode","faça isso","inicie")): return "execution"
    if any(k in t for k in ("talvez","especul","e se","hipotetic","imagina")): return "speculation"
    return "chat"

def configured_providers()->list[str]:
    raw=settings.cortex_providers or settings.provider
    providers=[p.strip().lower() for p in raw.split(',') if p.strip()]
    return [p for p in providers if p in {'ollama','openrouter','openai'}]

def provider_available(provider:str)->bool:
    if provider=='ollama': return bool(settings.ollama_base_url)
    if provider=='openrouter': return bool(settings.openrouter_api_key)
    if provider=='openai': return bool(settings.openai_api_key)
    return False

def provider_model(provider:str)->str:
    return {'ollama':settings.ollama_model,'openrouter':settings.openrouter_model,'openai':settings.openai_model}.get(provider,settings.doom_model)

def preference_for(task:str,providers:list[str])->list[str]:
    preferred=["openrouter","openai","ollama"] if task in {"analysis","creation","study","speculation"} else ["ollama","openrouter","openai"]
    return [p for p in preferred if p in providers and provider_available(p)]+[p for p in providers if p not in preferred and provider_available(p)]

def route_task(message:str):
    task=classify_task(message); providers=configured_providers(); candidates=preference_for(task,providers)
    reason={"chat":"tarefa geral","study":"tarefa pedagógica","analysis":"tarefa analítica","creation":"tarefa criativa","execution":"tarefa operacional","memory":"tarefa de memória","speculation":"tarefa especulativa"}[task]
    return task,candidates,reason

def _tool_context_messages(memory_text, recent_messages, profile_text, provider, response_text, result):
    messages=list(recent_messages)
    messages.append({"role":"assistant","content":response_text})
    messages.append({"role":"user","content":"DOOM_TOOL_RESULT\nO Tool Engine executou a ferramenta solicitada. Use somente este resultado para responder ao usuário:\n"+__import__('json').dumps(result,ensure_ascii=False)})
    return messages

def ask_with_cortex(memory_text:str,recent_messages:list[dict],user_message:str,profile_text:str|None=None,session_id:str='main')->tuple[str,CortexRoute]:
    task,candidates,reason=route_task(user_message)
    if not candidates: raise RuntimeError("O Cortex não encontrou nenhum cérebro configurado e disponível.")
    errors=[]
    for index,provider in enumerate(candidates):
        try:
            messages=list(recent_messages)
            reply=ask_doom(memory_text,messages,provider=provider,profile_text=profile_text)
            for _ in range(2):
                request=TOOL_ENGINE.parse_request(reply)
                if not request: break
                if request.get('invalid'): raise RuntimeError(f"O modelo solicitou uma ferramenta inexistente: {request.get('tool')}")
                result=TOOL_ENGINE.execute(request['tool'],request['args'],session_id,settings.doom_user_name)
                if result.get('requires_confirmation'):
                    reply=(f"A ferramenta '{request['tool']}' exige confirmação antes de ser executada. "
                           "A solicitação foi interrompida por segurança.")
                    break
                if not result.get('ok'):
                    reply=result.get('error') or 'A ferramenta não pôde ser executada.'
                    break
                messages=_tool_context_messages(memory_text,messages,profile_text,provider,reply,result)
                reply=ask_doom(memory_text,messages,provider=provider,profile_text=profile_text)
            return reply,CortexRoute(task,TASK_LABELS.get(task,task.upper()),provider,provider_model(provider),index,reason)
        except Exception as exc:
            errors.append(f"{provider}: {exc}")
    raise RuntimeError("Todos os cérebros disponíveis falharam. "+' | '.join(errors))
