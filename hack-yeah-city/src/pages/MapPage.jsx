import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Icon from "../components/Icons";
import { Link } from "react-router-dom";
import Map from "../components/Map";
import RouteForm from "../components/RouteForm";
import RoutePanel from "../components/RoutePanel";
import PlacePanel from "../components/PlacePanel";
import Assistant from "../components/Assistant";
import TransitPanel from "../components/TransitPanel";
import SignalForm from "../components/SignalForm";
import { SignalList, SignalPanel } from "../components/SignalPanel";
import { L, hours, km } from "../format";
import { API, api, getPosition } from "../api";
import { FONT_SCALES, loadUi, resolveRequirements, saveUi } from "../prefs";
import { canSpeak, createRecognition, setAutoRead, speak, stopSpeaking, useSpeechState } from "../speech";
import "../kbb.css";

const GROUP_ICON = {
  wozek_inwalidzki: "/disabled.png",
  wozek_dziecko: "/little-kid.png",
  niewidomy_slabowidzacy: "/eye.png",
  gluchy_niedoslyszacy: "/ear.png",
  senior: "/old-man.png",
  ciaza: "/pregnant.png",
};

const MODES = [
  ["standard", "Standardowy"],
  ["prosty", "Prosty"],
];

const NEAREST_QUICK = ["toaleta", "lawka", "winda", "apteka"];

const ACC_WORD = {
  potwierdzone: "potwierdzona",
  prawdopodobne: "prawdopodobna",
  niezweryfikowane: "niezweryfikowana",
  sprzeczne: "sprzeczna",
  brak: "brak danych",
};

// po nowym wyniku przewijamy panel do jego karty (tylko wewnątrz panelu, bez przewijania całej strony)
function revealCard(id) {
  setTimeout(() => {
    const el = document.getElementById(id)?.closest("section");
    const box = el?.closest(".kbb-float-body");
    if (!el || !box) return;
    if (getComputedStyle(box).overflowY === "visible") {
      el.scrollIntoView({ block: "start" });
    } else {
      box.scrollTop += el.getBoundingClientRect().top - box.getBoundingClientRect().top - 4;
    }
  }, 80);
}

function coordText(p) {
  return `${p.lng.toFixed(5)}, ${p.lat.toFixed(5)}`;
}

