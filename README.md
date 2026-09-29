# Doom v1.4 — Cortex ↔ Tool Engine Integration

Esta etapa conecta o **Doom Cortex** ao **Tool Engine** por uma fronteira estruturada e auditável.

## Fluxo

```text
Usuário
  ↓
Cortex / Provider
  ↓
JSON estrito de tool request
  ↓
CortexToolBridge
  ↓
Tool Engine
  ├─ SAFE → executa
  ├─ CONFIRM → gera token e para
  └─ BLOCKED → recusa
  ↓
ToolResult
  ↓
Cortex recebe DOOM_TOOL_RESULT
  ↓
Resposta final ao usuário
```

## O que esta implementação resolve

- Catálogo de ferramentas injetável no prompt do Cortex.
- Parser estrito: o modelo precisa produzir apenas o objeto JSON da chamada.
- Execução delegada exclusivamente ao `ToolEngine`.
- Ferramentas `confirm` interrompem o loop e exigem confirmação explícita.
- Resultado da ferramenta volta ao Cortex em mensagem estruturada.
- Loop limitado para impedir chamadas infinitas.
- Integração independente do provider (Ollama, OpenRouter, OpenAI etc.).

## Contrato do Cortex

Pedido:

```json
{"tool":"calculator","args":{"expression":"(12+8)*3"}}
```

Resultado interno:

```text
DOOM_TOOL_RESULT
{"tool":"calculator","ok":true,"data":{"expression":"(12+8)*3","result":60},"error":null}
```

Quando não precisa de ferramenta, o Cortex responde normalmente em texto.

## Integração no projeto real

O arquivo `cortex_bridge.py` foi feito como adaptador para não depender da estrutura exata da v1.3. A conexão com o seu `Cortex` atual consiste em:

1. criar um `ToolEngine` compartilhado por processo;
2. criar `CortexToolBridge(engine)`;
3. acrescentar `bridge.build_system_addendum()` às instruções do Cortex;
4. depois da resposta do provider, passar o texto por `bridge.handle_model_output(...)` ou usar `bridge.run_loop(...)` no ponto central do chat;
5. persistir os `AuditEvent` no banco na próxima subetapa.

## Limites de segurança mantidos

A integração não adiciona `subprocess`, shell, PowerShell, `eval`, execução de código arbitrário ou acesso irrestrito ao sistema de arquivos.
