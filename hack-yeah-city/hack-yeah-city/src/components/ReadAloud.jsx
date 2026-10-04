// Przycisk wyciszenia w rogu + czytnik, który czyta nazwy elementów pod kursorem / w fokusie.
// Na stronie głównej czyta kafelki profili (dla każdego). Po wybraniu profilu osoby niewidomej
// czyta wszystko na każdej stronie (dopóki użytkownik nie wyciszy).
import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { canSpeak, setMuted, speak, useSpeechState } from "../speech";

const INTERACTIVE = "button, a, input, select, textarea, summary, [role='button'], [role='tab']";

function labelOf(el) {
  const target = el.closest(INTERACTIVE);
  if (!target) return { target: null, text: "" };
  let text =
    target.getAttribute("aria-label") ||
    (target.labels && target.labels[0] && target.labels[0].innerText) ||
    target.innerText ||
    target.getAttribute("title") ||
    target.getAttribute("placeholder") ||
    "";
  text = text.replace(/\s+/g, " ").trim().slice(0, 220);
  if (target.matches("input[type=checkbox], input[type=radio]")) text += target.checked ? ", zaznaczone" : ", niezaznaczone";
  if (target.getAttribute("aria-pressed") === "true") text += ", wybrane";
  if (target.tagName === "SELECT") text += `, ${target.options[target.selectedIndex]?.text || ""}`;
  if (target.tagName === "INPUT" && ["text", "search", ""].includes(target.type)) text += ", pole tekstowe";
  return { target, text };
}

export default function ReadAloud() {
  const { muted, autoRead } = useSpeechState();
  const location = useLocation();
  const lastRef = useRef(null);
  const timerRef = useRef(null);
  const onHome = location.pathname === "/";

  // czytnik elementów: wszędzie przy trybie "czytaj wszystko", na stronie głównej tylko kafelki
  useEffect(() => {
    if (muted || !canSpeak || !(autoRead || onHome)) return undefined;

    const handle = (event) => {
      const { target, text } = labelOf(event.target);
      if (!target || !text) return;
      if (!autoRead && !target.closest(".profile-tile")) return;
      if (lastRef.current === target && event.type === "mouseover") return;
      lastRef.current = target;
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => speak(text, { auto: true }), 150);
    };
    document.addEventListener("mouseover", handle);
    document.addEventListener("focusin", handle);
    return () => {
      document.removeEventListener("mouseover", handle);
      document.removeEventListener("focusin", handle);
      clearTimeout(timerRef.current);
    };
  }, [muted, autoRead, onHome]);

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
      <span aria-hidden="true">{muted ? "🔇" : "🔊"}</span>{" "}
      {muted ? "Włącz głos" : "Wycisz głos"}
    </button>
  );
}
