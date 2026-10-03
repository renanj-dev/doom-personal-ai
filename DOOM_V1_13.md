# Doom v1.13

## v1.13.2 — Realtime Vision + Voice (preview local, analysis on demand)

- Câmera contínua para pré-visualização local no navegador.
- Nenhum frame é enviado à IA automaticamente.
- Botão “Analisar agora” captura apenas o quadro atual e reutiliza o pipeline de visão.
- Comando de voz pode disparar análise do quadro quando a câmera e a visão estão ativas.
- A câmera é desligada explicitamente pelo usuário e também no fechamento da página.
- Estado visual diferenciado: câmera ativa/prévia local versus IA analisando.
- Requer contexto seguro (HTTPS ou localhost) e permissão do navegador para câmera.
