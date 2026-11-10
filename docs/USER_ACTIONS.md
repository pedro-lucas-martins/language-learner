# Ações do usuário

Tudo o que precisa ser feito à mão (contas, chaves, comandos). Marque conforme for fazendo.

## Agora (fatia 0)

- [ ] Rodar localmente para conferir: `cp .env.example .env` e `docker compose up --build`.
      Abrir http://localhost:5173 — deve aparecer **"Backend OK (development)"**.
- [ ] Conferir no GitHub (aba **Actions**) que o CI passou no último commit.

## Antes da fatia 1 (conversa por texto)

- [ ] **Gemini:** criar uma API key no Google AI Studio **com faturamento ativado** (tier pago).
      Colocar em `GEMINI_API_KEY` no `.env`.
- [ ] **Escolher os modelos** na página de preços do Gemini e preencher `GEMINI_CHAT_MODEL`,
      `GEMINI_UTILITY_MODEL`, `GEMINI_STT_MODEL` e os `PRICE_*` correspondentes.
      Anotar a escolha e a data na tabela de `docs/DECISIONS.md`.
- [ ] **Alerta de orçamento** no Google Cloud Billing (ex.: alerta em US$ 10).

## Antes da fatia 2 (voz)

- [ ] **ElevenLabs:** assinar um plano (Starter ou Creator), criar a API key e colocar em `ELEVENLABS_API_KEY`.
- [ ] Na ElevenLabs, deixar **desligada** a cobrança por uso excedente (se o plano oferecer), para o fallback gratuito entrar em vez de cobrar a mais.
- [ ] Escolher ≥2 vozes para polonês e ≥2 para português na Voice Library e preencher
      `ELEVENLABS_VOICES_PL` / `ELEVENLABS_VOICES_PT` no formato `id:Nome,id:Nome`.
- [ ] Preencher `ELEVENLABS_MODEL`, `ELEVENLABS_MONTHLY_CHARS` e `PRICE_TTS_PER_1K_CHARS` conforme o plano.

## Fatia 6 (deploy) — detalhado depois

Contas gratuitas em Supabase, Render e Vercel.