export default function MapPage({ theme }) {
  const mapRef = useRef(null);
  const lastSpokenRef = useRef("");
  const clarifyRef = useRef(null);
  const overrideRef = useRef(null); // wymagania ustawione głosem (tylko do odświeżenia strony)
  const [override, setOverride] = useState(null);
  const reqRef = useRef(null);
  const assistantInputRef = useRef(null);

  const [ui, setUi] = useState(loadUi);
  const [req, setReq] = useState(null);
  const [reqError, setReqError] = useState("");
  const [area, setArea] = useState(undefined);
  const [meta, setMeta] = useState(null);
  const [health, setHealth] = useState(null);
  const [observations, setObservations] = useState(null);
  const [showObs, setShowObs] = useState(false);
  const [showStops, setShowStops] = useState(true);
  const [stopsData, setStopsData] = useState(null); // null = jeszcze nie wiadomo, false = serwer nie ma rozkładu

  const [points, setPoints] = useState({ pointA: null, pointB: null });
  const [addresses, setAddresses] = useState({ from: "", to: "" });
  const [clearVersion, setClearVersion] = useState(0);

  const [resp, setResp] = useState(null);
  const [selected, setSelected] = useState(0);
  const [stepIndex, setStepIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState({ text: "", kind: "info" });
  const [announce, setAnnounce] = useState("");

  const [clickMode, setClickMode] = useState("route"); // "route" | "info" | "report"
  const [signals, setSignals] = useState(null); // zgłoszenia społeczności: null = ładowanie, false = serwer ich nie obsługuje
  const [signalCats, setSignalCats] = useState([]);
  const [showSignals, setShowSignals] = useState(true);
  const [draft, setDraft] = useState(null);
  const [activeSignal, setActiveSignal] = useState(null);
  const [signalBusy, setSignalBusy] = useState(false);
  const [signalError, setSignalError] = useState("");
  const [info, setInfo] = useState(null);
  const [infoClick, setInfoClick] = useState(null);
  const [nearestRes, setNearestRes] = useState(null);
  const [where, setWhere] = useState(null);
  const [transit, setTransit] = useState(null);
  const [transitBusy, setTransitBusy] = useState(false);
  const [posSource, setPosSource] = useState("gps");
  const [showMap, setShowMap] = useState(() => loadUi().mode === "standard");

  const [heard, setHeard] = useState("");
  const [reply, setReply] = useState("");
  const [listening, setListening] = useState(false);

  const isDark = theme === "dark";
  const mode = ui.mode;
  const simpleLike = mode !== "standard";
  // animacje wyłączamy tylko wtedy, gdy system tego chce
  const reduceMotion = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const { autoRead, muted } = useSpeechState();
  const voiceOn = autoRead && !muted;

  // --- układ: pełnoekranowa mapa i pływające karty ---
  // panel zwija się do czasu pojawienia się nowego wyniku (wtedy otwiera się sam)
  const [collapsedSig, setCollapsedSig] = useState(null);
  const [openTool, setOpenTool] = useState(null); // "warstwy" | "wyglad" | null
  const [viewport, setViewport] = useState(() => ({ w: window.innerWidth, h: window.innerHeight, nav: 70 }));
  const toolsRef = useRef(null);
  const floatRef = useRef(null);
  const [sheetH, setSheetH] = useState(0);
  const [toolsH, setToolsH] = useState(56);

  // wysokość dolnego panelu na telefonie: mapa kończy się nad nim, żeby podpis mapy był widoczny
  useEffect(() => {
    const el = floatRef.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => setSheetH(Math.round(el.getBoundingClientRect().height)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const el = toolsRef.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => setToolsH(Math.round(el.getBoundingClientRect().height)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // przycisk „Wycisz głos” (poza tą stroną) ma stać nad dolnym panelem, nie na nim
  useEffect(() => {
    document.documentElement.style.setProperty("--sheet-h", `${sheetH}px`);
    return () => document.documentElement.style.removeProperty("--sheet-h");
  }, [sheetH]);


  useEffect(() => {
    const measure = () => {
      const nav = document.querySelector(".navbar");
      setViewport({ w: window.innerWidth, h: window.innerHeight, nav: nav ? Math.round(nav.getBoundingClientRect().height) : 70 });
    };
    measure();
    window.addEventListener("resize", measure);
    const nav = document.querySelector(".navbar");
    const ro = nav && typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    if (ro) ro.observe(nav);
    return () => {
      window.removeEventListener("resize", measure);
      if (ro) ro.disconnect();
    };
  }, []);

  useEffect(() => {
    if (openTool) document.documentElement.dataset.kbbPop = "1";
    else delete document.documentElement.dataset.kbbPop;
    return () => {
      delete document.documentElement.dataset.kbbPop;
    };
  }, [openTool]);

  useEffect(() => {
    if (!openTool) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") {
        setOpenTool(null);
        toolsRef.current?.querySelector(`[data-tool="${openTool}"]`)?.focus();
      }
    };
    const onDown = (e) => {
      if (toolsRef.current && !toolsRef.current.contains(e.target)) setOpenTool(null);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [openTool]);

  useEffect(() => { if (resp) revealCard("routes-heading"); }, [resp]);
  useEffect(() => { if (info) revealCard("place-heading"); }, [info]);
  useEffect(() => { if (nearestRes || where) revealCard("near-heading"); }, [nearestRes, where]);
  useEffect(() => { if (transit) revealCard("transit-heading"); }, [transit]);
  useEffect(() => { if (activeSignal?.id) revealCard("signal-heading"); }, [activeSignal?.id]);
  useEffect(() => { if (clickMode === "report") revealCard("report-heading"); }, [clickMode]);

  // --- wczytanie danych pomocniczych ---
  useEffect(() => {
    resolveRequirements()
      .then((r) => {
        reqRef.current = r;
        setReq(r);
      })
      .catch((err) => setReqError(err.message));
    api.area().then(setArea).catch(() => setArea(null));
    api.meta().then(setMeta).catch(() => {});
    api.health().then(setHealth).catch(() => {});
    api.transitStops().then(setStopsData).catch(() => setStopsData(false));
    api.signals().then(setSignals).catch(() => setSignals(false));
    api.signalCategories().then((r) => setSignalCats(r.categories || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (!showObs || observations) return;
    api.observations().then(setObservations).catch(() => setObservations({ type: "FeatureCollection", features: [] }));
  }, [showObs, observations]);

  useEffect(() => {
    saveUi(ui);
  }, [ui]);

  // dawny zapis „czytaj odpowiedzi na głos” włącza globalne czytanie
  useEffect(() => {
    if (loadUi().voice_replies) setAutoRead(true);
  }, []);

  useEffect(() => {
    if (showMap) setTimeout(() => mapRef.current?.resize(), 50);
  }, [showMap, mode]);

  const changeMode = (next) => {
    setUi((u) => ({ ...u, mode: next }));
    setShowMap(next === "standard");
    setAnnounce(`Wygląd: ${MODES.find((m) => m[0] === next)[1]}`);
  };

  // --- komunikaty i czytanie ---
  const say = useCallback(
    (text, { force = false } = {}) => {
      if (!text) return;
      setReply(text);
      setAnnounce(text);
      lastSpokenRef.current = text;
      if (force || voiceOn) speak(text, { auto: true });
    },
    [voiceOn]
  );

  const readAloud = (text) => {
    if (!text) return;
    lastSpokenRef.current = text;
    if (!speak(text)) setStatus({ text: "Ta przeglądarka nie czyta na głos.", kind: "error" });
  };

  const setOk = (text) => {
    setStatus({ text, kind: "info" });
    setAnnounce(text);
    if (autoRead) speak(text, { auto: true });
  };
  const setErr = (text) => {
    setStatus({ text, kind: "error" });
    setAnnounce(text);
    if (autoRead) speak(text, { auto: true });
  };

  // --- wymagania (profil + preferencje) ---
  const currentQuery = () => {
    const o = overrideRef.current;
    if (o) return { profiles: o.profiles, prefs: o.prefs };
    const r = reqRef.current;
    return { profiles: r?.profiles || "", prefs: r?.prefs || "" };
  };
  const requirementLabel = override?.label || req?.etykieta || "";

  // --- trasy ---
  const runRoutes = async (params) => {
    setLoading(true);
    setOk("Wyznaczanie trasy…");
    try {
      const base = currentQuery();
      const query = {
        ...params,
        profiles: params.profiles ? params.profiles : base.profiles,
        prefs: params.profiles ? params.prefs || "" : base.prefs,
        simple_steps: mode === "standard" ? 7 : 5,
      };
      const data = await api.routes(query);
      const recommendedIndex = Math.max(
        0,
        data.routes.findIndex((r) => r.properties.id === data.recommended)
      );
      setResp(data);
      setSelected(recommendedIndex);
      setStepIndex(0);
      // trasa z wpisanych adresów: stawiamy A/B tam, gdzie API zrozumiało adresy
      const coords = data.routes[recommendedIndex].geometry?.coordinates || [];
      if (coords.length && mapRef.current && (params.from_q || params.to_q)) {
        const cur = mapRef.current.getPoints();
        const first = coords[0];
        const last = coords[coords.length - 1];
        const a = params.from_q ? { lng: first[0], lat: first[1] } : cur.pointA;
        const b = params.to_q ? { lng: last[0], lat: last[1] } : cur.pointB;
        mapRef.current.setPoints(a, b);
        setPoints({ pointA: a, pointB: b });
      }
      const best = data.routes[recommendedIndex].properties;
      setOk(`Znaleziono ${data.routes.length} ${data.routes.length === 1 ? "wariant" : "warianty"} trasy. Polecana: ${km(best.length_m)}, około ${hours(best.time_min)}.`);
      const summary = L(best.spoken_summary);
      if (voiceOn) speak(summary, { auto: true });
      lastSpokenRef.current = summary;
      return data;
    } catch (err) {
      setResp(null);
      setErr(err.message);
      return null;
    } finally {
      setLoading(false);
    }
  };

  const handlePlanRoute = async () => {
    const fromSpec = addresses.from.trim()
      ? { from_q: addresses.from.trim() }
      : points.pointA
      ? { from_lon: points.pointA.lng, from_lat: points.pointA.lat }
      : null;
    const toSpec = addresses.to.trim()
      ? { to_q: addresses.to.trim() }
      : points.pointB
      ? { to_lon: points.pointB.lng, to_lat: points.pointB.lat }
      : null;
    if (!fromSpec || !toSpec) {
      setErr("Podaj początek i cel: wpisz adresy albo kliknij dwa punkty na mapie.");
      return;
    }
    setInfo(null);
    setNearestRes(null);
    setWhere(null);
    await runRoutes({ ...fromSpec, ...toSpec });
  };

  // --- punkty A/B ---
  const handleAddressesChange = (next) => {
    const fromChanged = next.from !== addresses.from;
    const toChanged = next.to !== addresses.to;
    setAddresses(next);
    setResp(null);
    setStatus({ text: "", kind: "info" });
    if (fromChanged || toChanged) {
      const a = fromChanged ? null : points.pointA;
      const b = toChanged ? null : points.pointB;
      mapRef.current?.setPoints(a, b);
      setPoints({ pointA: a, pointB: b });
    }
  };

  const samePoint = (p, q) => (!p && !q) || (p && q && p.lng === q.lng && p.lat === q.lat);

  const handlePointsChange = (next) => {
    // klik na mapie zastępuje wpisany adres po tej samej stronie
    const aChanged = !samePoint(next.pointA, points.pointA);
    const bChanged = !samePoint(next.pointB, points.pointB);
    setAddresses((old) => ({ from: aChanged ? "" : old.from, to: bChanged ? "" : old.to }));
    setPoints(next);
    setResp(null);
    setStatus({ text: "", kind: "info" });
  };

  const clearAll = () => {
    mapRef.current?.setPoints(null, null);
    setPoints({ pointA: null, pointB: null });
    setAddresses({ from: "", to: "" });
    setResp(null);
    setInfo(null);
    setNearestRes(null);
    setWhere(null);
    setTransit(null);
    setClearVersion((v) => v + 1);
    setStatus({ text: "", kind: "info" });
    stopSpeaking();
  };

  // --- pozycja urządzenia (zgoda dopiero po kliknięciu) lub punkt A jako pozycja symulowana ---
  const getOrigin = async () => {
    if (posSource === "A") {
      if (!points.pointA) throw new Error("Najpierw ustaw punkt A na mapie albo wybierz „Moja lokalizacja”.");
      return { lon: points.pointA.lng, lat: points.pointA.lat, simulated: true };
    }
    return getPosition();
  };

  const useMyLocationAsStart = async () => {
    try {
      setOk("Ustalam, gdzie jesteś…");
      const pos = await getPosition();
      const a = { lng: pos.lon, lat: pos.lat };
      mapRef.current?.setPoints(a, points.pointB);
      setPoints({ pointA: a, pointB: points.pointB });
      setAddresses((old) => ({ ...old, from: "" }));
      setResp(null);
      if (pos.accuracy_m > 50) setOk(`Lokalizacja jest niedokładna (około ${km(pos.accuracy_m)}). Ustawiono punkt A.`);
      else setOk("Punkt A ustawiony na Twoją lokalizację.");
      mapRef.current?.flyTo(pos.lon, pos.lat, 16);
    } catch (err) {
      setErr(err.message);
    }
  };

  // --- klik w mapę: co tu jest? (GET /api/at) ---
  const fetchInfo = async (lon, lat) => {
    setInfoClick({ lon, lat });
    setStatus({ text: "Sprawdzam, co tu jest…", kind: "info" });
    try {
      const q = currentQuery();
      const data = await api.at({ lon, lat, profiles: q.profiles, prefs: q.prefs });
      setInfo(data);
      setNearestRes(null);
      setWhere(null);
      setOk(L(data.text) || "Sprawdzono miejsce.");
      lastSpokenRef.current = L(data.spoken || data.text || "");
      if (voiceOn && data.spoken) speak(L(data.spoken), { auto: true });
    } catch (err) {
      setInfo(null);
      setErr(err.message);
    }
  };

  const handleInfoClick = (coords) => fetchInfo(coords.lng, coords.lat);

  // --- zgłoszenia społeczności ---
  const toggleReport = () => {
    setSignalError("");
    setDraft(null);
    if (clickMode === "report") {
      setClickMode("route");
      return;
    }
    setActiveSignal(null);
    setClickMode("report");
    setAnnounce("Zgłaszanie problemu. Kliknij na mapie miejsce, którego dotyczy zgłoszenie.");
  };
  const handleReportClick = (c) => {
    setDraft(c);
    setSignalError("");
    setAnnounce(`Wybrano miejsce ${c.lat.toFixed(4)}, ${c.lng.toFixed(4)}. Uzupełnij formularz.`);
  };
  const addToSignalList = (sg) =>
    setSignals((cur) => ({
      type: "FeatureCollection",
      count: (cur?.count || 0) + 1,
      features: [...(cur?.features || []), { type: "Feature", geometry: { type: "Point", coordinates: [sg.lon, sg.lat] }, properties: sg }],
    }));
  const patchSignalInList = (sg) =>
    setSignals((cur) =>
      cur
        ? { ...cur, features: cur.features.map((f) => (f.properties.id === sg.id ? { ...f, properties: { ...f.properties, up: sg.up, down: sg.down, comments_count: sg.comments_count, questioned: sg.questioned } } : f)) }
        : cur
    );
  const submitSignal = async (body) => {
    setSignalBusy(true);
    setSignalError("");
    try {
      const res = await api.createSignal(body);
      addToSignalList(res.signal);
      setActiveSignal(res.signal);
      setClickMode("route");
      setDraft(null);
      setShowSignals(true);
      setAnnounce("Zgłoszenie wysłane. Jest niezweryfikowane i nie zmienia trasy.");
    } catch (e) {
      setSignalError(e.message);
    } finally {
      setSignalBusy(false);
    }
  };
  const openSignal = async (id) => {
    setSignalError("");
    try {
      const d = await api.signal(id);
      setActiveSignal(d);
      setClickMode((m) => (m === "report" ? "route" : m));
      setDraft(null);
      mapRef.current?.flyTo(d.lon, d.lat, 18);
    } catch (e) {
      setSignalError(e.message);
    }
  };
  const voteSignal = async (value) => {
    if (!activeSignal) return;
    setSignalBusy(true);
    setSignalError("");
    try {
      const d = await api.voteSignal(activeSignal.id, value);
      setActiveSignal(d);
      patchSignalInList(d);
      setAnnounce(value === "none" ? "Głos cofnięty." : value === "up" ? "Dziękujemy za potwierdzenie." : "Dziękujemy. Zaznaczono, że zgłoszenie jest nieaktualne.");
    } catch (e) {
      setSignalError(e.message);
    } finally {
      setSignalBusy(false);
    }
  };
  const commentSignal = async (text) => {
    if (!activeSignal) return false;
    setSignalBusy(true);
    setSignalError("");
    try {
      const d = await api.commentSignal(activeSignal.id, text);
      setActiveSignal(d);
      patchSignalInList(d);
      setAnnounce("Komentarz dodany.");
      return true;
    } catch (e) {
      setSignalError(e.message);
      return false;
    } finally {
      setSignalBusy(false);
    }
  };

  const openPlaceAt = (o) => {
    if (typeof o.lon !== "number") return;
    mapRef.current?.flyTo(o.lon, o.lat, 18);
    setShowMap(true);
    fetchInfo(o.lon, o.lat);
  };

  // --- „Trasa tutaj” (z panelu miejsca i z wyników „najbliżej”) ---
  const routeTo = async (target, originOverride) => {
    // target: {lon, lat, id?, name?}
    let origin = originOverride;
    if (!origin) {
      if (points.pointA) origin = { lon: points.pointA.lng, lat: points.pointA.lat };
      else if (addresses.from.trim()) origin = null;
      else {
        try {
          origin = await getOrigin();
        } catch (err) {
          setErr(`${err.message} Trasa potrzebuje punktu początkowego.`);
          return;
        }
      }
    }
    const b = { lng: target.lon, lat: target.lat };
    const a = origin ? { lng: origin.lon, lat: origin.lat } : points.pointA;
    mapRef.current?.setPoints(a, b);
    setPoints({ pointA: a, pointB: b });
    setAddresses((old) => ({ from: origin ? "" : old.from, to: "" }));
    const fromSpec = origin ? { from_lon: origin.lon, from_lat: origin.lat } : { from_q: addresses.from.trim() };
    const toSpec = target.id ? { to_place: target.id } : { to_lon: target.lon, to_lat: target.lat };
    await runRoutes({ ...fromSpec, ...toSpec });
  };

  // --- „Najbliżej mnie” (GET /api/nearest) ---
  const runNearest = async (kind, { routeToFirst = false } = {}) => {
    try {
      setOk("Szukam najbliższego miejsca…");
      const pos = await getOrigin();
      const q = currentQuery();
      const data = await api.nearest({ lon: pos.lon, lat: pos.lat, kind, profiles: q.profiles, prefs: q.prefs });
      setNearestRes({ ...data, origin: pos });
      setInfo(null);
      setWhere(null);
      const text = L(data.spoken || data.note || "Nie znaleziono takiego miejsca w pobliżu.");
      setOk(text);
      say(text, { force: routeToFirst });
      mapRef.current?.flyTo(pos.lon, pos.lat, 16);
      if (routeToFirst && data.results?.[0]) await routeTo(data.results[0], pos);
      return data;
    } catch (err) {
      setErr(err.message);
      say(err.message);
      return null;
    }
  };

  // --- „Gdzie jestem” (GET /api/whereami) ---
  const runWhereAmI = async () => {
    try {
      setOk("Sprawdzam, gdzie jesteś…");
      const pos = await getOrigin();
      const data = await api.whereami({ lon: pos.lon, lat: pos.lat, accuracy_m: pos.accuracy_m });
      setWhere({ ...data, pos });
      setNearestRes(null);
      setInfo(null);
      say(L(data.spoken || data.text));
      setOk(L(data.text));
      mapRef.current?.flyTo(pos.lon, pos.lat, 17);
    } catch (err) {
      setErr(err.message);
      say(err.message);
    }
  };

  // --- komunikacja: przystanki w pobliżu i plan przejazdu ---
  const transitProblem = (err) =>
    err.status === 503
      ? {
          kind: "unavailable",
          message:
            "Ten serwer nie ma teraz rozkładu jazdy ZTP, więc nie pokazujemy przystanków ani przejazdów. Trasy piesze działają normalnie. Przystanki pojawią się, gdy serwer pobierze rozkład.",
        }
      : { kind: "error", message: err.message };

  const runTransitNearby = async ({ force = false } = {}) => {
    setTransitBusy(true);
    setTransit(null);
    try {
      const pos = await getOrigin();
      const q = currentQuery();
      const data = await api.transitNearby({ lon: pos.lon, lat: pos.lat, radius: 500, n: 4, only_accessible: false, profiles: q.profiles });
      setTransit({ kind: "nearby", data, origin: pos });
      mapRef.current?.flyTo(pos.lon, pos.lat, 16);
      const first = data.stops?.[0];
      say(
        first
          ? `Najbliższy przystanek: ${first.name}, ${km(first.distance_m)} stąd. Dostępności przystanku nie ma w danych.`
          : "Nie znaleziono przystanków w pobliżu.",
        { force }
      );
    } catch (err) {
      const t = transitProblem(err);
      setTransit(t);
      say(t.message, { force });
    } finally {
      setTransitBusy(false);
    }
  };

  const endpointSpecs = () => {
    const fromSpec = addresses.from.trim()
      ? { from_q: addresses.from.trim() }
      : points.pointA
      ? { from_lon: points.pointA.lng, from_lat: points.pointA.lat }
      : null;
    const toSpec = addresses.to.trim()
      ? { to_q: addresses.to.trim() }
      : points.pointB
      ? { to_lon: points.pointB.lng, to_lat: points.pointB.lat }
      : null;
    return fromSpec && toSpec ? { ...fromSpec, ...toSpec } : null;
  };

  const runTransitPlan = async () => {
    const spec = endpointSpecs();
    if (!spec) {
      setErr("Podaj początek i cel: wpisz adresy albo kliknij dwa punkty na mapie.");
      return;
    }
    setTransitBusy(true);
    setTransit(null);
    try {
      const q = currentQuery();
      const data = await api.plan({ ...spec, profiles: q.profiles, prefs: q.prefs });
      setTransit({ kind: "plan", data });
      const first = data.options?.[0];
      say(first ? L(first.summary) : "Nie znaleziono przejazdu komunikacją. Trasa piesza jest dostępna.");
    } catch (err) {
      const t = transitProblem(err);
      setTransit(t);
      say(t.message);
    } finally {
      setTransitBusy(false);
    }
  };

  const focusStop = (s) => mapRef.current?.flyTo(s.lon, s.lat, 18);
  const focusOption = (o) => {
    const a = o.ride?.board_stop;
    if (a) mapRef.current?.flyTo(a.lon, a.lat, 17);
  };

  // --- asystent głosowy (GET /api/voice/command) ---
  const completeRouteFromVoice = async (params) => {
    const p = { ...params };
    const hasFrom = p.from_lon !== undefined || p.from_q || p.from_place;
    const hasTo = p.to_lon !== undefined || p.to_q || p.to_place;
    if (!hasTo) {
      say("Nie wiem, dokąd iść. Powiedz na przykład: trasa do Dworca Głównego.");
      return;
    }
    if (!hasFrom) {
      try {
        const pos = await getOrigin();
        p.from_lon = pos.lon;
        p.from_lat = pos.lat;
      } catch (err) {
        say(err.message);
        return;
      }
    }
    const a = p.from_lon !== undefined ? { lng: Number(p.from_lon), lat: Number(p.from_lat) } : null;
    const b = p.to_lon !== undefined ? { lng: Number(p.to_lon), lat: Number(p.to_lat) } : null;
    if (a || b) {
      mapRef.current?.setPoints(a, b);
      setPoints({ pointA: a, pointB: b });
      setAddresses({ from: "", to: "" });
    }
    const data = await runRoutes(p);
    if (data) {
      const best = data.routes.find((r) => r.properties.id === data.recommended) || data.routes[0];
      say(`${L(best.properties.spoken_summary)} Powiedz: dalej, powtórz, przeszkody albo stop.`, { force: true });
    }
  };

  const handleClientAction = (r) => {
    const route = resp?.routes?.[selected]?.properties;
    switch (r.client_action) {
      case "repeat":
        readAloud(lastSpokenRef.current || "Nie mam nic do powtórzenia.");
        break;
      case "stop":
        stopSpeaking();
        setListening(false);
        break;
      case "next_step": {
        const steps = route?.simple?.steps || [];
        if (!steps.length) return say("Nie mam teraz trasy. Powiedz, dokąd chcesz iść.");
        const next = Math.min(stepIndex + 1, steps.length - 1);
        setStepIndex(next);
        say(L(steps[next].text), { force: true });
        break;
      }
      case "list_hazards": {
        const list = (route?.hazards || []).filter((h) => h.severity !== "brak_danych");
        if (!route) return say("Nie mam teraz trasy.");
        say(
          list.length
            ? list.map((h) => `Po ${km(h.at_m)}: ${L(h.spoken || h.text)}.`).join(" ")
            : "Na tej trasie nie mamy zapisanych przeszkód. To nie jest gwarancja, że ich nie ma.",
          { force: true }
        );
        break;
      }
      case "remaining":
        say(
          route
            ? `Cała trasa ma około ${km(route.length_m)}. Liczenie, ile zostało, wymaga śledzenia pozycji, którego jeszcze nie mamy.`
            : "Nie mam teraz trasy.",
          { force: true }
        );
        break;
      case "choose": {
        const pending = clarifyRef.current;
        if (!pending) return say("Nie mam teraz nic do wyboru.", { force: true });
        const choice = pending.clarify.choices[(r.index || 1) - 1];
        if (!choice) return say("Nie ma takiego numeru. Powiedz numer z listy.", { force: true });
        clarifyRef.current = null;
        completeRouteFromVoice({
          ...pending.call.params,
          [`${pending.clarify.slot}_lon`]: choice.lon,
          [`${pending.clarify.slot}_lat`]: choice.lat,
        });
        break;
      }
      case "confirm":
        say("Dobrze.", { force: true });
        break;
      case "deny":
        say("Dobrze. Powiedz, jaką grupę wybrać, na przykład: z wózkiem dziecięcym.", { force: true });
        break;
      default:
        break;
    }
  };

  const handleUtterance = async (text, { spoken = false } = {}) => {
    const clean = text.trim();
    if (!clean) return;
    setHeard(clean);
    try {
      const r = await api.voice(clean);
      if (r.client_action) {
        handleClientAction(r);
        return;
      }
      const force = spoken;
      switch (r.intent) {
        case "set_profile":
          overrideRef.current = {
            profiles: r.set.profiles || "",
            prefs: r.set.prefs || "",
            label: `ustawione głosem: ${r.set.profiles || "własne preferencje"}`,
          };
          setOverride(overrideRef.current);
          say(L(r.reply), { force });
          break;
        case "clarify":
          clarifyRef.current = r;
          say(L(r.reply), { force });
          break;
        case "route":
          say(L(r.reply), { force });
          await completeRouteFromVoice({ ...r.call.params });
          break;
        case "nearest":
          await runNearest(r.kind, { routeToFirst: Boolean(r.route_to_first) });
          break;
        case "where_am_i":
          await runWhereAmI();
          break;
        case "transit_nearby":
          await runTransitNearby({ force });
          break;
        default:
          say(L(r.reply), { force });
      }
    } catch (err) {
      say(err.message);
      setErr(err.message);
    }
  };

  const startListening = () => {
    const rec = createRecognition();
    if (!rec) return;
    stopSpeaking();
    rec.onresult = (e) => handleUtterance(e.results[0][0].transcript, { spoken: true });
    rec.onerror = () => {
      setListening(false);
      say("Nie udało się usłyszeć polecenia. Możesz je wpisać w polu tekstowym.");
    };
    rec.onend = () => setListening(false);
    setListening(true);
    rec.start();
  };

  // --- piny na mapie ---
  const pins = useMemo(() => {
    const list = [];
    if (infoClick && info?.inside_area) {
      list.push({
        key: "info",
        kind: "info",
        lon: infoClick.lon,
        lat: infoClick.lat,
        label: "i",
        aria: "Sprawdzane miejsce",
        title: "Sprawdzane miejsce",
      });
    }
    if (nearestRes) {
      if (nearestRes.origin) {
        list.push({
          key: "origin",
          kind: "me",
          lon: nearestRes.origin.lon,
          lat: nearestRes.origin.lat,
          label: "•",
          aria: nearestRes.origin.simulated ? "Pozycja symulowana (punkt A)" : "Twoja pozycja",
          title: "Punkt, od którego liczymy",
        });
      }
      (nearestRes.results || []).forEach((r, i) =>
        list.push({
          key: r.id,
          kind: "nearest",
          lon: r.lon,
          lat: r.lat,
          label: String(i + 1),
          aria: `${i + 1}. ${r.name}, ${km(r.walk_m)} chodnikami`,
          title: `${i + 1}. ${r.name}`,
          result: r,
        })
      );
    }
    if (transit?.kind === "nearby") {
      (transit.data.stops || []).forEach((st, i) =>
        list.push({
          key: `stop-${st.id}`,
          kind: "stop",
          lon: st.lon,
          lat: st.lat,
          label: String(i + 1),
          aria: `Przystanek ${i + 1}: ${st.name}, ${km(st.distance_m)}`,
          title: `Przystanek ${st.name}`,
        })
      );
    }
    if (transit?.kind === "plan") {
      (transit.data.options || []).slice(0, 3).forEach((o, i) => {
        [["board", o.ride?.board_stop, "Wsiadasz"], ["alight", o.ride?.alight_stop, "Wysiadasz"]].forEach(([k, st, word]) => {
          if (st) {
            list.push({
              key: `plan-${i}-${k}`,
              kind: "stop",
              lon: st.lon,
              lat: st.lat,
              label: k === "board" ? "W" : "Z",
              aria: `${word} na przystanku ${st.name} (przejazd ${i + 1})`,
              title: `${word}: ${st.name}`,
            });
          }
        });
      });
    }
    if (where?.pos) {
      list.push({
        key: "where",
        kind: "me",
        lon: where.pos.lon,
        lat: where.pos.lat,
        label: "•",
        aria: "Twoja pozycja",
        title: "Twoja pozycja",
      });
    }
    return list;
  }, [info, infoClick, nearestRes, where, transit]);

  const handlePinClick = (pin) => {
    if (pin.result) openPlaceAt(pin.result);
  };

  const selectedRoute = resp?.routes?.[selected];
  const hazards = selectedRoute?.properties?.hazards || [];
  const isReady =
    Boolean(addresses.from.trim() || points.pointA) && Boolean(addresses.to.trim() || points.pointB);
  const micSupported = typeof window !== "undefined" && Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
  const kinds = meta?.rodzaje_udogodnien || {};

  const focusAssistant = () => {
    assistantInputRef.current?.scrollIntoView?.({ behavior: reduceMotion ? "auto" : "smooth" });
    document.getElementById("assistant-input")?.focus();
  };

  const nearestKinds = simpleLike
    ? NEAREST_QUICK.filter((k) => kinds[k] || !meta).slice(0, 2)
    : Object.keys(kinds).length
    ? Object.keys(kinds)
    : NEAREST_QUICK;

  // --- widok ---
  const fontIndex = Math.max(0, FONT_SCALES.indexOf(ui.font_scale));
  const groupIcon = req?.group ? GROUP_ICON[req.group] : null;
  const noMap = simpleLike && !showMap;
  const wide = viewport.w > 900;
  const panelW = Math.round(Math.min(Math.max(380, 380 * ui.font_scale), 560, viewport.w * 0.6));
  const sig = [resp, info, nearestRes, where, transit, activeSignal, clickMode === "report"];
  const panelOpen = !(collapsedSig && collapsedSig.every((v, i) => v === sig[i]));
  const insets = wide
    ? { top: 64, left: panelOpen ? panelW + 28 : 16, right: 16, bottom: 40 }
    : { top: 64, left: 0, right: 0, bottom: 0 };
  const mapStyle = noMap ? { display: "none" } : wide ? undefined : { bottom: sheetH };
  const toggleTool = (name) => setOpenTool((cur) => (cur === name ? null : name));

  const lookEl = (
    <section id="tool-wyglad" className="kbb-pop" aria-labelledby="look-heading">
      <h2 id="look-heading" className="kbb-look-title">Wygląd strony</h2>
      <div className="kbb-toolbar" role="group" aria-label="Tryb wyglądu">
        {MODES.map(([key, label]) => (
          <button key={key} type="button" className="kbb-btn" aria-pressed={mode === key} onClick={() => changeMode(key)}>
            {label}
          </button>
        ))}
        <button
          type="button"
          className="kbb-btn"
          aria-pressed={ui.contrast === "wysoki"}
          onClick={() => setUi((u) => ({ ...u, contrast: u.contrast === "wysoki" ? "normalny" : "wysoki" }))}
        >
          Wysoki kontrast
        </button>
        {canSpeak && (
          <button
            type="button"
            className="kbb-btn"
            aria-pressed={autoRead}
            onClick={() => {
              setAutoRead(!autoRead);
              setUi((u) => ({ ...u, voice_replies: !autoRead }));
            }}
          >
            <Icon name="speaker" /> Czytaj wszystko na głos
          </button>
        )}
      </div>
      <div className="kbb-fontbox">
        <label htmlFor="font-scale">
          Wielkość liter: <strong>{Math.round(ui.font_scale * 100)}%</strong>
        </label>
        <input
          id="font-scale"
          type="range"
          min="0"
          max="3"
          step="1"
          value={fontIndex}
          onChange={(e) => setUi((u) => ({ ...u, font_scale: FONT_SCALES[Number(e.target.value)] }))}
          aria-valuetext={`${Math.round(ui.font_scale * 100)} procent`}
        />
        <div className="kbb-ticks" aria-hidden="true">
          <span>100%</span><span>125%</span><span>150%</span><span>175%</span>
        </div>
      </div>
    </section>
  );

  const legendEl = (
    <>
      <ul className="kbb-legend" aria-label="Legenda mapy">
        <li><span className="kbb-legend-area" aria-hidden="true" /> Jaśniejszy obszar z fioletowym obrysem to <strong>obszar demo</strong> (Kraków-Śródmieście), jedyny z danymi. Reszta jest przyciemniona.</li>
        {signals ? (
          <li><span className="kbb-signal kbb-legend-stop" aria-hidden="true">!</span> zgłoszenie społeczności, <strong>niezweryfikowane</strong> ({signals.count}); nie zmienia trasy</li>
        ) : null}
        {stopsData ? (
          <li><span className="kbb-stop kbb-stop-tram kbb-legend-stop" aria-hidden="true">T</span> przystanek tramwajowy <span className="kbb-stop kbb-stop-bus kbb-legend-stop" aria-hidden="true">A</span> przystanek autobusowy ({stopsData.count} w obszarze, z rozkładu ZTP)</li>
        ) : stopsData === false ? (
          <li>Przystanków nie pokazujemy: serwer nie ma teraz rozkładu jazdy ZTP.</li>
        ) : null}
      </ul>
      <p className="kbb-small kbb-muted kbb-mapnote">
        Mapa jest dodatkiem: wszystko, co widać na niej, jest też w listach w panelu (kroki, zagrożenia, wyniki).
      </p>
    </>
  );

  const layersEl = (
    <section id="tool-warstwy" className="kbb-pop" aria-labelledby="layers-heading">
      <h2 id="layers-heading" className="kbb-look-title">Warstwy mapy</h2>
      <label className="kbb-check">
        <input type="checkbox" checked={showObs} onChange={(e) => setShowObs(e.target.checked)} />
        Obserwacje z nalotu
      </label>
      <label className="kbb-check">
        <input type="checkbox" checked={showSignals} onChange={(e) => setShowSignals(e.target.checked)} disabled={signals === false} />
        Zgłoszenia społeczności
      </label>
      <label className="kbb-check">
        <input type="checkbox" checked={showStops} onChange={(e) => setShowStops(e.target.checked)} disabled={stopsData === false} />
        Przystanki
      </label>
      <Link className="kbb-btn-link" to="/dane">Źródła i aktualność danych</Link>
      <div className="kbb-pop-legend">{legendEl}</div>
    </section>
  );

  return (
    <main
      className="kbb kbb-app"
      data-theme={isDark ? "dark" : "light"}
      data-contrast={ui.contrast}
      data-mode={mode}
      data-motion={reduceMotion ? "reduced" : "normal"}
      style={{ "--font-scale": ui.font_scale, "--nav-h": `${viewport.nav}px`, "--panel-w": `${panelW}px`, "--tools-h": `${toolsH}px` }}
    >
      <div className={`kbb-stage${noMap ? " kbb-stage-nomap" : ""}${panelOpen ? "" : " kbb-panel-closed"}`}>
        <div className="kbb-tools" ref={toolsRef}>
          {!noMap && (
            <div className="kbb-seg" role="group" aria-label="Mapa: co robi klik">
              <button type="button" className="kbb-btn" aria-pressed={clickMode === "route"} onClick={() => setClickMode("route")}>
                Klik ustawia trasę (A, B)
              </button>
              <button type="button" className="kbb-btn" aria-pressed={clickMode === "info"} onClick={() => setClickMode("info")}>
                Klik sprawdza miejsce
              </button>
            </div>
          )}
          {!noMap && (
            <button
              type="button"
              className="kbb-btn kbb-btn-primary kbb-toolbtn"
              aria-pressed={clickMode === "report"}
              disabled={signals === false}
              title={signals === false ? "Ten serwer nie obsługuje zgłoszeń" : undefined}
              onClick={toggleReport}
            >
              <Icon name="pin" /> Zgłoś problem
            </button>
          )}
          {!noMap && (
            <button
              type="button"
              className="kbb-btn kbb-toolbtn"
              data-tool="warstwy"
              aria-expanded={openTool === "warstwy"}
              aria-controls="tool-warstwy"
              onClick={() => toggleTool("warstwy")}
            >
              Warstwy i legenda
            </button>
          )}
          <button
            type="button"
            className="kbb-btn kbb-toolbtn"
            data-tool="wyglad"
            aria-expanded={openTool === "wyglad"}
            aria-controls="tool-wyglad"
            onClick={() => toggleTool("wyglad")}
          >
            Wygląd strony
          </button>
          {openTool === "warstwy" && layersEl}
          {openTool === "wyglad" && lookEl}
        </div>

        <div className="kbb-float" ref={floatRef}>
          <div className="kbb-card kbb-float-head">
            <div className="kbb-float-title">
              <p className="eyebrow">Kraków Bez Barier</p>
              <h1>Zaplanuj trasę</h1>
            </div>
            {!noMap && (
            <button
                type="button"
                className="kbb-btn kbb-collapse"
                aria-expanded={panelOpen}
                aria-controls="kbb-panel-body"
                onClick={() => setCollapsedSig(panelOpen ? sig : null)}
              >
                {panelOpen ? "Zwiń panel" : "Pokaż panel"}
              </button>
            )}
          </div>

          <div id="kbb-panel-body" className="kbb-float-body" hidden={!panelOpen}>
            {/* Stan systemu */}
            {health?.status === "czesciowo" && (
              <div className="kbb-banner" role="status">
                <strong>Część danych chwilowo niedostępna.</strong>{" "}
                {(health.niedostepne || []).map((k) => health.co_widzi_uzytkownik?.[k]).filter(Boolean).join("; ")}
              </div>
            )}
            {reqError && (
              <div className="kbb-banner kbb-banner-error" role="alert">
                {reqError} (adres API: {API})
              </div>
            )}

            {/* Zgłoszenia społeczności */}
            {clickMode === "report" && (
              <SignalForm point={draft} categories={signalCats} busy={signalBusy} error={signalError} onSubmit={submitSignal} onCancel={toggleReport} />
            )}
            {activeSignal && clickMode !== "report" && (
              <SignalPanel signal={activeSignal} busy={signalBusy} error={signalError} onVote={voteSignal} onComment={commentSignal} onClose={() => { setActiveSignal(null); setSignalError(""); }} />
            )}

            {/* Kafelki w trybie prostym */}
            {simpleLike && (
              <section className="kbb-card" aria-labelledby="tiles-heading">
                <h2 id="tiles-heading">Co chcesz zrobić?</h2>
                <div className="kbb-tiles">
                  <button type="button" className="kbb-tile" onClick={() => document.getElementById("from")?.focus()}>
                    <Icon name="walk" className="kbb-tile-svg" />Dokąd idę?
                  </button>
                  <button type="button" className="kbb-tile" onClick={() => runNearest("toaleta")}>
                    <Icon name="wc" className="kbb-tile-svg" />Najbliższa toaleta
                  </button>
                  <button type="button" className="kbb-tile" onClick={() => runNearest("lawka")}>
                    <Icon name="bench" className="kbb-tile-svg" />Najbliższa ławka
                  </button>
                  <button type="button" className="kbb-tile" onClick={runWhereAmI}>
                    <Icon name="here" className="kbb-tile-svg" />Gdzie jestem?
                  </button>
                  <button type="button" className="kbb-tile" onClick={micSupported ? startListening : focusAssistant}>
                    <Icon name="mic" className="kbb-tile-svg" />Powiedz, czego szukasz
                  </button>
                  <Link className="kbb-tile" to="/">
                    {groupIcon ? <img className="kbb-tile-img" src={groupIcon} alt="" /> : <Icon name="person" className="kbb-tile-svg" />}
                    Mój profil
                  </Link>
                  <button type="button" className="kbb-tile" onClick={() => setShowMap((v) => !v)} aria-pressed={showMap}>
                    <Icon name="map" className="kbb-tile-svg" />{showMap ? "Ukryj mapę" : "Pokaż mapę"}
                  </button>
                </div>
              </section>
            )}

            {/* Skąd / dokąd */}
            <section className="kbb-card kbb-search" aria-labelledby="form-heading">
              <h2 id="form-heading">Dokąd idziesz?</h2>
              <p className="kbb-small kbb-muted kbb-lead">
                Mapa, która mówi, czego jeszcze nie wie. Brak danych nigdy nie oznacza „dostępne”.
              </p>
              <div className="kbb-req">
                {groupIcon && <img className="kbb-req-img" src={groupIcon} alt="" />}
                <p>
                  <span className="kbb-small kbb-muted">Twoje wymagania</span>
                  <br />
                  <strong>{requirementLabel || (reqError ? "Nie udało się ustalić." : "Ładowanie…")}</strong>
                </p>
                <Link className="kbb-btn" to="/profil">Zmień</Link>
              </div>
              {req?.group === null && !override && (
                <p className="kbb-small kbb-muted">Nie wybrano żadnych wymagań, więc trasa nie omija żadnych barier.</p>
              )}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handlePlanRoute();
                }}
              >
                <RouteForm addresses={addresses} onAddressesChange={handleAddressesChange} isDarkMode={isDark} />
                <div className="kbb-toolbar" style={{ marginTop: 10 }}>
                  <button type="submit" className="kbb-btn kbb-btn-primary" disabled={!isReady || loading}>
                    {loading ? "Wyznaczanie trasy…" : "Wyznacz trasę"}
                  </button>
                  <button type="button" className="kbb-btn" onClick={clearAll}>Wyczyść</button>
                </div>
              </form>
              <div role="status" aria-live="polite">
                {status.text && (
                  <div className={`kbb-banner ${status.kind === "error" ? "kbb-banner-error" : "kbb-banner-info"}`}>{status.text}</div>
                )}
                {!status.text && !isReady && (
                  <p className="kbb-small kbb-muted">
                    Wpisz adresy albo kliknij na mapie punkt startowy (A), a potem docelowy (B).
                  </p>
                )}
              </div>
              <div className="kbb-small kbb-muted">
                <div>Punkt początkowy: {points.pointA ? coordText(points.pointA) : addresses.from.trim() ? "z wpisanego adresu" : "nie wybrano"}</div>
                <div>Punkt końcowy: {points.pointB ? coordText(points.pointB) : addresses.to.trim() ? "z wpisanego adresu" : "nie wybrano"}</div>
              </div>

              {/* Najbliżej mnie: szybkie przyciski */}
              <div className="kbb-chips" role="group" aria-label="Najbliżej mnie">
                {nearestKinds.map((k) => (
                  <button key={k} type="button" className="kbb-btn kbb-chip" onClick={() => runNearest(k)}>
                    {kinds[k] || k}
                  </button>
                ))}
                <button type="button" className="kbb-btn kbb-chip" onClick={useMyLocationAsStart}><Icon name="here" /> Moja lokalizacja jako A</button>
                <button type="button" className="kbb-btn kbb-chip" onClick={runWhereAmI}><Icon name="here" /> Gdzie jestem?</button>
                <button type="button" className="kbb-btn kbb-chip" onClick={micSupported ? startListening : focusAssistant}>
                  <Icon name="mic" /> Powiedz
                </button>
              </div>
              <div className="kbb-toolbar kbb-from" role="group" aria-label="Skąd liczyć odległość">
                <span className="kbb-small">Liczę od:</span>
                <button type="button" className="kbb-btn kbb-chip" aria-pressed={posSource === "gps"} onClick={() => setPosSource("gps")}>
                  Moja lokalizacja
                </button>
                <button type="button" className="kbb-btn kbb-chip" aria-pressed={posSource === "A"} onClick={() => setPosSource("A")}>
                  Punkt A
                </button>
              </div>
              <p className="kbb-small kbb-muted">
                Zgodę na lokalizację przeglądarka zapyta dopiero po kliknięciu. Pozycji nigdzie nie zapisujemy.
              </p>
            </section>

            <RoutePanel
              resp={resp}
              selected={selected}
              onSelect={(i) => {
                setSelected(i);
                setStepIndex(0);
              }}
              mode={mode}
              onSpeak={readAloud}
            />

            <PlacePanel
              info={info}
              mode={mode}
              onSpeak={readAloud}
              onClose={() => {
                setInfo(null);
                setInfoClick(null);
              }}
              onRouteHere={(data) => routeTo({ lon: data.place.lon, lat: data.place.lat, id: data.place.id, name: data.place.name })}
              onOpenPlace={openPlaceAt}
            />

            {/* Wyniki „najbliżej mnie” i „gdzie jestem” */}
            {(where || nearestRes) && (
              <section className="kbb-card" aria-labelledby="near-heading">
                <h2 id="near-heading">Najbliżej mnie</h2>

                {where && (
                  <div className="kbb-banner kbb-banner-info" role="status">
                    <p style={{ margin: 0, fontSize: "1.15em" }}>{L(where.text)}</p>
                    {where.accuracy_m > 50 && <p className="kbb-small">Lokalizacja jest niedokładna (około {km(where.accuracy_m)}).</p>}
                    {where.pos?.simulated && <p className="kbb-small">To pozycja z punktu A na mapie, nie z GPS.</p>}
                    {where.nearby?.length > 0 && (
                      <ul className="kbb-list" style={{ marginTop: 8 }}>
                        {where.nearby.map((n) => (
                          <li key={n.id}>
                            {n.name} · {km(n.distance_m)}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                {nearestRes && (
                  <div>
                    <h3>{nearestRes.label}</h3>
                    {nearestRes.results?.length ? (
                      <ol className="kbb-list" style={{ paddingLeft: 0 }}>
                        {nearestRes.results.map((r, i) => (
                          <li key={r.id} className="kbb-item kbb-item-unknown" style={{ borderStyle: "solid" }}>
                            <span className="kbb-ico" aria-hidden="true">{i + 1}</span>
                            <span style={{ flex: 1 }}>
                              <strong>{r.name}</strong>
                              <br />
                              {km(r.walk_m)} chodnikami (około {hours(r.walk_min)})
                              <span className="kbb-small kbb-muted"> · w linii prostej: {km(r.straight_m)}</span>
                              <br />
                              <span className="kbb-small">
                                Dostępność: {r.wheelchair?.value_text || "brak danych"} ({ACC_WORD[r.wheelchair?.status] || r.wheelchair?.status || "brak danych"}
                                {r.wheelchair?.source ? `, ${r.wheelchair.source}` : ""}
                                {r.wheelchair?.observed_at ? `, ${r.wheelchair.observed_at}` : ""})
                              </span>
                              <br />
                              <button type="button" className="kbb-btn" style={{ marginTop: 6 }} onClick={() => routeTo(r, nearestRes.origin)}>
                                Trasa tutaj
                              </button>{" "}
                              <button type="button" className="kbb-btn" style={{ marginTop: 6 }} onClick={() => openPlaceAt(r)}>
                                Szczegóły
                              </button>
                            </span>
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <p>{nearestRes.note || "Nie znaleziono takiego miejsca w pobliżu."}</p>
                    )}
                    {nearestRes.uwaga && <p className="kbb-small kbb-muted">{nearestRes.uwaga}</p>}
                  </div>
                )}
              </section>
            )}

            {showSignals && signals && <SignalList data={signals} activeId={activeSignal?.id} onOpen={openSignal} />}

            <TransitPanel
              transit={transit}
              busy={transitBusy}
              canPlan={Boolean(endpointSpecs())}
              onNearby={() => runTransitNearby()}
              onPlan={runTransitPlan}
              onFocusStop={focusStop}
              onFocusOption={focusOption}
            />

            <div ref={assistantInputRef}>
              <Assistant
                onSubmit={(t) => handleUtterance(t)}
                reply={reply}
                heard={heard}
                micSupported={micSupported}
                listening={listening}
                onMic={startListening}
                onRepeat={() => readAloud(lastSpokenRef.current || "Nie mam nic do powtórzenia.")}
                big={simpleLike}
              />
            </div>
          </div>
        </div>

        <div className="kbb-mapbox" style={mapStyle}>
          <Map
            ref={mapRef}
            onPointsChange={handlePointsChange}
            points={points}
            routes={resp?.routes}
            selectedRoute={selected}
            hazards={hazards}
            pins={pins}
            footprint={info?.building?.footprint || null}
            observations={observations}
            showObservations={showObs}
            stops={showStops && stopsData ? stopsData : null}
            area={area}
            theme={theme}
            clickMode={clickMode}
            onInfoClick={handleInfoClick}
            onPinClick={handlePinClick}
            clearSelectionVersion={clearVersion}
            reduceMotion={reduceMotion}
            insets={insets}
            signals={showSignals && signals ? signals : null}
            activeSignalId={activeSignal?.id || null}
            onSignalClick={openSignal}
            onReportClick={handleReportClick}
            draft={clickMode === "report" ? draft : null}
          />
        </div>

        {!noMap && (
          <details className="kbb-legend-card" open={wide}>
            <summary>Legenda</summary>
            {legendEl}
          </details>
        )}

        <div className="sr-only" aria-live="polite" role="status">{announce}</div>
      </div>
    </main>
  );
}
