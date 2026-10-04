import { useState } from "react";

const SEVERITY = {
  blokada: { icon: "✕", word: "Przeszkoda", cls: "bad" },
  ostrzezenie: { icon: "!", word: "Utrudnienie", cls: "warn" },
  brak_danych: { icon: "?", word: "Brak danych", cls: "unknown" },
};

const STEP_STATUS = {
  0: { icon: "✓", word: "bez uwag", cls: "ok" },
  1: { icon: "!", word: "uwaga", cls: "warn" },
  2: { icon: "✕", word: "przeszkoda", cls: "bad" },
};

const ARROWS = { start: "↑", prosto: "↑", prawo: "→", lewo: "←", zawroc: "↩", koniec: "⚑" };
const TURN_WORD = { start: "start", prosto: "prosto", prawo: "w prawo", lewo: "w lewo", zawroc: "zawróć", koniec: "cel" };

function Counts({ counts }) {
  const c = counts || {};
  const total = (c.blokada || 0) + (c.ostrzezenie || 0) + (c.brak_danych || 0);
  if (!total) {
    return <p className="kbb-small kbb-muted" style={{ margin: "6px 0 0" }}>Brak przeszkód w naszych danych (to nie gwarancja).</p>;
  }
  return (
    <div className="kbb-counts">
      {["blokada", "ostrzezenie", "brak_danych"].map((key) =>
        c[key] ? (
          <span key={key} className={`kbb-count kbb-count-${key}`}>
            <b aria-hidden="true">{SEVERITY[key].icon}</b>
            {c[key]} {key === "blokada" ? "przeszkód" : key === "ostrzezenie" ? "utrudnień" : "braków danych"}
          </span>
        ) : null
      )}
    </div>
  );
}

