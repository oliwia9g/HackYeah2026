// Czytanie na głos i rozpoznawanie mowy robi przeglądarka (Web Speech API); na serwer idzie tylko tekst polecenia.
export const canSpeak = typeof window !== "undefined" && "speechSynthesis" in window;

export function speak(text) {
  if (!canSpeak || !text) return false;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "pl-PL";
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
  return true;
}

export function stopSpeaking() {
  if (canSpeak) window.speechSynthesis.cancel();
}

export function createRecognition() {
  const SR = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);
  if (!SR) return null;
  const rec = new SR();
  rec.lang = "pl-PL";
  rec.interimResults = false;
  rec.maxAlternatives = 1;
  return rec;
}
