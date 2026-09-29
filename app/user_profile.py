"""Consolidated, non-sensitive user profile for Doom.

This file is intentionally human-readable and easy to edit. It should contain
only information the user wants Doom to retain as durable context.
"""

USER_PROFILE = {
    "identity": {
        "name": "Renan",
        "age": "18 anos (informação fornecida pelo usuário em setembro de 2026)",
        "country": "Brasil",
    },
    "education": {
        "current_stage": "3º ano do ensino médio",
        "school_context": "Ensino médio no Brasil, com foco em conteúdos escolares e preparação para exames",
        "study_preferences": [
            "explicações lineares e em sequência lógica",
            "conceitos antes de avançar para tópicos dependentes",
            "exemplos práticos",
            "explicações no nível adequado ao ensino médio quando solicitado",
            "análises completas quando o assunto é importante",
        ],
        "interests": [
            "ENEM",
            "vestibulares",
            "matemática e conteúdos escolares",
            "medicina e tecnologia aplicada à medicina",
        ],
    },
    "work_and_skills": {
        "experience": "Experiência em atendimento e organização em ambiente de padaria/lanchonete/confeitaria",
        "skills": [
            "atendimento ao cliente",
            "organização",
            "responsabilidade e comprometimento",
            "aprendizado de novas atividades",
            "informática básica",
        ],
    },
    "thinking_and_communication": {
        "patterns": [
            "faz perguntas de acompanhamento para aprofundar o assunto",
            "gosta de comparar cenários e alternativas",
            "costuma transformar ideias pequenas em projetos maiores",
            "valoriza fatos, explicações e raciocínio passo a passo",
            "prefere comunicação natural, clara e sem excesso de formalidade",
            "gosta que erros ou limitações sejam apontados com respeito",
        ],
        "preferred_assistant_behavior": [
            "não concordar automaticamente",
            "separar fatos, hipóteses, interpretações e opiniões",
            "mostrar consequências e alternativas sem tomar decisões pelo usuário",
            "adaptar o nível de detalhe ao pedido",
            "lembrar o contexto de projetos em andamento",
        ],
    },
    "technology": {
        "interests": [
            "inteligência artificial",
            "programação",
            "automação",
            "computadores",
            "criação de assistentes pessoais",
            "integração entre PC, celular e serviços em nuvem",
        ],
        "current_pc": {
            "cpu": "Intel Core i5-3470",
            "ram": "16 GB",
            "gpu": "NVIDIA GeForce GT 730 2 GB",
            "storage": "ADATA SU650 SSD",
            "os_architecture": "Windows 64-bit",
        },
    },
    "projects": {
        "doom": [
            "Projeto pessoal de uma IA assistente masculina chamada Doom.",
            "Doom deve ter personalidade própria, memória, voz, visão, ferramentas e integração futura com PC e celular.",
            "A identidade visual preferida é verde-escuro em tom de floresta.",
            "A arquitetura desejada deve permitir trocar o modelo de IA sem perder a personalidade ou a memória da Doom.",
            "O usuário quer combinar cérebros locais e online para equilibrar custo, qualidade, privacidade e disponibilidade.",
        ],
    },
    "career": {
        "interests": [
            "medicina",
            "tecnologia",
            "projetos que combinam ciência, tecnologia e resolução de problemas",
        ],
    },
    "assistant_note": "Este perfil é um resumo contextual. Deve ser corrigido quando Renan fornecer informação nova ou contraditória. Não inventar dados ausentes."
}


