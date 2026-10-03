import { NavLink } from "react-router-dom";

function Navbar({ theme, onToggleTheme }) {
  return (
    <nav className="navbar">
      <NavLink to="/" className="navbar-logo">
        <img src="/logo_ponad_bar.png?v=2" alt="Kraków Bez Barier" />
      </NavLink>

      <div className="navbar-links">
        <NavLink
          to="/"
          className={({ isActive }) =>
            isActive ? "nav-link active" : "nav-link"
          }
        >
          Strona główna
        </NavLink>

        <NavLink
          to="/profil"
          className={({ isActive }) =>
            isActive ? "nav-link active" : "nav-link"
          }
        >
          Profil i Bariery
        </NavLink>

        <NavLink
          to="/mappage"
          className={({ isActive }) =>
            isActive ? "nav-link active" : "nav-link"
          }
        >
          Mapa
        </NavLink>
      </div>
      <button
        type="button"
        className="theme-toggle"
        onClick={onToggleTheme}
        aria-label={theme === "dark" ? "Włącz jasny motyw" : "Włącz ciemny motyw"}
        title={theme === "dark" ? "Włącz jasny motyw" : "Włącz ciemny motyw"}
      >
        {theme === "dark" ? "☀ Jasny" : "◐ Ciemny"}
      </button>
    </nav>
  );
}

export default Navbar;