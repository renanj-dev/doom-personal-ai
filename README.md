# Doom v1.4.4

**History & Memory Management Engine**

Pacote modular para integrar ao Doom existente:

- `memory_history_engine.py` — persistência e regras de negócio;
- `router.py` — endpoints FastAPI opcionais;
- `test_memory_history.py` — suíte de validação;
- `DOOM_V1_4_4.md` — arquitetura e instruções.

## Validação

```bash
python -m unittest -v test_memory_history.py
python -m compileall -q .
```
