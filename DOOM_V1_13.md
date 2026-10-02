# Doom v1.13.0 — Multimodal (Voz + Visão)

A v1.13 junta voz e visão em uma única etapa.

## Visão
- `POST /api/chat/vision` recebe imagem + solicitação.
- Suporta JPG, PNG, WebP e GIF.
- Limite configurável por `VISION_MAX_FILE_MB`.
- Seleciona o provedor do Cortex configurado e usa o modelo visual específico quando definido.
- Contexto e Knowledge são apenas apoio; a solicitação atual permanece prioritária.
- A imagem não é gravada permanentemente pelo Doom.

## Voz
- Entrada por `SpeechRecognition` / `webkitSpeechRecognition` quando o navegador oferece suporte.
- Saída por `speechSynthesis`.
- Botões de microfone e resposta por voz ficam na barra de conversa.

## Configuração
```env
MULTIMODAL_ENABLED=true
VISION_MAX_FILE_MB=10
OPENAI_VISION_MODEL=
OPENROUTER_VISION_MODEL=
OLLAMA_VISION_MODEL=
```

Os modelos visuais devem aceitar entrada de imagem.
