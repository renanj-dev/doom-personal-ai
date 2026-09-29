# Doom v1.4 — Tool Engine

Esta entrega contém o núcleo modular do sistema de ferramentas da Doom.

## Uso rápido

```python
from doom_tools import build_default_engine

engine = build_default_engine()

print(engine.list_tools())

result = engine.invoke(
    "calculator",
    {"expression": "(12 + 8) * 3"},
    session_id="main",
)

print(result.data)
```

A v1.4 é uma camada de infraestrutura: ela pode ser integrada ao Doom Cortex sem exigir que o modelo tenha acesso direto ao sistema.
