// Czytanie na głos i rozpoznawanie mowy robi przeglądarka (Web Speech API); na serwer idzie tylko tekst polecenia.
// Stan globalny: "wyciszone" (przycisk w rogu) i "czytaj wszystko" (włączane wyborem profilu osoby niewidomej).
import { useSyncExternalStore } from "react";

export const canSpeak = typeof window !== "undefined" && "speechSynthesis" in window;

const MUTE_KEY = "kbb.muted";
const AUTO_KEY = "kbb.autoread";

function read(key) {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}
function write(key, value) {
  try {
    localStorage.setItem(key, value ? "1" : "0");
  } catch {
    /* tryb prywatny może blokować zapis */
  }
}

let state = { muted: read(MUTE_KEY), autoRead: read(AUTO_KEY) };
const listeners = new Set();

function update(patch) {
  state = { ...state, ...patch };
  listeners.forEach((fn) => fn());
}

export function getSpeechState() {
  return state;
}
export function subscribeSpeech(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
export function useSpeechState() {
  return useSyncExternalStore(subscribeSpeech, getSpeechState, getSpeechState);
}

export function setMuted(muted) {
  write(MUTE_KEY, muted);
  if (muted && canSpeak) window.speechSynthesis.cancel();
  update({ muted });
}
export function setAutoRead(autoRead) {
  write(AUTO_KEY, autoRead);
  update({ autoRead });
}

// auto: true = czytanie "z własnej inicjatywy" (podlega wyciszeniu); bez auto = użytkownik sam kliknął „Przeczytaj”
export function speak(text, { auto = false } = {}) {
  if (!canSpeak || !text) return false;
  if (auto && state.muted) return false;
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
