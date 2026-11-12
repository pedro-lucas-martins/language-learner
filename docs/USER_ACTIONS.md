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

## Fatia 2b — avaliar a transcrição com a sua voz (opcional, recomendado)

- [ ] Gravar 6–10 clipes curtos (5–15 s) falando polonês **com erros de propósito** (casos, aspecto,
      gênero) e alguns em português. Qualquer gravador serve (.webm, .ogg, .mp3, .m4a, .wav).
      Salvar em `backend/scripts/stt_clips/` (essa pasta não vai para o git) com um `expected.json`:
      ```json
      [{"file": "pl_01.webm", "target_lang": "pl-PL", "native_lang": "pt-BR",
        "expected": "Ja mam dwa kot.", "mispronounced": []}]
      ```
- [ ] Rodar (mostra o custo estimado — centavos — e pede confirmação):
      ```bash
      cd backend && .venv/bin/python -m scripts.stt_eval
      ```
      Compare "expected" com "got": o ideal é a transcrição manter os seus erros.

## Fatia 2c — testar a voz

**No computador (Chrome):** com `docker compose up`, abra http://localhost:5173.
- [ ] **Segure** o botão do microfone, fale em polonês e solte: a transcrição aparece e a IA responde falando.
- [ ] **Toque** no microfone (toque rápido): liga o modo mãos-livres (botão verde). Fale normalmente; depois
      de ~1 s de silêncio a fala é enviada. Toque de novo para desligar.
- [ ] Enquanto a IA fala, toque/segure o microfone: ela para na hora (interrupção).
- [ ] Nas respostas, ▶ repete o áudio e 0.8× repete mais devagar (sem gastar nada).

**No celular (mesma rede Wi-Fi):**
- [ ] No `.env`, `DEV_EXTRA_ORIGINS` deve ter o endereço do computador na rede, ex.
      `DEV_EXTRA_ORIGINS=https://192.168.1.8:5173` (descubra o IP com `hostname -I`). Depois:
      `docker compose up -d backend`.
- [ ] Troque o frontend do Docker pelo modo HTTPS:
      ```bash
      docker compose stop frontend
      cd frontend && npm install && npm run dev:lan
      ```
- [ ] No celular, abra `https://192.168.1.8:5173`, aceite o aviso de certificado (é o certificado
      local de desenvolvimento) e faça login com o token.
- [ ] Para voltar ao normal: Ctrl+C no `dev:lan` e `docker compose start frontend`.

## Fatia 3 — testar correções e flashcards

- [ ] Abra http://localhost:5173 e fale ou escreva frases **com erros** (3 palavras ou mais). As correções
      aparecem no painel à direita (no celular: botão 📝 com o número de correções novas), explicadas na sua
      língua materna.
- [ ] Toque numa mensagem sua para **corrigir a transcrição**; ao salvar, a gramática é verificada de novo.
- [ ] Em itens de pronúncia: ▶ ouve a palavra certa, 0.8× mais devagar, e **segure 🎙** para tentar de novo.
- [ ] Aba **Flashcards**: revise os cartões (Errei/Difícil/Bom/Fácil). Errou? O cartão volta em 10 minutos.
- [ ] O botão **Eco de pronúncia** no topo liga/desliga o recast (a IA repete certo, sem explicar, a palavra
      que você pronunciou errado).
- [ ] Para testar a direção PL→PT **falando português**, entre com o usuário **Aluno PL** (token em
      `~/language-learner-token-pl.txt`; guarde no gerenciador de senhas e apague o arquivo). A interface e as
      explicações dele já estão em português; o seletor PT/PL no topo troca o idioma.
- [ ] Novos usuários com idioma de interface diferente: `--ui-lang`, ex.
      `docker compose exec backend python -m scripts.create_user --name "Teste" --native pl-PL --ui-lang pt-BR`.

## Depois do benchmark

- [x] Ouvir a comparação às cegas (`bench_results/<data>/index.html`) e ver a latência no `report.md`.
- [x] Escolher `TTS_PROVIDER` (escolhido: `google`, plano gratuito), ajustar `TTS_MONTHLY_CHARS` à cota grátis ou ao plano e `PRICE_TTS_PER_1K_CHARS`.
- [ ] Se for um plano pago (ElevenLabs), deixar **desligada** a cobrança por excedente, se o plano oferecer.
- [x] Anotar resultado e escolha em `docs/DECISIONS.md`.

## Voz atual: ElevenLabs (plano Free)

- [ ] O plano Free dá ~10.000 caracteres por mês; ao chegar em 95% o app troca sozinho para a voz reserva
      (aviso "Voz reserva em uso" no rodapé). A cota renova todo mês.
- [ ] Para uso diário, assine um plano pago do ElevenLabs e depois ajuste no `.env`: `TTS_MONTHLY_CHARS`
      (caracteres do plano) e `PRICE_TTS_PER_1K_CHARS`. Deixe **desligada** a cobrança por excedente, se existir.
      Com plano pago dá para usar vozes nativas da biblioteca (`ELEVENLABS_VOICES_PL/PT`).
- [ ] Para voltar ao Google (grátis até 1M caracteres/mês): `TTS_PROVIDER=google` e `TTS_MONTHLY_CHARS=1000000`,
      depois `docker compose up -d backend`.

## Fatia 6 (deploy) — detalhado depois

Contas gratuitas em Supabase, Render e Vercel.
