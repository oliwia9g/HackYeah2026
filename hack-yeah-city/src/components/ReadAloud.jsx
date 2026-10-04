// Przycisk wyciszenia w rogu + czytnik.
// - Strona główna: czyta nazwy kafelków profili po najechaniu / w fokusie (dla każdego).
// - Po wybraniu profilu osoby niewidomej (albo włączeniu „Czytaj wszystko na głos”) czyta na każdej stronie:
//   przyciski, linki, pola, a po najechaniu także nagłówki, akapity i listy.
// - Czyta też skutek zmian: suwak wielkości liter, tryb wyglądu, kontrast, pola wyboru (np. „Prosty, wybrane”).
import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import Icon from "./Icons";
import { canSpeak, setMuted, speak, useSpeechState } from "../speech";

const INTERACTIVE = "button, a, input, select, textarea, summary, [role='button'], [role='tab']";
const TEXTUAL = "h1, h2, h3, h4, p, li, th, td, dt, dd, caption, figcaption, label";

const clean = (t) => (t || "").replace(/\s+/g, " ").trim().slice(0, 300);

function controlText(target) {
  let text =
    target.getAttribute("aria-label") ||
    (target.labels && target.labels[0] && target.labels[0].innerText) ||
    target.innerText ||
    target.getAttribute("title") ||
    target.getAttribute("placeholder") ||
    "";
  text = clean(text);
  if (target.matches("input[type=checkbox], input[type=radio]")) text += target.checked ? ", zaznaczone" : ", niezaznaczone";
  if (target.getAttribute("aria-pressed") === "true") text += ", włączone";
  if (target.getAttribute("aria-pressed") === "false") text += ", wyłączone";
  if (target.getAttribute("aria-expanded") === "true") text += ", rozwinięte";
  if (target.tagName === "SELECT") text += `, ${target.options[target.selectedIndex]?.text || ""}`;
  if (target.tagName === "INPUT" && ["text", "search", ""].includes(target.type)) text += ", pole tekstowe";
  return text;
}

function labelOf(el, { includeText }) {
  const target = el.closest(INTERACTIVE);
  if (target) return { target, text: controlText(target), interactive: true };
  if (!includeText) return { target: null, text: "" };
  const block = el.closest(TEXTUAL);
  if (!block) return { target: null, text: "" };
  return { target: block, text: clean(block.innerText), interactive: false };
}

export default function ReadAloud() {
  const { muted, autoRead } = useSpeechState();
  const location = useLocation();
  const lastRef = useRef(null);
  const timerRef = useRef(null);
  const onHome = location.pathname === "/";

  // najechanie / fokus
  useEffect(() => {
    if (muted || !canSpeak || !(autoRead || onHome)) return undefined;

    const handle = (event) => {
      const { target, text, interactive } = labelOf(event.target, { includeText: autoRead && event.type === "mouseover" });
      if (!target || !text) return;
      if (!autoRead && !target.closest(".profile-tile")) return;
      if (lastRef.current === target && event.type === "mouseover") return;
      lastRef.current = target;
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => speak(text, { auto: true }), interactive ? 150 : 350);
    };
    document.addEventListener("mouseover", handle);
    document.addEventListener("focusin", handle);
    return () => {
      document.removeEventListener("mouseover", handle);
      document.removeEventListener("focusin", handle);
      clearTimeout(timerRef.current);
    };
  }, [muted, autoRead, onHome]);

  // zmiany ustawień: czytamy nowy stan po tym, jak strona się przerysuje
  useEffect(() => {
    if (muted || !canSpeak || !autoRead) return undefined;
    let t;
    const later = (fn) => {
      clearTimeout(t);
      t = setTimeout(fn, 120);
    };
    const onInput = (e) => {
      const el = e.target;
      if (!(el instanceof HTMLElement)) return;
      if (el.matches("input[type=range]")) {
        later(() => {
          const label = (el.labels && el.labels[0] && clean(el.labels[0].innerText)) || el.getAttribute("aria-label") || "Suwak";
          speak(label, { auto: true });
        });
      } else if (el.matches("input[type=checkbox], input[type=radio], select")) {
        later(() => speak(controlText(el), { auto: true }));
      }
    };
    const onClick = (e) => {
      const btn = e.target instanceof Element ? e.target.closest("button[aria-pressed]") : null;
      if (btn) later(() => speak(controlText(btn), { auto: true }));
    };
    document.addEventListener("input", onInput);
    document.addEventListener("change", onInput);
    document.addEventListener("click", onClick);
    return () => {
      clearTimeout(t);
      document.removeEventListener("input", onInput);
      document.removeEventListener("change", onInput);
      document.removeEventListener("click", onClick);
    };
  }, [muted, autoRead]);

  // przy zmianie strony czyta jej nagłówek (tylko w trybie "czytaj wszystko")
  useEffect(() => {
    if (muted || !autoRead || !canSpeak) return undefined;
    const t = setTimeout(() => {
      const h = document.querySelector("h1");
      if (h) speak(`Strona: ${h.innerText}`, { auto: true });
    }, 600);
    return () => clearTimeout(t);
  }, [location.pathname, muted, autoRead]);

  if (!canSpeak) return null;
  return (
    <button
      type="button"
      className="kbb-mute"
      aria-pressed={muted}
      onClick={() => setMuted(!muted)}
      title={muted ? "Włącz czytanie na głos" : "Wycisz czytanie na głos"}
    >
      <Icon name={muted ? "speakerOff" : "speaker"} />{" "}
      {muted ? "Włącz głos" : "Wycisz głos"}
    </button>
  );
}
