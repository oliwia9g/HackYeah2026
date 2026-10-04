// Wymagania użytkownika: zapis na urządzeniu + zamiana na parametry API (profiles + prefs).
// Nic z tego nie trafia na serwer poza gotowymi parametrami trasy (FRONTEND.md §13–14).
import { api } from "./api";

export const USER_KEY = "ponadBarieramiUser";
export const GROUP_KEY = "userAccessibilityProfile";
export const UI_KEY = "kbb.ui.v1";

function safeGet(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function safeSet(key, value) {
  try {
    localStorage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}
function safeRemove(key) {
  try {
    localStorage.removeItem(key);
  } catch {
    /* tryb prywatny może blokować zapis */
  }
}

export function readStoredUser() {
  const raw = safeGet(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export const API_GROUPS = [
  "wozek_inwalidzki",
  "wozek_dziecko",
  "niewidomy_slabowidzacy",
  "gluchy_niedoslyszacy",
  "senior",
  "ciaza",
];

// Grupa (klucz API) wybrana na ekranie głównym albo w konfiguracji profilu.
export function readGroup() {
  const user = readStoredUser();
  if (user?.grupa && API_GROUPS.includes(user.grupa)) return user.grupa;
  const raw = safeGet(GROUP_KEY);
  if (!raw) return null;
  let value = raw;
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed === "string") value = parsed;
  } catch {
    /* zwykły tekst */
  }
  return API_GROUPS.includes(value) ? value : null;
}

export function clearStoredRequirements() {
  safeRemove(USER_KEY);
  safeRemove(GROUP_KEY);
}

export function saveGroupOnly(group) {
  // wybór kafelka na ekranie głównym: zerujemy szczegółowe ustawienia, żeby obowiązywały domyślne wartości grupy
  safeRemove(USER_KEY);
  if (group) safeSet(GROUP_KEY, JSON.stringify(group));
}

export function saveUser(data) {
  return safeSet(USER_KEY, JSON.stringify(data));
}

// --- wygląd (tryb standardowy / prosty / skupienia) ---
export const UI_DEFAULT = { mode: "standard", font_scale: 1, contrast: "normalny", voice_replies: false };

export function loadUi() {
  const raw = safeGet(UI_KEY);
  if (!raw) return { ...UI_DEFAULT };
  try {
    const parsed = JSON.parse(raw);
    return {
      mode: ["standard", "prosty", "skupienie"].includes(parsed.mode) ? parsed.mode : "standard",
      font_scale: Math.min(2, Math.max(1, Number(parsed.font_scale) || 1)),
      contrast: parsed.contrast === "wysoki" ? "wysoki" : "normalny",
      voice_replies: Boolean(parsed.voice_replies),
    };
  } catch {
    return { ...UI_DEFAULT };
  }
}

export function saveUi(ui) {
  safeSet(UI_KEY, JSON.stringify(ui));
}

// --- ustawienia ProfileSetup → pozycje katalogu API ---
const BOOL_ITEMS = {
  stairs: "bezSchodow",
  kerb: "niskieKrawedzniki",
  surface: "gladszaNawierzchnia",
  tactile: "prowadzenieDotykowe",
  sound: "sygnalDzwiekowy",
  lit: "oswietlenie",
  toilet: "toaleta",
  lift: "winda",
  changing: "przewijak",
  loop: "petla",
};

// 12% lub więcej = bez ograniczenia (tak jak domyślna wartość suwaka)
export const NO_INCLINE_LIMIT = 12;

// Różnica między tym, co wybrał użytkownik, a domyślnymi pozycjami grupy → listy on/off dla /api/catalog/resolve
export function diffAgainstGroup(preferences, groupDefaults) {
  const defaults = new Set(groupDefaults || []);
  const on = [];
  const off = [];
  const p = preferences || {};

  for (const [id, key] of Object.entries(BOOL_ITEMS)) {
    const wanted = p[key];
    if (wanted === undefined) continue; // starszy zapis bez tego pola: zostają domyślne grupy
    if (wanted && !defaults.has(id)) on.push(id);
    if (!wanted && defaults.has(id)) off.push(id);
  }

  const numeric = [
    ["incline", p.maxNachylenie === undefined ? undefined : p.maxNachylenie < NO_INCLINE_LIMIT, `incline:${p.maxNachylenie}`],
    ["width", p.szerokoscAktywna, `width:${p.szerokoscPrzejscia}`],
    ["bench", p.lawkiAktywne, `bench:${p.lawkaCoXm}`],
  ];
  for (const [id, active, token] of numeric) {
    if (active === undefined) continue;
    if (active) on.push(token);
    else if (defaults.has(id)) off.push(id);
  }
  return { on, off };
}

let catalogCache = null;
export async function getCatalog() {
  if (!catalogCache) catalogCache = await api.catalog();
  return catalogCache;
}

// Zwraca {profiles, prefs, etykieta} gotowe do wstawienia do każdego zapytania.
export async function resolveRequirements() {
  const group = readGroup();
  const user = readStoredUser();
  if (!user?.preferencje) {
    if (!group) return { profiles: "", prefs: "", etykieta: "Pieszy (bez ograniczeń)", group: null, custom: false };
    const res = await api.resolve({ profiles: group });
    return { ...res, group, custom: false };
  }
  const catalog = await getCatalog();
  const defaults = catalog.grupy.find((g) => g.key === group)?.domyslne || [];
  const { on, off } = diffAgainstGroup(user.preferencje, defaults);
  const res = await api.resolve({
    profiles: group || "",
    on: on.join(","),
    off: off.join(","),
  });
  return { ...res, group, custom: on.length + off.length > 0 };
}

// --- plik profilu (konto bez konta): zapis i odczyt ---
export async function buildProfileFile({ name, ui }) {
  const group = readGroup();
  const user = readStoredUser();
  const catalog = await getCatalog();
  const defaults = catalog.grupy.find((g) => g.key === group)?.domyslne || [];
  const { on, off } = diffAgainstGroup(user?.preferencje, defaults);
  return {
    format: "krakow-bez-barier-profil",
    version: 1,
    name: name || "Mój profil",
    groups: group ? [group] : [],
    on,
    off,
    ui: {
      mode: ui.mode,
      font_scale: ui.font_scale,
      contrast: ui.contrast,
      voice_replies: ui.voice_replies,
    },
  };
}

// Odpowiedź /api/profile/validate → ustawienia formularza
export function preferencesFromValidated(result, base) {
  const prof = result.profile || {};
  const active = new Set(result.aktywne || []);
  const tokens = {};
  (prof.on || []).forEach((t) => {
    const [id, value] = String(t).split(":");
    if (value !== undefined) tokens[id] = Number(value);
  });
  const next = { ...base };
  for (const [id, key] of Object.entries(BOOL_ITEMS)) next[key] = active.has(id);
  next.maxNachylenie = active.has("incline") ? tokens.incline ?? 6 : NO_INCLINE_LIMIT;
  next.szerokoscAktywna = active.has("width");
  if (tokens.width !== undefined) next.szerokoscPrzejscia = tokens.width;
  next.lawkiAktywne = active.has("bench");
  if (tokens.bench !== undefined) next.lawkaCoXm = tokens.bench;
  return next;
}