function Variants({ routes, selected, onSelect, recommended }) {
  return (
    <ul className="kbb-variants" aria-label="Warianty trasy">
      {routes.map((feature, index) => {
        const p = feature.properties;
        const isRecommended = p.id === recommended || p.recommended;
        return (
          <li key={p.id || index}>
            <button
              type="button"
              className="kbb-variant"
              aria-pressed={index === selected}
              onClick={() => onSelect(index)}
            >
              <span style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                <strong>{p.label}</strong>
                {isRecommended && <span className="kbb-badge">★ Polecana</span>}
              </span>
              <span style={{ display: "block" }}>
                {p.length_m} m · {Math.round(p.time_min)} min
                {p.extra_m > 0 ? ` · o ${p.extra_m} m dłużej niż najkrótsza` : ""}
              </span>
              <Counts counts={p.hazard_counts} />
              {Array.isArray(p.tez_jako) && p.tez_jako.length > 0 && (
                <span className="kbb-small kbb-muted" style={{ display: "block", marginTop: 4 }}>
                  Ta sama trasa jest też jako: {p.tez_jako.join(", ")}
                </span>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function HazardList({ hazards }) {
  if (!hazards?.length) return null;
  return (
    <>
      <h3>Zagrożenia na trasie</h3>
      <ul className="kbb-list">
        {hazards.map((h) => {
          const s = SEVERITY[h.severity] || SEVERITY.ostrzezenie;
          return (
            <li key={h.id ?? `${h.lon}-${h.lat}-${h.text}`} className={`kbb-item kbb-item-${s.cls}`}>
              <span className="kbb-ico" aria-hidden="true">{s.icon}</span>
              <span>
                <strong>{s.word}</strong>
                {h.at_m !== undefined ? `, po ${h.at_m} m` : ""}: {h.text}
                {h.street ? ` (${h.street})` : ""}
                {h.source ? <span className="kbb-small kbb-muted"> · źródło: {h.source}</span> : null}
              </span>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function StepList({ steps }) {
  if (!steps?.length) return null;
  return (
    <>
      <h3>Kroki trasy</h3>
      <ol className="kbb-list" style={{ paddingLeft: 0 }}>
        {steps.map((step, index) => {
          const s = STEP_STATUS[step.status] || STEP_STATUS[0];
          return (
            <li key={index} className={`kbb-item kbb-item-${s.cls}`}>
              <span className="kbb-ico" aria-hidden="true">{s.icon}</span>
              <span>
                <span className="sr-only">{s.word}: </span>
                {step.text}
              </span>
            </li>
          );
        })}
      </ol>
    </>
  );
}

// Widok standardowy: warianty, zagrożenia, kroki
function StandardView({ resp, selected, onSelect, onSpeak }) {
  const route = resp.routes[selected];
  const p = route.properties;
  return (
    <>
      <Variants routes={resp.routes} selected={selected} onSelect={onSelect} recommended={resp.recommended} />
      <div style={{ marginTop: 12 }}>
        {(p.start_label || p.end_label) && (
          <p className="kbb-small kbb-muted">Rozumiem: {p.start_label || "punkt na mapie"} → {p.end_label || "punkt na mapie"}</p>
        )}
        <p className="kbb-small kbb-muted">Wymagania: {p.profile}</p>
        {(p.warnings || []).map((w, i) => (
          <div key={i} className="kbb-banner" role="status">{typeof w === "string" ? w : w.text}</div>
        ))}
        {p.nalot?.text && <p className="kbb-small kbb-muted">{p.nalot.text}</p>}
        <div className="kbb-toolbar">
          <button type="button" className="kbb-btn" onClick={() => onSpeak(p.spoken_summary)}>
            🔊 Przeczytaj trasę
          </button>
        </div>
        <HazardList hazards={p.hazards} />
        <StepList steps={p.steps} />
        {resp.uwaga && <p className="kbb-small kbb-muted">{resp.uwaga}</p>}
      </div>
    </>
  );
}

// Tryb prosty: jeden wariant, duże kroki po jednym zdaniu, „Przeczytaj” przy każdym
function SimpleView({ resp, selected, onSelect, onSpeak }) {
  const [showOthers, setShowOthers] = useState(false);
  const p = resp.routes[selected].properties;
  const simple = p.simple || { summary: p.spoken_summary, steps: [] };
  return (
    <>
      <h2>{simple.summary}</h2>
      <div className="kbb-toolbar">
        <button type="button" className="kbb-btn kbb-btn-primary" onClick={() => onSpeak(p.spoken_summary || simple.summary)}>
          🔊 Przeczytaj
        </button>
        {resp.routes.length > 1 && (
          <button type="button" className="kbb-btn" onClick={() => setShowOthers((v) => !v)} aria-expanded={showOthers}>
            {showOthers ? "Ukryj inne trasy" : "Pokaż inne trasy"}
          </button>
        )}
      </div>
      {showOthers && <Variants routes={resp.routes} selected={selected} onSelect={onSelect} recommended={resp.recommended} />}
      <ol className="kbb-list" style={{ gap: 10, marginTop: 12, paddingLeft: 0 }}>
        {simple.steps.map((step) => (
          <li key={step.n} className="kbb-step-card">
            <span className="kbb-step-n" aria-hidden="true">{step.n}</span>
            <div>
              <div>
                <span className="kbb-arrow" aria-hidden="true">{ARROWS[step.turn] || "↑"}</span>
                <span className="sr-only">Krok {step.n}, {TURN_WORD[step.turn] || ""}. </span>
                {step.text}
              </div>
              {step.warning && (
                <div className="kbb-item kbb-item-warn" style={{ marginTop: 8 }}>
                  <span className="kbb-ico" aria-hidden="true">!</span>
                  <span>{step.warning_text}</span>
                </div>
              )}
              <button type="button" className="kbb-btn" style={{ marginTop: 8 }} onClick={() => onSpeak(step.text)}>
                🔊 Przeczytaj krok
              </button>
            </div>
          </li>
        ))}
      </ol>
      {p.nalot?.text && <p className="kbb-small kbb-muted">{p.nalot.text}</p>}
    </>
  );
}

// Tryb skupienia: tylko bieżący krok, „Dalej / Wstecz / Powtórz”, postęp tekstem
function FocusView({ resp, selected, stepIndex, setStepIndex, onSpeak }) {
  const p = resp.routes[selected].properties;
  const simple = p.simple || { summary: p.spoken_summary, steps: [] };
  const steps = simple.steps;
  if (!steps.length) return <h2>{simple.summary}</h2>;
  const index = Math.min(stepIndex, steps.length - 1);
  const step = steps[index];
  return (
    <>
      <p>{simple.summary}</p>
      <p className="kbb-muted" aria-live="polite">Krok {index + 1} z {steps.length}</p>
      <div className="kbb-step-card" role="group" aria-label={`Krok ${index + 1} z ${steps.length}`}>
        <span className="kbb-step-n" aria-hidden="true">{step.n}</span>
        <div>
          <span className="kbb-arrow" aria-hidden="true">{ARROWS[step.turn] || "↑"}</span>
          {step.text}
          {step.warning && (
            <div className="kbb-item kbb-item-warn" style={{ marginTop: 8 }}>
              <span className="kbb-ico" aria-hidden="true">!</span>
              <span>{step.warning_text}</span>
            </div>
          )}
        </div>
      </div>
      <div className="kbb-toolbar" style={{ marginTop: 12 }}>
        <button type="button" className="kbb-btn" disabled={index === 0} onClick={() => setStepIndex(index - 1)}>Wstecz</button>
        <button type="button" className="kbb-btn kbb-btn-primary" disabled={index >= steps.length - 1} onClick={() => setStepIndex(index + 1)}>Dalej</button>
        <button type="button" className="kbb-btn" onClick={() => onSpeak(step.text)}>🔊 Powtórz</button>
      </div>
    </>
  );
}

export default function RoutePanel({ resp, selected, onSelect, mode, stepIndex, setStepIndex, onSpeak }) {
  if (!resp?.routes?.length) return null;
  return (
    <section className="kbb-card" aria-labelledby="routes-heading">
      {mode === "standard" && <h2 id="routes-heading">Trasy</h2>}
      {mode !== "standard" && <h2 id="routes-heading" className="sr-only">Trasa</h2>}
      {mode === "standard" && <StandardView resp={resp} selected={selected} onSelect={onSelect} onSpeak={onSpeak} />}
      {mode === "prosty" && <SimpleView resp={resp} selected={selected} onSelect={onSelect} onSpeak={onSpeak} />}
      {mode === "skupienie" && (
        <FocusView resp={resp} selected={selected} stepIndex={stepIndex} setStepIndex={setStepIndex} onSpeak={onSpeak} />
      )}
    </section>
  );
}
