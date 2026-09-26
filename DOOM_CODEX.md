# DOOM VISUAL CODEX — FOREST CORE

## Identidade
Doom usa verde-floresta como identidade permanente. Modos/estados alteram accents, glows, barras, badges e runas; o fundo permanece derivado da base.

## Base
- deep `#0D3B1F`
- main `#1A5C2E`
- active `#2D8A3E`
- dark background `#0A110D`
- light background `#F4F7F2`

## Estados
| Estado | Dark | Light | Uso |
|---|---|---|---|
| Erro | `#FF9A90` | `#8E2C32` | falha |
| Sucesso | `#91D5A0` | `#206B39` | conclusão |
| Aviso | `#F1C46B` | `#805700` | atenção |
| Info | `#8CBFD4` | `#24576B` | informação |
| Análise/Possibilidades | `#B9A9EE` | `#58458A` | análise e comparação |
| Criação | `#DFA8D2` | `#783E72` | criação |
| Execução | `#9FD2B1` | `#2D6547` | ação/ferramenta |
| Memória | `#A5B8E7` | `#405B8F` | memória |
| Estudo | `#E9ECE8` | `#35423A` | estudo |
| Offline | `#C9AE86` | `#6D512E` | sem conexão |
| Online | `#8DD5B3` | `#1F6A49` | conectado |
| Especulação | `#C5ACEA` | `#65478C` | hipótese |

## Regras
1. Cor semântica é accent, não fundo total.
2. Estados devem ser comunicados por cor + texto/símbolo.
3. Em erro, as runas ficam pretas/dark e o accent assume vermelho.
4. A personalidade e o cérebro são independentes do tema visual.
5. O mesmo Codex deve servir para local e Cloud.

## Máquina de estados
`online`, `thinking`, `error`, `success`, `warning`, `info`, `analysis`, `creation`, `execution`, `memory`, `study`, `offline`, `speculation`.
