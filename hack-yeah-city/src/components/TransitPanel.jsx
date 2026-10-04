// Komunikacja miejska: przystanki w pobliżu (GET /api/transit/nearby) i plan przejazdu (GET /api/plan).
// Zasady z backendu, które pokazujemy wprost: dostępność PRZYSTANKU nie jest w danych ZTP, a dostępność POJAZDU
// ma źródło (deklaracja MPK, dane na żywo, typ taboru) i nigdy nie jest "potwierdzona" bez dowodu.
import Icon from "./Icons";
import { L, hours, km } from "../format";

const VEHICLE_CLS = { yes: "ok", likely: "ok", unknown: "unknown", conflict: "warn", no: "bad" };

function VehicleBadge({ d }) {
  const text = d.wheelchair_text || "brak danych o dostępności";
  const cls = VEHICLE_CLS[d.wheelchair] || "unknown";
  const mark = cls === "ok" ? "✓" : cls === "bad" ? "✕" : cls === "warn" ? "!" : "?";
  return (
    <span className={`kbb-count kbb-count-${cls === "ok" ? "ok" : cls === "bad" ? "blokada" : cls === "warn" ? "ostrzezenie" : "brak_danych"}`}>
      <b aria-hidden="true">{mark}</b>
      Pojazd: {text}
    </span>
  );
}

function Departure({ d }) {
  return (
    <li className="kbb-dep">
      <strong>
        {d.line} → {d.headsign}
      </strong>{" "}
      o {d.time}
      {typeof d.in_min === "number" && d.in_min < 180 ? `, za ${hours(d.in_min)}` : ""}
      <br />
      <VehicleBadge d={d} />
      {d.wheelchair_basis && <span className="kbb-small kbb-muted"> · {d.wheelchair_basis}</span>}
    </li>
  );
}

function Nearby({ data, onFocus }) {
  const stops = data.stops || [];
  if (!stops.length) {
    return <p>Nie znaleziono przystanków w pobliżu (w obszarze demo).</p>;
  }
  return (
    <div>
      <ol className="kbb-list" style={{ paddingLeft: 0 }}>
        {stops.map((s, i) => {
          const live = s.live?.available ? s.live.departures : null;
          const deps = (live && live.length ? live : s.departures || []).slice(0, 3);
          return (
            <li key={s.id} className="kbb-item kbb-item-unknown" style={{ borderStyle: "solid" }}>
              <span className="kbb-ico" aria-hidden="true">{i + 1}</span>
              <span style={{ flex: 1 }}>
                <strong>{s.name}</strong> <span className="kbb-badge">{s.mode}</span>
                <br />
                <span className="kbb-small">
                  Linie: {(s.lines || []).join(", ") || "brak danych"} · {km(s.distance_m)} od punktu
                </span>
                <br />
                <span className="kbb-small">Przystanek: {s.wheelchair_boarding_text || "brak danych o dostępności"}</span>
                {deps.length > 0 ? (
                  <>
                    <h4 className="kbb-h4">{live && live.length ? "Odjazdy na żywo" : "Odjazdy z rozkładu (nie na żywo)"}</h4>
                    <ul className="kbb-list" style={{ paddingLeft: 0 }}>
                      {deps.map((d, j) => (
                        <Departure key={j} d={d} />
                      ))}
                    </ul>
                  </>
                ) : (
                  <span className="kbb-small kbb-muted"> · brak najbliższych odjazdów w danych</span>
                )}
                {s.live && !s.live.available && s.live.reason && <span className="kbb-small kbb-muted">{s.live.reason}</span>}
                <br />
                <button type="button" className="kbb-btn" style={{ marginTop: 6 }} onClick={() => onFocus(s)}>
                  <Icon name="pin" /> Pokaż na mapie
                </button>
              </span>
            </li>
          );
        })}
      </ol>
      {data.note && <p className="kbb-small kbb-muted">{data.note}</p>}
      {data.accessibility_note && <p className="kbb-small kbb-muted">{data.accessibility_note}</p>}
    </div>
  );
}

