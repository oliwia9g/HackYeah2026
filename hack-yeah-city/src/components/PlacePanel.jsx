import { useState } from "react";
import { api } from "../api";

const STATUS_WORD = {
  potwierdzone: "potwierdzone",
  prawdopodobne: "prawdopodobne",
  niezweryfikowane: "niezweryfikowane",
  sprzeczne: "sprzeczne",
  brak: "brak danych",
};

function Row({ cls, icon, children }) {
  return (
    <li className={`kbb-item kbb-item-${cls}`}>
      <span className="kbb-ico" aria-hidden="true">{icon}</span>
      <span>{children}</span>
    </li>
  );
}

function Provenance({ item }) {
  const parts = [STATUS_WORD[item.status] || item.status, item.source, item.observed_at].filter(Boolean);
  return <span className="kbb-small kbb-muted"> · {parts.join(", ")}</span>;
}

const REPORT_ATTRS = [
  ["wheelchair", "Wejście / dostęp dla wózka"],
  ["elevator", "Winda"],
  ["ramp:wheelchair", "Rampa dla wózka"],
  ["toilets:wheelchair", "Toaleta dostępna dla wózka"],
];
const REPORT_VALUES = [
  ["yes", "tak"],
  ["no", "nie"],
  ["limited", "częściowo / ograniczony"],
];

