# DOOM VISUAL CODEX — v1.1

## Direção

A interface da Doom usa **Forest Core** como identidade visual permanente. O verde-floresta é a linguagem estrutural; os estados alteram apenas accents, glows, badges, barras e runas.

## Base

- Deep: `#0D3B1F`
- Main: `#1A5C2E`
- Active: `#2D8A3E`
- Dark background: `#0A110D`
- Light background: `#F4F7F2`

## Estados

| Estado | Dark | Light | Uso |
|---|---|---|---|
| Erro | `#FF9A90` | `#8E2C32` | falhas e bloqueios |
| Sucesso | `#91D5A0` | `#206B39` | confirmação |
| Aviso | `#F1C46B` | `#805700` | atenção |
| Info | `#8CBFD4` | `#24576B` | informação neutra |
| Análise/Possibilidades | `#B9A9EE` | `#58458A` | exploração e comparação |
| Criação | `#DFA8D2` | `#783E72` | geração |
| Execução | `#9FD2B1` | `#2D6547` | ação em andamento |
| Memória | `#A5B8E7` | `#405B8F` | memória e perfil |
| Estudo | `#E9ECE8` | `#35423A` | foco/estudo |
| Offline | `#C9AE86` | `#6D512E` | indisponibilidade de rede |
| Online | `#8DD5B3` | `#1F6A49` | operação normal |
| Especulação | `#C5ACEA` | `#65478C` | hipóteses |

## Layout v0.9

- Moldura externa discreta.
- Topbar com identidade, Cortex e controles.
- Ribbon semântico com estado + runas.
- Coluna lateral esquerda: Cortex.
- Centro: Command Center/conversa.
- Coluna lateral direita: telemetria.
- Runas de canto decorativas.
- Rodapé com identidade do sistema.

## Regras de comportamento visual

1. Não transformar a interface inteira na cor do estado.
2. Preservar o verde-floresta como estrutura base.
3. Usar cor semântica principalmente em accent, border, glow, badge, barra e rune.
4. Em `ERROR`, as runas ativas tornam-se escuras/pretas.
5. Em `STUDY`, o accent é branco/cinza muito claro.
6. Respeitar `prefers-reduced-motion`.
7. Manter texto e controles com contraste adequado.