function Plan({ data, onFocus }) {
  const options = data.options || [];
  return (
    <div>
      {options.length === 0 && <p>Nie znaleziono przejazdu komunikacją. Poniżej powody; trasa piesza nadal jest w sekcji „Trasy”.</p>}
      <ol className="kbb-list" style={{ paddingLeft: 0 }}>
        {options.map((o, i) => {
          const slower = typeof o.faster_than_walking_min === "number" && o.faster_than_walking_min < 0;
          return (
            <li key={o.id || i} className="kbb-item kbb-item-unknown" style={{ borderStyle: "solid" }}>
              <span className="kbb-ico" aria-hidden="true"><Icon name="bus" /></span>
              <span style={{ flex: 1 }}>
                <strong>{L(o.summary)}</strong>
                <br />
                <span className="kbb-small">
                  Wyjście {o.depart}, odjazd {o.board_departure}, przyjazd {o.arrive} · razem {hours(o.total_min)}, w tym czekanie {hours(o.wait_min)}
                </span>
                <br />
                {typeof o.faster_than_walking_min === "number" && (
                  <span className="kbb-small">
                    {slower
                      ? `Wolniej niż pieszo o ${hours(Math.abs(o.faster_than_walking_min))}.`
                      : `Szybciej niż pieszo o ${hours(o.faster_than_walking_min)}.`}
                  </span>
                )}
                <br />
                {o.ride && <VehicleBadge d={o.ride} />}
                {o.ride?.wheelchair_basis && <span className="kbb-small kbb-muted"> · {o.ride.wheelchair_basis}</span>}
                {o.live_at_board_stop?.available === false && o.live_at_board_stop?.reason && (
                  <span className="kbb-small kbb-muted"> · {o.live_at_board_stop.reason}</span>
                )}
                <br />
                {o.ride?.board_stop && (
                  <button type="button" className="kbb-btn" style={{ marginTop: 6 }} onClick={() => onFocus(o)}>
                    <Icon name="pin" /> Pokaż przystanki na mapie
                  </button>
                )}
              </span>
            </li>
          );
        })}
      </ol>
      {(data.notes || []).map((n, i) => (
        <p key={i} className="kbb-small kbb-muted">{L(n)}</p>
      ))}
      {data.excluded_inaccessible > 0 && (
        <p className="kbb-small kbb-muted">Pominęliśmy {data.excluded_inaccessible} przejazdów pojazdami, które nie są dostępne dla Twoich wymagań.</p>
      )}
      {data.uwaga && <p className="kbb-small kbb-muted">{data.uwaga}</p>}
    </div>
  );
}

export default function TransitPanel({ transit, busy, canPlan, onNearby, onPlan, onFocusStop, onFocusOption }) {
  return (
    <section className="kbb-card" aria-labelledby="transit-heading">
      <h2 id="transit-heading">Komunikacja miejska</h2>
      <p className="kbb-small kbb-muted">
        Przystanki i rozkład pochodzą z danych ZTP Kraków. Dostępności samego przystanku w tych danych nie ma, więc piszemy
        „brak danych”. To nie znaczy „dostępny”.
      </p>
      <div className="kbb-toolbar">
        <button type="button" className="kbb-btn" onClick={onNearby} disabled={busy}>
          <Icon name="bus" /> Przystanki w pobliżu
        </button>
        <button type="button" className="kbb-btn" onClick={onPlan} disabled={busy || !canPlan}>
          <Icon name="walk" /> Przejazd z A do B komunikacją
        </button>
      </div>
      {!canPlan && <p className="kbb-small kbb-muted">Przejazd potrzebuje początku i celu: wpisz adresy albo kliknij dwa punkty na mapie.</p>}
      <div role="status" aria-live="polite">
        {busy && <p>Sprawdzam komunikację…</p>}
        {transit?.kind === "unavailable" && <div className="kbb-banner kbb-banner-info">{transit.message}</div>}
        {transit?.kind === "error" && <div className="kbb-banner kbb-banner-error">{transit.message}</div>}
      </div>
      {transit?.kind === "nearby" && <Nearby data={transit.data} onFocus={onFocusStop} />}
      {transit?.kind === "plan" && <Plan data={transit.data} onFocus={onFocusOption} />}
    </section>
  );
}