def render_profile() -> str:
    lines = [
        "PERFIL CONSOLIDADO DO USUÁRIO — RENAN",
        "Use este perfil somente como contexto sobre o usuário. Doom e Renan são entidades diferentes.",
        "",
        "IDENTIDADE",
        f"- Nome: {USER_PROFILE['identity']['name']}",
        f"- Idade registrada: {USER_PROFILE['identity']['age']}",
        f"- País: {USER_PROFILE['identity']['country']}",
        "",
        "EDUCAÇÃO",
        f"- Situação: {USER_PROFILE['education']['current_stage']}",
        f"- Contexto: {USER_PROFILE['education']['school_context']}",
        "- Preferências de estudo:",
    ]
    lines.extend(f"  - {x}" for x in USER_PROFILE["education"]["study_preferences"])
    lines.append("- Interesses educacionais:")
    lines.extend(f"  - {x}" for x in USER_PROFILE["education"]["interests"])

    lines += ["", "TRABALHO E HABILIDADES", f"- Experiência: {USER_PROFILE['work_and_skills']['experience']}", "- Habilidades:"]
    lines.extend(f"  - {x}" for x in USER_PROFILE["work_and_skills"]["skills"])

    lines += ["", "MODO DE PENSAR E COMUNICAR", "- Padrões observados:"]
    lines.extend(f"  - {x}" for x in USER_PROFILE["thinking_and_communication"]["patterns"])
    lines.append("- Como o assistente deve interagir:")
    lines.extend(f"  - {x}" for x in USER_PROFILE["thinking_and_communication"]["preferred_assistant_behavior"])

    lines += ["", "TECNOLOGIA", "- Interesses:"]
    lines.extend(f"  - {x}" for x in USER_PROFILE["technology"]["interests"])
    lines += [
        "- PC atual registrado:",
        f"  - CPU: {USER_PROFILE['technology']['current_pc']['cpu']}",
        f"  - RAM: {USER_PROFILE['technology']['current_pc']['ram']}",
        f"  - GPU: {USER_PROFILE['technology']['current_pc']['gpu']}",
        f"  - Armazenamento: {USER_PROFILE['technology']['current_pc']['storage']}",
        f"  - Sistema: {USER_PROFILE['technology']['current_pc']['os_architecture']}",
    ]

    lines += ["", "PROJETOS"]
    lines.extend(f"- Doom: {x}" for x in USER_PROFILE["projects"]["doom"])

    lines += ["", "CARREIRA"]
    lines.extend(f"- Interesse: {x}" for x in USER_PROFILE["career"]["interests"])
    lines += ["", "NOTA", USER_PROFILE["assistant_note"]]
    return "\n".join(lines)


def render_profile_for_query(query: str) -> str:
    """Render only the profile sections most relevant to the current query."""
    q = (query or "").lower()
    sections: list[str] = ["identity"]
    if any(k in q for k in ("estud", "aprender", "enem", "aula", "matemática", "faculdade")):
        sections += ["education"]
    if any(k in q for k in ("trabalho", "currículo", "vaga", "emprego", "habilidade")):
        sections += ["work_and_skills"]
    if any(k in q for k in ("pc", "computador", "python", "programa", "tecnologia", "ia", "ollama", "código")):
        sections += ["technology"]
    if any(k in q for k in ("doom", "projeto", "cortex", "memória", "layout", "app")):
        sections += ["projects"]
    if any(k in q for k in ("carreira", "medicina", "profissão", "futuro")):
        sections += ["career"]
    if not len(sections) > 1:
        sections += ["thinking_and_communication"]

    unique_sections = list(dict.fromkeys(sections))
    lines = [
        "PERFIL FOCADO DO USUÁRIO — RENAN",
        "Doom e Renan são entidades diferentes. Use somente como contexto durável."
    ]
    for section in unique_sections:
        data = USER_PROFILE.get(section, {})
        title = section.replace("_", " ").upper()
        lines += ["", title]
        if isinstance(data, dict):
            for key, value in data.items():
                label = key.replace("_", " ").capitalize()
                if isinstance(value, list):
                    lines.append(f"- {label}:")
                    lines.extend(f"  - {item}" for item in value)
                elif isinstance(value, dict):
                    lines.append(f"- {label}:")
                    for subkey, subvalue in value.items():
                        lines.append(f"  - {subkey.replace('_', ' ').capitalize()}: {subvalue}")
                else:
                    lines.append(f"- {label}: {value}")
    return "\n".join(lines)
