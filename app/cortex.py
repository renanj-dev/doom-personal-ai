from dataclasses import dataclass
import re
from .config import get_settings
from .llm import ask_doom

settings = get_settings()

TASK_LABELS = {
    "chat": "CONVERSA",
    "study": "ESTUDO",
    "analysis": "ANÁLISE / POSSIBILIDADES",
    "creation": "CRIAÇÃO",
    "execution": "EXECUÇÃO",
    "memory": "MEMÓRIA",
    "speculation": "ESPECULAÇÃO",
}

@dataclass(frozen=True)
class CortexRoute:
    task: str
    task_label: str
    provider: str
    model: str
    fallback_count: int
    reason: str


def classify_task(message: str) -> str:
    t = (message or "").strip().lower()
    if any(k in t for k in ("quem sou eu", "o que você sabe sobre mim", "o que sabe sobre mim", "memória", "lembra", "lembrar", "esquecer")):
        return "memory"
    if any(k in t for k in ("estud", "aprender", "exercício", "matemática", "enem", "aula")):
        return "study"
    if any(k in t for k in ("analise", "análise", "possibilidade", "possibilidades", "compare", "comparar", "cenário", "hipótese", "avaliar")):
        return "analysis"
    if any(k in t for k in ("crie", "criar", "escreva", "escrever", "desenhe", "ideia", "projeto", "roteiro")):
        return "creation"
    if any(k in t for k in ("execute", "executar", "abra", "rodar", "rode", "faça isso", "inicie")):
        return "execution"
    if any(k in t for k in ("talvez", "especul", "e se", "hipotetic", "imagina")):
        return "speculation"
    return "chat"


def configured_providers() -> list[str]:
    raw = settings.cortex_providers or settings.provider
    providers = [p.strip().lower() for p in raw.split(",") if p.strip()]
    return [p for p in providers if p in {"ollama", "openrouter", "openai"}]


def provider_available(provider: str) -> bool:
    if provider == "ollama":
        return bool(settings.ollama_base_url)
    if provider == "openrouter":
        return bool(settings.openrouter_api_key)
    if provider == "openai":
        return bool(settings.openai_api_key)
    return False


def provider_model(provider: str) -> str:
    if provider == "ollama":
        return settings.ollama_model
    if provider == "openrouter":
        return settings.openrouter_model
    if provider == "openai":
        return settings.openai_model
    return settings.doom_model


def preference_for(task: str, providers: list[str]) -> list[str]:
    # Online-capable models are preferred for complex reasoning; local is preferred for
    # simple/offline-friendly tasks. The configured provider list is always respected.
    if task in {"analysis", "creation", "study", "speculation"}:
        preferred = ["openrouter", "openai", "ollama"]
    elif task in {"chat", "memory", "execution"}:
        preferred = ["ollama", "openrouter", "openai"]
    else:
        preferred = providers
    ordered = [p for p in preferred if p in providers and provider_available(p)]
    ordered += [p for p in providers if p not in ordered and provider_available(p)]
    return ordered


def route_task(message: str) -> tuple[str, list[str], str]:
    task = classify_task(message)
    providers = configured_providers()
    candidates = preference_for(task, providers)
    reason = {
        "chat": "tarefa geral; priorizando resposta rápida e fallback local quando disponível",
        "study": "tarefa pedagógica; priorizando um modelo online mais capaz quando disponível",
        "analysis": "tarefa analítica; priorizando um modelo online mais capaz quando disponível",
        "creation": "tarefa criativa; priorizando um modelo online mais capaz quando disponível",
        "execution": "tarefa operacional; priorizando o cérebro local quando disponível",
        "memory": "tarefa ligada à memória; o perfil é tratado pelo Doom Core quando aplicável",
        "speculation": "tarefa especulativa; priorizando um modelo online mais capaz quando disponível",
    }[task]
    return task, candidates, reason


def ask_with_cortex(memory_text: str, recent_messages: list[dict], user_message: str, profile_text: str | None = None) -> tuple[str, CortexRoute]:
    task, candidates, reason = route_task(user_message)
    if not candidates:
        raise RuntimeError("O Cortex não encontrou nenhum cérebro configurado e disponível.")

    errors: list[str] = []
    for index, provider in enumerate(candidates):
        try:
            reply = ask_doom(memory_text=memory_text, recent_messages=recent_messages, provider=provider, profile_text=profile_text)
            route = CortexRoute(
                task=task,
                task_label=TASK_LABELS.get(task, task.upper()),
                provider=provider,
                model=provider_model(provider),
                fallback_count=index,
                reason=reason,
            )
            return reply, route
        except Exception as exc:
            errors.append(f"{provider}: {exc}")

    raise RuntimeError("Todos os cérebros disponíveis falharam. " + " | ".join(errors))
