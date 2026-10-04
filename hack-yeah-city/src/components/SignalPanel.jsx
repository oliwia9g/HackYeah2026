import { useId, useState } from "react";
import { signalPhotoUrl } from "../api";
import Icon from "./Icons";

const fmtDate = (iso) => {
  try {
    return new Date(iso).toLocaleDateString("pl-PL", { day: "numeric", month: "long", year: "numeric" });
  } catch {
    return iso;
  }
};

// Karta jednego zgłoszenia: opis, zdjęcie, głosy + / − i komentarze
export function SignalPanel({ signal, busy, error, onVote, onComment, onClose }) {
  const id = useId();
  const [text, setText] = useState("");
  if (!signal) return null;

  const send = async (e) => {
    e.preventDefault();
    if (text.trim().length < 2) return;
    const ok = await onComment(text.trim());
    if (ok) setText("");
  };
  const vote = (v) => onVote(signal.my_vote === v ? "none" : v);

  return (
    <section className="kbb-card kbb-signal-card" aria-labelledby="signal-heading">
      <div className="kbb-row-between">
        <h2 id="signal-heading">{signal.category_label}</h2>
        <button type="button" className="kbb-btn" onClick={onClose}>Zamknij</button>
      </div>
      <p className="kbb-small">
        <span className="kbb-badge">{signal.status === "sprawdzone" ? "Sprawdzone przez moderatora" : "Niezweryfikowane"}</span>{" "}
        {signal.demo && <span className="kbb-badge">PRZYKŁADOWE – dane demo</span>}{" "}
        <span className="kbb-muted">Zgłoszono {fmtDate(signal.created_at)}</span>
      </p>
      {signal.questioned && (
        <p className="kbb-banner">Wątpliwe: wielu użytkowników uważa, że to nieaktualne lub nieprawdziwe.</p>
      )}
      <p className="kbb-signal-desc">{signal.description}</p>
      {signal.photo_url && (
        <img className="kbb-signal-photo" src={signalPhotoUrl(signal.photo_url)} alt={signal.photo_alt || "Zdjęcie dołączone do zgłoszenia"} loading="lazy" />
      )}

      <div className="kbb-votes" role="group" aria-label="Oceń zgłoszenie">
        <button type="button" className="kbb-btn kbb-vote" aria-pressed={signal.my_vote === "up"} disabled={busy} onClick={() => vote("up")}>
          <span aria-hidden="true">+</span> Potwierdzam ({signal.up})
        </button>
        <button type="button" className="kbb-btn kbb-vote" aria-pressed={signal.my_vote === "down"} disabled={busy} onClick={() => vote("down")}>
          <span aria-hidden="true">−</span> Nieaktualne ({signal.down})
        </button>
      </div>
      <p className="kbb-small kbb-muted">Głosy nie zmieniają trasy. Pomagają innym ocenić, czy zgłoszeniu można ufać.</p>

      <h3>Komentarze ({signal.comments_count})</h3>
      {signal.comments?.length ? (
        <ul className="kbb-list kbb-comments">
          {signal.comments.map((c) => (
            <li key={c.id} className="kbb-item kbb-item-unknown" style={{ borderStyle: "solid" }}>
              <span>
                {c.text}
                <br />
                <span className="kbb-small kbb-muted">{fmtDate(c.created_at)}</span>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="kbb-small kbb-muted">Nikt jeszcze nie skomentował.</p>
      )}
      <form onSubmit={send}>
        <label htmlFor={`${id}-c`} className="kbb-label">Dodaj komentarz</label>
        <textarea id={`${id}-c`} className="kbb-input" rows={2} maxLength={300} value={text} onChange={(e) => setText(e.target.value)} />
        {error && <p className="kbb-banner kbb-banner-error" role="alert">{error}</p>}
        <div className="kbb-toolbar">
          <button type="submit" className="kbb-btn" disabled={busy || text.trim().length < 2}>Wyślij komentarz</button>
        </div>
      </form>
    </section>
  );
}

// Lista zgłoszeń: odpowiednik pinezek dla osób, które nie korzystają z mapy
export function SignalList({ data, activeId, onOpen }) {
  const items = (data?.features || []).map((f) => f.properties).sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
  if (!items.length) return null;
  return (
    <section className="kbb-card" aria-labelledby="signals-heading">
      <details>
        <summary><h2 id="signals-heading" style={{ display: "inline" }}>Zgłoszenia społeczności ({items.length})</h2></summary>
        <p className="kbb-small kbb-muted">Niezweryfikowane zgłoszenia użytkowników. Nie zmieniają tras.</p>
        <ul className="kbb-list">
          {items.slice(0, 50).map((s) => (
            <li key={s.id}>
              <button type="button" className="kbb-btn kbb-signal-row" aria-pressed={activeId === s.id} onClick={() => onOpen(s.id)}>
                <Icon name="pin" /> {s.category_label}: {s.description.slice(0, 60)}{s.description.length > 60 ? "…" : ""}
                <span className="kbb-small"> (+{s.up} / −{s.down}{s.has_photo ? ", ze zdjęciem" : ""})</span>
              </button>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
