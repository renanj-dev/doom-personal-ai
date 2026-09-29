# Doom Cloud v1.6.0 — Planner / Agent

A v1.6 adiciona um modo Agent controlado e persistente ao Doom Core.

## Capacidades
- toggle global ON/OFF e override por requisição;
- planejamento estruturado em JSON com etapas limitadas;
- etapas de ferramenta e Deep Search;
- execução sequencial com limites de segurança;
- confirmação de ferramentas integrada ao Agent;
- retomada do Agent após confirmação, com resposta persistida no histórico;
- registro de `AgentRun` e `AgentStep` no banco;
- endpoints para status, histórico e inspeção das execuções;
- síntese final baseada somente nos resultados registrados das etapas.

## Limites
- até 8 etapas por execução (configurável até esse máximo);
- até 5 chamadas de ferramenta por execução;
- somente ferramentas presentes no catálogo podem ser planejadas;
- o Agent não ganha permissão adicional: o Tool Engine continua aplicando SAFE/CONFIRM/BLOCKED;
- Deep Search só é usado quando já estiver habilitado para aquela execução.

O Agent fica DESATIVADO por padrão.
