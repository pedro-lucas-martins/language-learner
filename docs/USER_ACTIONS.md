# Ações do usuário

Tudo o que precisa ser feito à mão (contas, chaves, comandos). Marque conforme for fazendo.

## Fatia 1 — conversar por texto de verdade

- [x] **Gemini:** criar uma API key no Google AI Studio **com faturamento ativado** (tier pago).
      Colocar em `GEMINI_API_KEY` no `.env`.
- [x] **Escolher os modelos** (feito em 12/11/2026: `gemini-3.5-flash-lite` + `gemini-3.1-flash-lite`, já no `.env`) na página de preços do Gemini e preencher `GEMINI_CHAT_MODEL`
      (conversa) e `GEMINI_UTILITY_MODEL` (resumos; também é o fallback), mais os `PRICE_*`.
      `GEMINI_STT_MODEL` só é usado a partir da fatia 2.
      Opcional: `GEMINI_THINKING_LEVEL=MINIMAL` ou `LOW` deixa as respostas mais rápidas
      (só funciona em modelos que aceitam esse ajuste).
      Anotar a escolha e a data na tabela de `docs/DECISIONS.md`.
- [ ] **Alerta de orçamento** no Google Cloud Billing (ex.: alerta em US$ 10).
- [x] Subir tudo: `cp .env.example .env` (se ainda não fez), preencher o Gemini e rodar
      `docker compose up --build`. As migrações do banco rodam sozinhas.
- [x] **Criar seu usuário** (Pedro, pt-BR → pl-PL, A1) (o token aparece uma vez só — guarde num gerenciador de senhas):
      ```bash
      docker compose exec backend python -m scripts.create_user --name "Pedro" --native pt-BR --level A1
      ```
      Para alguém aprendendo português: `--native pl-PL`.
- [ ] Abrir http://localhost:5173, colar o token e conversar.
- [ ] Conferir no GitHub (aba **Actions**) que o CI passou.

## Antes da fatia 2 (voz) — contas gratuitas para o benchmark

Os dois provedores serão comparados com `backend/scripts/tts_bench.py`, só com planos gratuitos.
O script mostra quantos caracteres vai gastar e pede confirmação antes de rodar.

- [x] **Google Cloud Text-to-Speech:** no mesmo projeto do Google Cloud do Gemini, ativar a
      *Cloud Text-to-Speech API*, criar uma *service account* com acesso à API, baixar a chave JSON
      para fora do repositório e apontar `GOOGLE_APPLICATION_CREDENTIALS` para ela.
      Escolher ≥2 vozes Chirp 3 HD em polonês e ≥2 em português (`GOOGLE_TTS_VOICES_PL/PT`).
- [x] **ElevenLabs (plano Free):** criar conta, gerar API key (`ELEVENLABS_API_KEY`),
      escolher vozes na Voice Library (`ELEVENLABS_VOICES_PL/PT`) e o modelo Flash (`ELEVENLABS_MODEL`).
- [x] Voice lists no formato `id:Nome,id:Nome`.

## Fatia 2a — rodar o benchmark de voz

- [x] Com o Docker rodando (o banco precisa estar no ar), na pasta `backend/`:
      ```bash
      .venv/bin/python -m scripts.tts_bench --runs 2
      ```
      Ele mostra quantos caracteres vai gastar (~8.200 por provedor com `--runs 2`) e pede confirmação.
      O plano Free do ElevenLabs tem poucos créditos por mês: prefira `--runs 2`.
      Se ainda não tiver o ambiente: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt`.
- [ ] Observação: no plano Free, o ElevenLabs só usa as vozes padrão pela API (Sarah e George, com sotaque
      neutro). Vozes nativas polonesas e brasileiras da biblioteca exigem plano pago.

## Depois do benchmark

- [x] Ouvir a comparação às cegas (`bench_results/<data>/index.html`) e ver a latência no `report.md`.
- [x] Escolher `TTS_PROVIDER` (escolhido: `google`, plano gratuito), ajustar `TTS_MONTHLY_CHARS` à cota grátis ou ao plano e `PRICE_TTS_PER_1K_CHARS`.
- [ ] Se for um plano pago (ElevenLabs), deixar **desligada** a cobrança por excedente, se o plano oferecer.
- [x] Anotar resultado e escolha em `docs/DECISIONS.md`.

## Fatia 6 (deploy) — detalhado depois

Contas gratuitas em Supabase, Render e Vercel.
