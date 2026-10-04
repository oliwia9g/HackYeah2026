// Jedno miejsce z adresem API i wszystkimi wywołaniami backendu "Kraków bez barier".
// Adres ustawiasz w pliku .env.local:  VITE_API=https://twoj-codespace-8000.app.github.dev
// (bez ukośnika na końcu). Bez tej zmiennej używamy adresu zapasowego poniżej.

const FALLBACK_API = "https://cuddly-space-journey-g49vpw47wqwhw7rp-8000.app.github.dev";

export const API = (import.meta.env.VITE_API || FALLBACK_API).replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function detailToText(detail) {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => (typeof d === "string" ? d : d.msg || JSON.stringify(d))).join("; ");
  }
  if (typeof detail === "object") {
    return detail.message || detail.hint || detail.komunikat || JSON.stringify(detail);
  }
  return String(detail);
}

// Przyjazne komunikaty (FRONTEND.md §5)
function friendlyMessage(status, detail) {
  const text = detailToText(detail);
  if (status === 404) return text || "Nie znaleziono. Wpisz ulicę z numerem albo nazwę miejsca.";
  if (status === 422) {
    return text
      ? `${text}`
      : "Ten punkt jest poza obszarem, dla którego mamy dane (Kraków-Śródmieście).";
  }
  if (status === 429) return "Za dużo zgłoszeń naraz. Spróbuj za chwilę.";
  if (status === 503) return "Serwer nie ma teraz danych. Spróbuj za chwilę.";
  return text || `Błąd serwera (${status}).`;
}

function buildUrl(path, params) {
  const url = new URL(API + path);
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    url.searchParams.set(key, String(value));
  });
  return url.toString();
}

async function request(path, params, init) {
  let response;
  try {
    response = await fetch(buildUrl(path, params), init);
  } catch {
    throw new ApiError(
      `Nie można połączyć się z serwerem (${API}). Sprawdź, czy backend działa i czy port 8000 jest ustawiony jako Public.`,
      0
    );
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail ?? body;
    throw new ApiError(friendlyMessage(response.status, detail), response.status, detail);
  }
  return body;
}

const get = (path, params) => request(path, params);

export const api = {
  health: () => get("/api/health"),
  meta: () => get("/api/meta"),
  area: () => get("/api/area"),
  geocode: (q, limit = 1) => get("/api/geocode", { q, limit }),
  routes: (params) => get("/api/routes", params),
  at: (params) => get("/api/at", params),
  nearest: (params) => get("/api/nearest", params),
  whereami: (params) => get("/api/whereami", params),
  voice: (q) => get("/api/voice/command", { q }),
  sources: () => get("/api/sources"),
  stats: () => get("/api/stats"),
  surveys: () => get("/api/surveys"),
  observations: () => get("/api/surveys/observations"),
  catalog: () => get("/api/catalog"),
  resolve: (params) => get("/api/catalog/resolve", params),
  profileSchema: () => get("/api/profile/schema"),
  validateProfile: (profile) =>
    request("/api/profile/validate", null, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(profile),
    }),
  report: (body) =>
    request("/api/reports", null, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  place: (id, params) => get(`/api/places/${encodeURI(id)}`, params),
};

export function embedUrl(placeId, prefs) {
  return buildUrl(`/embed/place/${encodeURI(placeId)}`, { prefs });
}

// --- Pozycja urządzenia (FRONTEND.md §12): zgoda dopiero po kliknięciu, nic nie zapisujemy ---
export function getPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("Ta przeglądarka nie potrafi ustalić lokalizacji. Wskaż miejsce na mapie albo wpisz adres."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (p) =>
        resolve({
          lon: p.coords.longitude,
          lat: p.coords.latitude,
          accuracy_m: Math.round(p.coords.accuracy),
        }),
      (e) => {
        if (e.code === 1) {
          reject(
            new Error(
              "Nie masz włączonej lokalizacji dla tej strony. Możesz wpisać adres albo wskazać miejsce na mapie."
            )
          );
        } else {
          reject(new Error("Nie udało się ustalić, gdzie jesteś. Spróbuj jeszcze raz albo wpisz adres."));
        }
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 }
    );
  });
}
