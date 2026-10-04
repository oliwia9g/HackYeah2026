// Jednostki w całej aplikacji: odległość w kilometrach, czas w godzinach.
// Czas podajemy też w minutach w nawiasie, bo "0,03 h" samo nic nie mówi.
const dec = (x) => x.toFixed(2).replace(".", ",");

export function km(meters) {
  const m = Number(meters);
  if (!Number.isFinite(m)) return "";
  return `${dec(m / 1000)} km`;
}

export function hours(minutes) {
  const min = Number(minutes);
  if (!Number.isFinite(min)) return "";
  return `${dec(min / 60)} h (${Math.round(min)} min)`;
}

// Zamienia "100 m" / "100 metrów" i "2 min" w tekstach z serwera na km i godziny.
// Używamy tylko do tekstów o trasach (nie do ustawień, np. szerokości przejścia 0,9 m).
const NOT_LETTER = "(?![\\p{L}\\d])";
const METERS = new RegExp(`(\\d+(?:[.,]\\d+)?)\\s*(?:metrów|metry|metr|m)${NOT_LETTER}`, "giu");
const MINUTES = new RegExp(`(\\d+(?:[.,]\\d+)?)\\s*(?:minut|minuty|minutę|min)${NOT_LETTER}`, "giu");

export function L(text) {
  if (typeof text !== "string") return text;
  const num = (s) => parseFloat(s.replace(",", "."));
  return text.replace(METERS, (_, n) => km(num(n))).replace(MINUTES, (_, n) => hours(num(n)));
}