function ReportForm({ featureId }) {
  const [attribute, setAttribute] = useState("wheelchair");
  const [value, setValue] = useState("no");
  const [comment, setComment] = useState("");
  const [state, setState] = useState({ busy: false, done: null, error: "" });

  const submit = async (event) => {
    event.preventDefault();
    setState({ busy: true, done: null, error: "" });
    try {
      const result = await api.report({
        feature_id: featureId,
        attribute,
        value,
        comment: comment.trim() || null,
      });
      setState({ busy: false, done: result, error: "" });
    } catch (err) {
      setState({ busy: false, done: null, error: err.message });
    }
  };

  if (state.done) {
    return (
      <div className="kbb-banner kbb-banner-info" role="status">
        Dziękujemy. Zgłoszenie ma status <strong>{state.done.status || "niezweryfikowane"}</strong>: nie zmienia danych
        źródłowych, dopóki ktoś go nie sprawdzi.
        {state.done.osm_edit_url && (
          <>
            {" "}Chcesz poprawić źródło dla wszystkich?{" "}
            <a href={state.done.osm_edit_url} target="_blank" rel="noreferrer">Popraw w OpenStreetMap</a>
          </>
        )}
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="kbb-form kbb-card" aria-label="Zgłoś dostępność">
      <h3>Zgłoś dostępność</h3>
      <label htmlFor="rep-attr">Czego dotyczy zgłoszenie</label>
      <select id="rep-attr" value={attribute} onChange={(e) => setAttribute(e.target.value)} style={{ minHeight: 44, width: "100%" }}>
        {REPORT_ATTRS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
      </select>
      <label htmlFor="rep-val">Jak jest na miejscu</label>
      <select id="rep-val" value={value} onChange={(e) => setValue(e.target.value)} style={{ minHeight: 44, width: "100%" }}>
        {REPORT_VALUES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
      </select>
      <label htmlFor="rep-com">Komentarz (opcjonalnie)</label>
      <input id="rep-com" type="text" maxLength={500} value={comment} onChange={(e) => setComment(e.target.value)} />
      <p className="kbb-small kbb-muted">Zgłoszenia są zawsze niezweryfikowane, dopóki ktoś ich nie sprawdzi.</p>
      <button type="submit" className="kbb-btn kbb-btn-primary" disabled={state.busy}>
        {state.busy ? "Wysyłanie…" : "Wyślij zgłoszenie"}
      </button>
      {state.error && <div className="kbb-banner kbb-banner-error" role="alert">{state.error}</div>}
    </form>
  );
}

// Panel po kliknięciu w mapę (GET /api/at): adres, udogodnienia, bariery, czego nie wiemy
export default function PlacePanel({ info, mode, onRouteHere, onSpeak, onClose, onOpenPlace }) {
  const [showReport, setShowReport] = useState(false);
  if (!info) return null;

  if (!info.inside_area) {
    return (
      <section className="kbb-card" aria-labelledby="place-heading">
        <h2 id="place-heading">Poza obszarem</h2>
        <p>{info.text}</p>
        <button type="button" className="kbb-btn" onClick={onClose}>Zamknij</button>
      </section>
    );
  }

  const place = info.place;
  const title =
    place?.name || (info.found === "budynek" ? "Budynek bez nazwy" : info.found === "obiekt" ? "Obiekt bez nazwy" : "Nic tu nie znaleźliśmy");
  const addr = info.address;
  const simple = mode !== "standard";

  const udogodnienia = simple ? info.udogodnienia.slice(0, 3) : info.udogodnienia;
  const bariery = simple ? info.bariery.slice(0, 3) : info.bariery;

  return (
    <section className="kbb-card" aria-labelledby="place-heading">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
        <h2 id="place-heading">{title}</h2>
        <button type="button" className="kbb-btn" onClick={onClose} aria-label="Zamknij panel miejsca">✕</button>
      </div>

      {addr ? (
        <p>
          {addr.approximate ? (
            <>Najbliższy adres: <strong>{addr.label}</strong> (około {addr.distance_m} m stąd)</>
          ) : (
            <>Adres: <strong>{addr.label}</strong></>
          )}
        </p>
      ) : (
        <p className="kbb-muted">Nie znamy adresu tego miejsca w danych OpenStreetMap.</p>
      )}

      <p>{info.summary?.text}</p>

      <div className="kbb-toolbar">
        <button type="button" className="kbb-btn" onClick={() => onSpeak(info.spoken)}>🔊 Przeczytaj</button>
        {place && (
          <button type="button" className="kbb-btn kbb-btn-primary" onClick={() => onRouteHere(info)}>
            Trasa tutaj
          </button>
        )}
      </div>

      {udogodnienia.length > 0 && (
        <>
          <h3>Udogodnienia</h3>
          <ul className="kbb-list">
            {udogodnienia.map((u) => (
              <Row key={u.attribute} cls="ok" icon="✓">
                <strong>{u.label}</strong>: {u.value_text}<Provenance item={u} />
              </Row>
            ))}
          </ul>
        </>
      )}

      {bariery.length > 0 && (
        <>
          <h3>Bariery</h3>
          <ul className="kbb-list">
            {bariery.map((b) => (
              <Row key={b.attribute} cls="bad" icon="✕">
                <strong>{b.label}</strong>: {b.value_text}<Provenance item={b} />
              </Row>
            ))}
          </ul>
        </>
      )}

      {info.sprzeczne.length > 0 && (
        <>
          <h3>Sprzeczne dane</h3>
          <ul className="kbb-list">
            {info.sprzeczne.map((s) => (
              <Row key={s.attribute} cls="warn" icon="⚠">
                <strong>{s.label}</strong>: źródła się różnią. Pokazujemy obie wersje, nie wybieramy za Ciebie.
                <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                  {(s.versions || []).map((v, i) => (
                    <li key={i}>
                      {v.value} ({STATUS_WORD[v.status] || v.status}) · {v.source}{v.observed_at ? `, ${v.observed_at}` : ""}
                    </li>
                  ))}
                </ul>
              </Row>
            ))}
          </ul>
        </>
      )}

      {!simple && info.informacje.length > 0 && (
        <>
          <h3>Informacje</h3>
          <ul className="kbb-list">
            {info.informacje.map((i) => (
              <Row key={i.attribute} cls="unknown" icon="i">
                <strong>{i.label}</strong>: {i.value_text}<Provenance item={i} />
              </Row>
            ))}
          </ul>
        </>
      )}

      {info.brak_danych.length > 0 && (
        <>
          <h3>Czego nie wiemy</h3>
          <p className="kbb-small kbb-muted">
            {udogodnienia.length + bariery.length === 0
              ? "Nie mamy danych o udogodnieniach ani barierach tego miejsca. Nie zakładamy, że jest dostępne."
              : "Brak danych nie znaczy, że jest dostępne."}
          </p>
          {!simple && (
            <ul className="kbb-list">
              {info.brak_danych.map((b) => (
                <Row key={b.attribute} cls="unknown" icon="?">{b.label}: brak danych</Row>
              ))}
            </ul>
          )}
        </>
      )}

      {!simple && info.fit?.checks?.length > 0 && (
        <>
          <h3>Czy pasuje do Twoich wymagań</h3>
          <p>{info.fit.text}</p>
          <ul className="kbb-list">
            {info.fit.checks.map((c) => (
              <Row
                key={c.attribute}
                cls={c.verdict === "tak" ? "ok" : c.verdict === "nie" ? "bad" : c.verdict === "brak_danych" ? "unknown" : "warn"}
                icon={c.verdict === "tak" ? "✓" : c.verdict === "nie" ? "✕" : c.verdict === "brak_danych" ? "?" : "~"}
              >
                {c.label}: {c.verdict_text}<Provenance item={c} />
              </Row>
            ))}
          </ul>
        </>
      )}

      {!simple && info.w_budynku?.length > 0 && (
        <>
          <h3>W budynku</h3>
          <ul className="kbb-list">
            {info.w_budynku.map((o) => (
              <li key={o.id}>
                <button type="button" className="kbb-btn-link" onClick={() => onOpenPlace(o)}>
                  {o.name || o.category}
                </button>
                {o.wheelchair?.value_text ? ` · dostępność: ${o.wheelchair.value_text}` : ""}
              </li>
            ))}
          </ul>
        </>
      )}

      {!simple && info.w_poblizu?.length > 0 && (
        <>
          <h3>W pobliżu</h3>
          <ul className="kbb-list">
            {info.w_poblizu.map((o) => (
              <li key={o.id}>
                <button type="button" className="kbb-btn-link" onClick={() => onOpenPlace(o)}>
                  {o.name || o.kind}
                </button>
                {` (${o.kind}) · w linii prostej: ${o.distance_m} m`}
                {o.wheelchair?.value_text ? ` · dostępność: ${o.wheelchair.value_text} (${STATUS_WORD[o.wheelchair.status] || o.wheelchair.status})` : ""}
              </li>
            ))}
          </ul>
        </>
      )}

      {!simple && info.nalot?.text && <p className="kbb-small kbb-muted">{info.nalot.text}</p>}

      {!simple && (
        <div className="kbb-toolbar">
          {place && (
            <button type="button" className="kbb-btn" onClick={() => setShowReport((v) => !v)} aria-expanded={showReport}>
              Zgłoś dostępność
            </button>
          )}
          {info.osm_edit_url && (
            <a className="kbb-btn" href={info.osm_edit_url} target="_blank" rel="noreferrer">Popraw w OpenStreetMap</a>
          )}
        </div>
      )}
      {!simple && showReport && place && <ReportForm featureId={place.id} />}
    </section>
  );
}
