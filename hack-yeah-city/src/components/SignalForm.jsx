import { useId, useState } from "react";
import Icon from "./Icons";

const MAX_SIDE = 1280;

// Zmniejsza zdjęcie i zamienia je na JPEG (canvas przy okazji usuwa metadane, np. GPS). Zwraca base64 bez prefiksu.
async function photoToJpegBase64(file) {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((resolve, reject) => {
      const i = new Image();
      i.onload = () => resolve(i);
      i.onerror = () => reject(new Error("Nie udało się odczytać zdjęcia. Wybierz plik JPEG lub PNG."));
      i.src = url;
    });
    const scale = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(img.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
    canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.8);
    return { base64: dataUrl.split(",")[1], preview: dataUrl };
  } finally {
    URL.revokeObjectURL(url);
  }
}

export default function SignalForm({ point, categories, busy, error, onSubmit, onCancel }) {
  const id = useId();
  const [picked, setPicked] = useState("");
  const category = picked || categories?.[0]?.id || "";
  const [description, setDescription] = useState("");
  const [photo, setPhoto] = useState(null); // {base64, preview}
  const [photoAlt, setPhotoAlt] = useState("");
  const [photoError, setPhotoError] = useState("");

  const pickPhoto = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setPhotoError("");
    try {
      setPhoto(await photoToJpegBase64(file));
    } catch (err) {
      setPhoto(null);
      setPhotoError(err.message);
    }
  };

  const submit = (e) => {
    e.preventDefault();
    if (!point) return;
    onSubmit({
      lon: point.lng,
      lat: point.lat,
      category,
      description: description.trim(),
      photo: photo?.base64 || undefined,
      photo_alt: photo ? photoAlt.trim() || undefined : undefined,
    });
  };

  return (
    <section className="kbb-card kbb-signal-form" aria-labelledby="report-heading">
      <h2 id="report-heading">Zgłoś problem w terenie</h2>
      {!point ? (
        <>
          <p role="status">
            <Icon name="pin" /> Kliknij na mapie miejsce, którego dotyczy zgłoszenie.
          </p>
          <button type="button" className="kbb-btn" onClick={onCancel}>Anuluj</button>
        </>
      ) : (
        <form onSubmit={submit}>
          <p className="kbb-small kbb-muted">
            Wybrane miejsce: {point.lat.toFixed(5)}, {point.lng.toFixed(5)}. Możesz kliknąć na mapie inne miejsce.
          </p>

          <label htmlFor={`${id}-cat`} className="kbb-label">Rodzaj problemu</label>
          <select id={`${id}-cat`} className="kbb-input" value={category} onChange={(e) => setPicked(e.target.value)} required>
            {(categories || []).map((c) => (
              <option key={c.id} value={c.id}>{c.label}</option>
            ))}
          </select>

          <label htmlFor={`${id}-desc`} className="kbb-label">Opis: co tu się dzieje?</label>
          <textarea
            id={`${id}-desc`}
            className="kbb-input"
            rows={3}
            maxLength={500}
            minLength={3}
            required
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            aria-describedby={`${id}-count`}
          />
          <p id={`${id}-count`} className="kbb-small kbb-muted">{description.length}/500 znaków</p>

          <label htmlFor={`${id}-photo`} className="kbb-label">Zdjęcie (nieobowiązkowe)</label>
          <input id={`${id}-photo`} className="kbb-input" type="file" accept="image/*" onChange={pickPhoto} />
          {photoError && <p className="kbb-banner kbb-banner-error" role="alert">{photoError}</p>}
          {photo && (
            <div className="kbb-photo-prev">
              <img src={photo.preview} alt="Podgląd wybranego zdjęcia" />
              <label htmlFor={`${id}-alt`} className="kbb-label">Co widać na zdjęciu? (dla osób niewidomych)</label>
              <input id={`${id}-alt`} className="kbb-input" type="text" maxLength={200} value={photoAlt} onChange={(e) => setPhotoAlt(e.target.value)} />
              <button type="button" className="kbb-btn" onClick={() => { setPhoto(null); setPhotoAlt(""); }}>Usuń zdjęcie</button>
            </div>
          )}
          <p className="kbb-small kbb-muted">
            Zdjęcie będzie publiczne. Nie fotografuj twarzy ani tablic rejestracyjnych. Dane lokalizacji ze zdjęcia usuwamy.
            Zgłoszenie jest niezweryfikowane i nie zmienia trasy.
          </p>

          {error && <p className="kbb-banner kbb-banner-error" role="alert">{error}</p>}
          <div className="kbb-toolbar">
            <button type="submit" className="kbb-btn kbb-btn-primary" disabled={busy || !category || description.trim().length < 3}>
              {busy ? "Wysyłanie…" : "Wyślij zgłoszenie"}
            </button>
            <button type="button" className="kbb-btn" onClick={onCancel}>Anuluj</button>
          </div>
        </form>
      )}
    </section>
  );
}
