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

## Antes da fatia 2 (voz) — contas gratuitas para o benchmark

Os três provedores serão comparados com `backend/scripts/tts_bench.py`, só com planos gratuitos.
O script mostra quantos caracteres vai gastar e pede confirmação antes de rodar.

- [ ] **Google Cloud Text-to-Speech:** no mesmo projeto do Google Cloud do Gemini, ativar a
      *Cloud Text-to-Speech API*, criar uma *service account* com acesso à API, baixar a chave JSON
      para fora do repositório e apontar `GOOGLE_APPLICATION_CREDENTIALS` para ela.
      Escolher ≥2 vozes Chirp 3 HD em polonês e ≥2 em português (`GOOGLE_TTS_VOICES_PL/PT`).
- [ ] **ElevenLabs (plano Free):** criar conta, gerar API key (`ELEVENLABS_API_KEY`),
      escolher vozes na Voice Library (`ELEVENLABS_VOICES_PL/PT`) e o modelo Flash (`ELEVENLABS_MODEL`).
- [ ] **Cartesia (plano Free):** criar conta, gerar API key (`CARTESIA_API_KEY`),
      escolher vozes polonesas e brasileiras (`CARTESIA_VOICES_PL/PT`) e o modelo Sonic (`CARTESIA_MODEL`).
- [ ] Voice lists no formato `id:Nome,id:Nome`.

## Depois do benchmark

- [ ] Ouvir a comparação às cegas (`bench_results/<data>/index.html`) e ver a latência no `report.md`.
- [ ] Escolher `TTS_PROVIDER`, ajustar `TTS_MONTHLY_CHARS` à cota grátis ou ao plano e `PRICE_TTS_PER_1K_CHARS`.
- [ ] Se for um plano pago (ElevenLabs/Cartesia), deixar **desligada** a cobrança por excedente, se o plano oferecer.
- [ ] Anotar resultado e escolha em `docs/DECISIONS.md`.

## Fatia 6 (deploy) — detalhado depois

Contas gratuitas em Supabase, Render e Vercel.
