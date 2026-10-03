export default function Tile({ icon, title, selected, onClick }) {
  return (
    <button
      type="button"
      className={`profile-tile ${selected ? "selected" : ""}`}
      onClick={onClick}
      aria-pressed={selected}
    >
      <div className="tile-icon">
        <img src={icon} alt="" />
      </div>
      <span className="tile-title">{title}</span>
      <span className="tile-selection" aria-hidden="true">
        {selected ? "Wybrany ✓" : "Wybierz"}
      </span>
    </button>
  );
}