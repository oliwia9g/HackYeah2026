import React from "react";

export default function Tile({ icon, title, selected, onClick }) {
  return (
    <button
      type="button"
      className={`profile-tile ${selected ? "selected" : ""}`}
      onClick={onClick}
    >
      <div className="tile-icon">{icon}</div>
      <span>{title}</span>
    </button>
  );
}