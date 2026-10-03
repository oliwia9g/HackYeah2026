export default function RouteForm({ addresses, onAddressesChange, isDarkMode }) {
  return (
    <div className="route-form" data-theme={isDarkMode ? "dark" : "light"}>
      <div className="route-input">
        <label htmlFor="from">
          <span className="route-input-marker route-input-marker-start">A</span>
          <span>Początek</span>
        </label>

        <input
          id="from"
          type="text"
          autoComplete="street-address"
          placeholder="Wpisz adres początkowy"
          value={addresses.from}
          onChange={(event) =>
            onAddressesChange({ ...addresses, from: event.target.value })
          }
        />
      </div>

      <div className="route-input">
        <label htmlFor="to">
          <span className="route-input-marker route-input-marker-end">B</span>
          <span>Cel</span>
        </label>

        <input
          id="to"
          type="text"
          autoComplete="street-address"
          placeholder="Wpisz adres docelowy"
          value={addresses.to}
          onChange={(event) =>
            onAddressesChange({ ...addresses, to: event.target.value })
          }
        />
      </div>
    </div>
  );
}