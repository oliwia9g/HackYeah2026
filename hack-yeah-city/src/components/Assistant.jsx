// Asystent: pole tekstowe + mikrofon + odpowiedź czytana na głos. Polecenie idzie do /api/voice/command jako zwykły tekst.
import { useState } from "react";
import Icon from "./Icons";

export default function Assistant({ onSubmit, reply, heard, micSupported, listening, onMic, onRepeat, big }) {
  const [text, setText] = useState("");
  const submit = (event) => {
    event.preventDefault();
    if (!text.trim()) return;
    onSubmit(text);
    setText("");
  };
  return (
    <section className="kbb-card" aria-labelledby="assistant-heading">
      <h2 id="assistant-heading">Powiedz, czego szukasz</h2>
      <form onSubmit={submit} className="kbb-form">
        <label htmlFor="assistant-input">Na przykład: „jak dojść do toalety” albo „trasa z Rynku Głównego do Dworca Głównego dla wózka”</label>
        <div className="kbb-row">
          <div>
            <input
              id="assistant-input"
              type="text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              autoComplete="off"
            />
          </div>
          <button type="submit" className="kbb-btn kbb-btn-primary">Wyślij</button>
        </div>
      </form>
      <div className="kbb-toolbar" style={{ marginTop: 8 }}>
        {micSupported ? (
          <button
            type="button"
            className={big ? "kbb-btn kbb-btn-primary" : "kbb-btn"}
            onClick={onMic}
            aria-pressed={listening}
            aria-label="Powiedz polecenie"
          >
            <Icon name="mic" /> {listening ? "Słucham…" : "Powiedz polecenie"}
          </button>
        ) : (
          <span className="kbb-small kbb-muted">Ta przeglądarka nie ma rozpoznawania mowy. Wpisz polecenie w pole powyżej.</span>
        )}
        <button type="button" className="kbb-btn" onClick={onRepeat}><Icon name="speaker" /> Powtórz odpowiedź</button>
      </div>
      {micSupported && (
        <p className="kbb-small kbb-muted">
          Uwaga: w niektórych przeglądarkach (np. Chrome) nagranie mowy może być wysyłane do usługi dostawcy przeglądarki.
          Do nas trafia tylko tekst polecenia. Możesz też pisać zamiast mówić.
        </p>
      )}
      {heard && <p className="kbb-small kbb-muted">Usłyszałam: „{heard}”</p>}
      <div role="status" aria-live="polite">{reply && <p><strong>{reply}</strong></p>}</div>
    </section>
  );
}
