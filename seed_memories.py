from app.db import SessionLocal, init_db
from app.models import Memory

INITIAL_MEMORIES = [
    ("identidade", "O usuário prefere ser chamado de Renan."),
    ("identidade", "O usuário informou que já tem 18 anos em setembro de 2026."),
    ("identidade", "O usuário é do Brasil."),
    ("educacao", "O usuário está no 3º ano do ensino médio."),
    ("educacao", "O usuário se prepara para provas escolares, ENEM e vestibulares."),
    ("aprendizado", "O usuário prefere explicações lineares, em sequência lógica, com conceitos antes de avançar, exemplos e aplicação prática."),
    ("aprendizado", "Quando pede uma análise completa, o usuário prefere respostas abrangentes e organizadas."),
    ("aprendizado", "O usuário gosta que o nível da explicação seja adaptado ao contexto, especialmente ao nível do ensino médio quando solicitado."),
    ("comunicacao", "O usuário prefere comunicação natural, clara e sem excesso de formalidade ou linguagem robótica."),
    ("analise", "O usuário costuma fazer perguntas de acompanhamento para aprofundar assuntos."),
    ("analise", "O usuário gosta de separar fatos, hipóteses, interpretações e consequências."),
    ("analise", "O usuário gosta de comparar cenários, alternativas e possibilidades."),
    ("planejamento", "O usuário gosta de transformar ideias em etapas concretas, cenários e projetos executáveis."),
    ("criatividade", "O usuário frequentemente transforma ideias pequenas em projetos maiores."),
    ("tecnologia", "O usuário demonstra interesse recorrente por inteligência artificial, programação, automação e computadores."),
    ("tecnologia", "O usuário quer integrar uma IA pessoal a PC, celular, voz, visão, memória e ferramentas."),
    ("pc", "O PC atual registrado do usuário usa Intel Core i5-3470, 16 GB de RAM, SSD ADATA SU650 e NVIDIA GeForce GT 730 de 2 GB, em Windows 64-bit."),
    ("trabalho", "O usuário possui experiência em atendimento, organização e apoio operacional em ambiente de padaria/lanchonete/confeitaria."),
    ("habilidades", "O usuário valoriza atendimento ao cliente, organização, responsabilidade, comprometimento, aprendizado de novas atividades e informática básica."),
    ("carreira", "O usuário demonstra interesse em medicina, tecnologia e projetos que combinam ciência, tecnologia e resolução de problemas."),
    ("projeto_doom", "A Doom é um projeto pessoal contínuo do usuário e deve ter identidade própria, personalidade masculina, memória, voz, visão, ferramentas e integração futura com PC e celular."),
    ("projeto_doom", "A identidade visual escolhida para a Doom usa verde-escuro em tom de floresta, em vez de vermelho."),
    ("projeto_doom", "A arquitetura da Doom deve permitir trocar o modelo de IA sem perder personalidade, memória e ferramentas."),
    ("projeto_doom", "O usuário quer combinar cérebros locais e online para equilibrar custo, qualidade, privacidade e disponibilidade."),
]


def seed_memories() -> int:
    init_db()
    db = SessionLocal()
    try:
        existing = {m.content for m in db.query(Memory).all()}
        added = 0
        for category, content in INITIAL_MEMORIES:
            if content not in existing:
                db.add(Memory(category=category, content=content))
                added += 1
        db.commit()
        return added
    finally:
        db.close()


if __name__ == "__main__":
    print(f"Memórias iniciais inseridas: {seed_memories()}")
