import type { Lang } from "./protocol.ts";

/**
 * UI strings. The UI language is the learner's native language (SPEC §1).
 * Both locales must always have the same keys (enforced by the type below).
 */
const ptBR = {
  appTitle: "Parceiro de conversa",
  loginTitle: "Entrar",
  loginTokenLabel: "Token de acesso",
  loginTokenHelp: "O token foi gerado pelo script create_user.py.",
  loginButton: "Entrar",
  loginInvalid: "Token inválido. Confira e tente de novo.",
  loginOrigin: "Este endereço não tem permissão para acessar o servidor.",
  connecting: "Conectando…",
  disconnected: "Conexão perdida.",
  reconnect: "Reconectar",
  logout: "Sair",
  level: "Nível",
  inputPlaceholder: "Escreva sua mensagem…",
  send: "Enviar",
  thinking: "digitando…",
  emptyChat: "Diga oi para começar a conversa!",
  usageMonth: "Gasto estimado no mês",
  mic: "Microfone",
  micHint: "Toque: mãos livres · Segure: falar",
  listening: "Ouvindo… pode falar",
  recording: "Gravando…",
  aiSpeaking: "Falando… toque no microfone para interromper",
  micDenied: "Sem acesso ao microfone. Libere a permissão no navegador.",
  micUnsupported: "Microfone indisponível: abra o app por HTTPS ou em localhost.",
  replay: "Ouvir de novo",
  replaySlow: "Ouvir devagar",
  stopAudio: "Parar áudio",
  metricsVoice: "1ª voz",
  metricsStt: "transcrição",
  metricsTotal: "total",
  metricsLabel: "Última resposta (medido)",
  fallbackVoice: "Voz reserva em uso (cota de voz do mês)",
} as const;

type Strings = { [K in keyof typeof ptBR]: string };

const plPL: Strings = {
  appTitle: "Partner do rozmowy",
  loginTitle: "Zaloguj się",
  loginTokenLabel: "Token dostępu",
  loginTokenHelp: "Token został wygenerowany skryptem create_user.py.",
  loginButton: "Zaloguj",
  loginInvalid: "Nieprawidłowy token. Sprawdź i spróbuj ponownie.",
  loginOrigin: "Ten adres nie ma dostępu do serwera.",
  connecting: "Łączenie…",
  disconnected: "Utracono połączenie.",
  reconnect: "Połącz ponownie",
  logout: "Wyloguj",
  level: "Poziom",
  inputPlaceholder: "Napisz wiadomość…",
  send: "Wyślij",
  thinking: "pisze…",
  emptyChat: "Przywitaj się, aby zacząć rozmowę!",
  usageMonth: "Szacowany koszt w tym miesiącu",
  mic: "Mikrofon",
  micHint: "Dotknij: tryb bez rąk · Przytrzymaj: mów",
  listening: "Słucham… możesz mówić",
  recording: "Nagrywam…",
  aiSpeaking: "Mówię… dotknij mikrofonu, aby przerwać",
  micDenied: "Brak dostępu do mikrofonu. Zezwól na to w przeglądarce.",
  micUnsupported: "Mikrofon niedostępny: otwórz aplikację przez HTTPS lub na localhost.",
  replay: "Odtwórz ponownie",
  replaySlow: "Odtwórz wolniej",
  stopAudio: "Zatrzymaj dźwięk",
  metricsVoice: "pierwszy głos",
  metricsStt: "transkrypcja",
  metricsTotal: "razem",
  metricsLabel: "Ostatnia odpowiedź (zmierzone)",
  fallbackVoice: "Używany jest głos zapasowy (miesięczny limit głosu)",
};

export type StringKey = keyof typeof ptBR;

export const STRINGS: Record<Lang, Strings> = { "pt-BR": ptBR, "pl-PL": plPL };

export function t(lang: Lang, key: StringKey): string {
  return STRINGS[lang][key];
}

/** Before login we do not know the native language: guess from the browser. */
export function detectLang(languages: readonly string[]): Lang {
  for (const tag of languages) {
    const lower = tag.toLowerCase();
    if (lower.startsWith("pl")) return "pl-PL";
    if (lower.startsWith("pt")) return "pt-BR";
  }
  return "pt-BR";
}
