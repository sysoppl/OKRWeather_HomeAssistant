/**
 * OKRWeather Cards — Lovelace widgets for the OKRWeather (Pogoda OKR)
 * integration.
 *
 * Served automatically by the integration (no manual resource registration).
 * Pick a station's weather entity; every other entity (live sensors, air
 * quality, alerts, premium AI insights) is resolved through the device
 * registry by translation key, so renamed or non-English entity ids work.
 *
 * Two kinds of cards, one design system:
 *
 * `okrweather-card` — the full station widget. Its accent palette follows
 * the live condition (sun, rain, storm, snow, night) as a translucent wash
 * over the active HA theme.
 *
 *   type: custom:okrweather-card
 *   entity: weather.gogolin_rondo
 *   name: Gogolin                # optional title override
 *   show_current: true
 *   show_details: true
 *   show_air_quality: true
 *   show_alerts: true
 *   show_forecast: true
 *   forecast_type: daily         # daily | hourly | twice_daily
 *   forecast_slots: 5            # 3..8
 *   insights: [comfort, radar, storm, pressure, frost, solar, air_trend]
 *   compact: false               # hide advisory texts and section captions
 *
 * Feature cards — small, single-purpose widgets for composing dashboards.
 * All take `entity` (the station's weather entity), `name` (title override)
 * and `show_title`; insight cards add `show_note`:
 *
 *   custom:okrweather-comfort-card    (+ show_factors: per-factor meters)
 *   custom:okrweather-radar-card
 *   custom:okrweather-storm-card
 *   custom:okrweather-pressure-card
 *   custom:okrweather-frost-card
 *   custom:okrweather-solar-card
 *   custom:okrweather-air-trend-card
 *   custom:okrweather-air-quality-card
 *   custom:okrweather-alerts-card
 *   custom:okrweather-forecast-card   (+ forecast_type, forecast_slots)
 *   custom:okrweather-details-card    (+ fields: which values to show)
 */

const CARD_TYPE = "okrweather-card";
const INTEGRATION_DOMAIN = "okrweather";
const DOCS_URL =
  "https://github.com/sysoppl/OKRWeather_HomeAssistant#dashboard-cards";

const ALL_INSIGHTS = [
  "comfort",
  "radar",
  "storm",
  "pressure",
  "frost",
  "solar",
  "air_trend",
];

const DEFAULT_DETAIL_FIELDS = [
  "wind_speed",
  "wind_gust",
  "humidity",
  "pressure",
  "precipitation_rate",
  "precipitation_today",
  "uv_index",
  "solar_radiation",
  "dew_point",
];
const ALL_DETAIL_FIELDS = [
  "temperature",
  "apparent_temperature",
  ...DEFAULT_DETAIL_FIELDS,
];

const DEFAULT_CONFIG = {
  name: "",
  background: "condition",
  background_intensity: 100,
  show_current: true,
  show_details: true,
  show_air_quality: true,
  show_alerts: true,
  show_forecast: true,
  forecast_type: "daily",
  forecast_slots: 5,
  insights: ALL_INSIGHTS,
  compact: false,
};

const CONDITION_ICONS = {
  "clear-night": "mdi:weather-night",
  cloudy: "mdi:weather-cloudy",
  exceptional: "mdi:alert-circle-outline",
  fog: "mdi:weather-fog",
  hail: "mdi:weather-hail",
  lightning: "mdi:weather-lightning",
  "lightning-rainy": "mdi:weather-lightning-rainy",
  partlycloudy: "mdi:weather-partly-cloudy",
  pouring: "mdi:weather-pouring",
  rainy: "mdi:weather-rainy",
  snowy: "mdi:weather-snowy",
  "snowy-rainy": "mdi:weather-snowy-rainy",
  sunny: "mdi:weather-sunny",
  windy: "mdi:weather-windy",
  "windy-variant": "mdi:weather-windy-variant",
};

/**
 * Per-condition ambience: `accent` colors the hero icon and small accents,
 * `washA`/`washB` are blended (via color-mix, at low opacity) into the card
 * background so the palette adapts to whatever theme is active.
 */
const CONDITION_THEMES = {
  sunny: { accent: "#eda232", washA: "#ffc55c", washB: "#4a9fd8" },
  "clear-night": { accent: "#8fa7d9", washA: "#33406e", washB: "#141c38" },
  partlycloudy: { accent: "#e0a844", washA: "#9cc0dd", washB: "#c2cdd6" },
  cloudy: { accent: "#8fa1ac", washA: "#9fb0bb", washB: "#7c8f9b" },
  fog: { accent: "#a3aab9", washA: "#aeb4c2", washB: "#8d93a5" },
  rainy: { accent: "#5b8db8", washA: "#5b8db8", washB: "#3c6a94" },
  pouring: { accent: "#417099", washA: "#417099", washB: "#2b5578" },
  lightning: { accent: "#6f7cc3", washA: "#4a548f", washB: "#23294f" },
  "lightning-rainy": { accent: "#6f7cc3", washA: "#3f4880", washB: "#1d2342" },
  hail: { accent: "#6fa5c8", washA: "#87b6d4", washB: "#5b86a8" },
  snowy: { accent: "#79b0d4", washA: "#a8d0e8", washB: "#6f9fc0" },
  "snowy-rainy": { accent: "#6ba0c6", washA: "#93bdd8", washB: "#5e8cae" },
  windy: { accent: "#69a6a2", washA: "#84b8b4", washB: "#5b8d89" },
  "windy-variant": { accent: "#69a6a2", washA: "#84b8b4", washB: "#5b8d89" },
  exceptional: { accent: "#d98a3d", washA: "#d98a3d", washB: "#a85f28" },
};
const DEFAULT_THEME = CONDITION_THEMES.cloudy;

/**
 * Fixed ambient palettes selectable via the `background` option — same
 * accent + two-tone wash structure as the condition themes, so a preset
 * behaves identically on light and dark HA themes.
 */
const BACKGROUND_PRESETS = {
  sunrise: { accent: "#e8875a", washA: "#f0a05c", washB: "#c96a8a" },
  amber: { accent: "#dda03c", washA: "#e8b45c", washB: "#a8742a" },
  forest: { accent: "#5da06b", washA: "#6fb27c", washB: "#3d7a52" },
  ocean: { accent: "#4d9bc9", washA: "#56a8d8", washB: "#2e6f9e" },
  dusk: { accent: "#8d7fc9", washA: "#7d6fc0", washB: "#453a78" },
  midnight: { accent: "#7d93c4", washA: "#2c3a63", washB: "#101830" },
  graphite: { accent: "#93a1ad", washA: "#8b98a5", washB: "#5d6a76" },
};

/** `background` option values: follow the weather, flat, preset, or custom. */
const BACKGROUND_MODES = [
  "condition",
  "none",
  ...Object.keys(BACKGROUND_PRESETS),
  "custom",
];

const RAIN_COLOR = "#4f86ba";

/** severity rank → status color; -1 = neutral */
const STATUS_COLORS = {
  "-1": "#8a95a1",
  0: "#3f9d63",
  1: "#7cab48",
  2: "#d9a23c",
  3: "#e07b39",
  4: "#d75449",
};

/**
 * Severity rank per enum sensor (keyed by translation key), matching the
 * backend orderings in const.py. Kept per-enum on purpose: "nearby" means
 * rank 3 for storm proximity but rank 2 for the radar trend, so a shared
 * flat map would silently collide. Unknown states fall back to neutral.
 */
const ENUM_RANKS = {
  comfort_label: { excellent: 0, good: 1, fair: 2, poor: 3, very_poor: 4 },
  solar_production_label: {
    excellent: 0, good: 1, fair: 2, poor: 3, very_poor: 4,
  },
  frost_level: { none: -1, low: 1, moderate: 2, high: 3, very_high: 4 },
  pressure_alert_level: {
    none: -1, low: 1, moderate: 2, high: 3, extreme: 4,
  },
  pressure_trend: { rising: -1, falling: -1, stable: -1 },
  storm_proximity: {
    none: -1, distant: 1, approaching: 2, nearby: 3, close: 4, overhead: 4,
  },
  storm_intensity: { none: -1, mild: 1, moderate: 2, severe: 3, extreme: 4 },
  radar_intensity: { none: -1, light: 1, moderate: 2, heavy: 3, extreme: 4 },
  radar_trend: {
    clear: -1, departing: 1, weakening: 1, nearby: 2, approaching: 3,
    arriving: 4, raining: 4, intensifying: 4,
  },
  air_quality_trend: {
    improving_fast: 0, improving: 1, stable: -1,
    deteriorating: 3, deteriorating_fast: 4, spike: 4,
  },
};

/** EPA AQI bands: [upper bound, color] — track segments + marker color. */
const AQI_BANDS = [
  [50, "#3f9d63"],
  [100, "#d9a23c"],
  [150, "#e07b39"],
  [200, "#d75449"],
  [300, "#8e5aa8"],
  [400, "#7d3a4a"],
];

const STRINGS = {
  en: {
    details: "Details",
    air_quality: "Air quality",
    alerts: "Weather alerts",
    forecast: "Forecast",
    insights: "AI insights",
    comfort: "Comfort",
    radar: "Rain radar",
    storm: "Storm",
    pressure: "Pressure",
    frost: "Frost",
    solar: "Solar",
    air_trend: "Air trend",
    feels_like: "feels like",
    temperature: "Temperature",
    apparent: "Feels like",
    humidity: "Humidity",
    wind: "Wind",
    gust: "Gust",
    rain_rate: "Rain rate",
    rain_today: "Rain today",
    uv: "UV index",
    solar_rad: "Solar rad.",
    dew_point: "Dew point",
    eta: "ETA",
    closest_rain: "Closest rain",
    rain_30: "Rain 30 min",
    rain_60: "Rain 60 min",
    lightning_30: "Strikes 30 min",
    distance: "Distance",
    trend: "Trend",
    window: "Window",
    peak: "Peak",
    efficiency: "Efficiency",
    probability: "Probability",
    change_rate: "Change rate",
    category: "Category",
    alert: "alert",
    alerts_n: "alerts",
    no_alerts: "No active alerts",
    until: "until",
    station_offline: "Station offline — data may be stale",
    no_entity: "Entity not found",
    empty: "No data available",
    min: "min",
  },
  pl: {
    details: "Szczegóły",
    air_quality: "Jakość powietrza",
    alerts: "Alerty pogodowe",
    forecast: "Prognoza",
    insights: "Analizy AI",
    comfort: "Komfort",
    radar: "Radar opadów",
    storm: "Burza",
    pressure: "Ciśnienie",
    frost: "Przymrozek",
    solar: "Solar",
    air_trend: "Trend powietrza",
    feels_like: "odczuwalna",
    temperature: "Temperatura",
    apparent: "Odczuwalna",
    humidity: "Wilgotność",
    wind: "Wiatr",
    gust: "Porywy",
    rain_rate: "Natężenie opadu",
    rain_today: "Deszcz dziś",
    uv: "Indeks UV",
    solar_rad: "Nasłonecznienie",
    dew_point: "Punkt rosy",
    eta: "ETA",
    closest_rain: "Najbliższy deszcz",
    rain_30: "Deszcz 30 min",
    rain_60: "Deszcz 60 min",
    lightning_30: "Wyładowania 30 min",
    distance: "Odległość",
    trend: "Trend",
    window: "Okno",
    peak: "Szczyt",
    efficiency: "Wydajność",
    probability: "Prawdopodobieństwo",
    change_rate: "Tempo zmian",
    category: "Kategoria",
    alert: "alert",
    alerts_n: "alerty(-ów)",
    no_alerts: "Brak aktywnych alertów",
    until: "do",
    station_offline: "Stacja offline — dane mogą być nieaktualne",
    no_entity: "Nie znaleziono encji",
    empty: "Brak danych",
    min: "min",
  },
};

const CARDINALS = [
  "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
];

const esc = (value) =>
  value == null
    ? ""
    : String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");

/** Accepts a color_rgb array ([r,g,b]) or a CSS color string from YAML. */
const cssColor = (value, fallback) => {
  if (Array.isArray(value) && value.length >= 3) {
    return `rgb(${Number(value[0]) || 0}, ${Number(value[1]) || 0}, ${Number(value[2]) || 0})`;
  }
  if (typeof value === "string" && value.trim()) return value.trim();
  return fallback;
};

const bearingToCardinal = (deg) => {
  if (typeof deg !== "number" || Number.isNaN(deg)) return null;
  return CARDINALS[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16];
};

const aqiColor = (aqi) => {
  if (aqi == null || Number.isNaN(aqi)) return STATUS_COLORS["-1"];
  for (const [bound, color] of AQI_BANDS) {
    if (aqi <= bound) return color;
  }
  return AQI_BANDS[AQI_BANDS.length - 1][1];
};

const comfortColor = (score) => {
  if (score == null || Number.isNaN(score)) return STATUS_COLORS["-1"];
  if (score >= 80) return STATUS_COLORS[0];
  if (score >= 60) return STATUS_COLORS[1];
  if (score >= 40) return STATUS_COLORS[2];
  if (score >= 20) return STATUS_COLORS[3];
  return STATUS_COLORS[4];
};

/** Map a temperature (°C-ish range) onto a cold-blue → hot-orange hue. */
const tempColor = (t) => {
  const clamped = Math.max(-10, Math.min(32, Number(t)));
  const hue = 215 - ((clamped + 10) / 42) * 195; // 215 (cold) → 20 (hot)
  return `hsl(${Math.round(hue)} 62% 52%)`;
};

const rankColor = (enumKey, state) =>
  STATUS_COLORS[String(ENUM_RANKS[enumKey]?.[state] ?? -1)];

const alertSeverityColor = (severity) => {
  const s = String(severity || "").toLowerCase();
  if (s === "extreme" || s === "severe") return STATUS_COLORS[4];
  if (s === "moderate") return STATUS_COLORS[3];
  return STATUS_COLORS[2];
};

const isKnown = (stateObj) =>
  stateObj && stateObj.state !== "unknown" && stateObj.state !== "unavailable";

const findStationWeather = (hass) => {
  const ids = Object.keys(hass.states).filter((id) =>
    id.startsWith("weather.")
  );
  return (
    ids.find((id) => hass.entities?.[id]?.platform === INTEGRATION_DOMAIN) ||
    ids[0] ||
    ""
  );
};

// ── Shared stylesheet ───────────────────────────────────────────────────────

const STYLES = `
  :host { display: block; }
  ha-card {
    position: relative;
    overflow: hidden;
    container-type: inline-size;
  }
  .wash {
    position: absolute;
    inset: 0;
    pointer-events: none;
    background:
      radial-gradient(120% 90% at 85% -10%,
        color-mix(in srgb, var(--okr-wash-a) calc(26% * var(--okr-tint, 1)), transparent),
        transparent 55%),
      linear-gradient(168deg,
        color-mix(in srgb, var(--okr-wash-a) calc(14% * var(--okr-tint, 1)), transparent),
        color-mix(in srgb, var(--okr-wash-b) calc(5% * var(--okr-tint, 1)), transparent) 40%,
        transparent 68%);
  }
  .content {
    position: relative;
    padding: 14px 18px 18px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  ha-card.mini .content { padding: 12px 16px 14px; gap: 10px; }
  [data-entity]:not([data-entity=""]) { cursor: pointer; }
  .warning { padding: 4px 0; color: var(--error-color, #d75449); font-size: 13px; }
  .empty {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: var(--secondary-text-color);
    padding: 2px 0;
  }
  .empty ha-icon { --mdc-icon-size: 16px; }
  .empty.ok ha-icon { color: ${STATUS_COLORS[0]}; }

  /* Entrance — first render only, transform/opacity, honors reduced motion */
  ha-card.animate .sec {
    animation: okr-rise 0.55s cubic-bezier(0.22, 1, 0.36, 1) both;
    animation-delay: calc(var(--i) * 70ms);
  }
  @keyframes okr-rise {
    from { opacity: 0; transform: translateY(7px); }
    to { opacity: 1; transform: none; }
  }
  @media (prefers-reduced-motion: reduce) {
    ha-card.animate .sec { animation: none; }
    .alert-banner.grave ha-icon { animation: none; }
  }

  .sec { display: flex; flex-direction: column; gap: 9px; min-width: 0; }

  /* ── Header (full card) ─────────────────────────────────────────────── */
  .header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
  }
  .overline {
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--secondary-text-color);
    margin-bottom: 2px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .header-left { min-width: 0; flex: 1; }
  .temp {
    display: flex;
    align-items: flex-start;
    line-height: 1;
    color: var(--primary-text-color);
    font-variant-numeric: tabular-nums;
  }
  .temp-value {
    font-size: clamp(38px, 15cqw, 56px);
    font-weight: 300;
    letter-spacing: -0.02em;
  }
  .temp-unit {
    font-size: clamp(15px, 5cqw, 20px);
    font-weight: 400;
    color: var(--secondary-text-color);
    margin: 6px 0 0 3px;
  }
  .cond {
    margin-top: 5px;
    font-size: 12.5px;
    color: var(--secondary-text-color);
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 5px;
    min-width: 0;
  }
  .cond .dot { opacity: 0.6; }
  .range { display: inline-flex; gap: 6px; font-variant-numeric: tabular-nums; }
  .range .hi { color: var(--primary-text-color); font-weight: 500; }
  .range .lo { opacity: 0.85; }
  .header-icon ha-icon {
    --mdc-icon-size: clamp(44px, 16cqw, 58px);
    color: var(--okr-accent);
    filter: drop-shadow(0 3px 10px color-mix(in srgb, var(--okr-accent) 40%, transparent));
  }

  .offline {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: var(--warning-color, #e07b39);
  }
  .offline ha-icon { --mdc-icon-size: 16px; }

  /* ── Section captions / mini header ─────────────────────────────────── */
  .section-title {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: color-mix(in srgb, var(--secondary-text-color) 80%, transparent);
  }
  .section-title::after {
    content: "";
    flex: 1;
    height: 1px;
    background: color-mix(in srgb, var(--divider-color) 80%, transparent);
  }
  .mini-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
    min-width: 0;
  }
  .mini-head .overline { margin-bottom: 0; }
  .mini-station {
    font-size: 10px;
    color: color-mix(in srgb, var(--secondary-text-color) 75%, transparent);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* ── Details: value-first instrument strip ──────────────────────────── */
  .details {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(88px, 1fr));
    gap: 12px 16px;
  }
  .detail { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
  .detail-value {
    font-size: 14px;
    font-weight: 500;
    color: var(--primary-text-color);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .detail-label {
    font-size: 9.5px;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--secondary-text-color);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* ── Air quality meter ──────────────────────────────────────────────── */
  .aqi { display: flex; flex-direction: column; gap: 7px; }
  .aqi-head {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
  }
  .aqi-value {
    font-size: 14px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .aqi-pm { font-size: 11.5px; color: var(--secondary-text-color); }
  .aqi-track {
    position: relative;
    display: flex;
    gap: 2px;
    height: 5px;
    margin: 3px 0 4px;
  }
  .aqi-track i {
    height: 100%;
    border-radius: 3px;
    opacity: 0.42;
  }
  .aqi-marker {
    position: absolute;
    top: 50%;
    width: 11px;
    height: 11px;
    border-radius: 50%;
    transform: translate(-50%, -50%);
    box-shadow: 0 0 0 2px var(--ha-card-background, var(--card-background-color, #fff));
  }

  /* ── Alert banners ──────────────────────────────────────────────────── */
  .alert-list { display: flex; flex-direction: column; gap: 8px; }
  .alert-banner {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 12px;
    border-radius: 10px;
    background: color-mix(in srgb, var(--alert-color) 12%, transparent);
  }
  .alert-banner ha-icon { color: var(--alert-color); flex-shrink: 0; }
  .alert-banner.grave ha-icon { animation: okr-pulse 2.2s ease-in-out infinite; }
  @keyframes okr-pulse { 50% { opacity: 0.45; } }
  .alert-text { display: flex; flex-direction: column; min-width: 0; }
  .alert-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--primary-text-color);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .alert-sub { font-size: 11px; color: var(--secondary-text-color); }

  /* ── Insight tiles ──────────────────────────────────────────────────── */
  .insights {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(175px, 1fr));
    gap: 8px;
  }
  .tile {
    background: color-mix(in srgb, var(--primary-text-color) 4%, transparent);
    border-radius: 12px;
    padding: 10px 12px 11px;
    display: flex;
    flex-direction: column;
    gap: 7px;
    min-width: 0;
  }
  .tile-head { display: flex; align-items: center; }
  .tile-title {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--secondary-text-color);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .tile-body { display: flex; gap: 12px; align-items: flex-start; }
  .tile-col { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
  .tile-main {
    font-size: 14px;
    font-weight: 500;
    color: var(--primary-text-color);
    line-height: 1.15;
  }
  .tile-main .big {
    font-size: 21px;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
  }
  .tile-rows { display: flex; flex-direction: column; gap: 3px; }
  .tile-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 8px;
    font-size: 11px;
  }
  .tile-row span:first-child { color: var(--secondary-text-color); }
  .tile-row span:last-child {
    color: var(--primary-text-color);
    font-weight: 500;
    font-variant-numeric: tabular-nums;
    text-align: right;
  }
  .tile-note {
    font-size: 11px;
    line-height: 1.4;
    color: var(--secondary-text-color);
  }

  /* Status chip: colored dot + label in ink */
  .status {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 500;
    color: var(--primary-text-color);
  }
  .status i {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  /* Comfort ring gauge */
  .gauge { position: relative; width: 52px; height: 52px; flex-shrink: 0; }
  .gauge-ring {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    background: conic-gradient(var(--c) var(--p),
      color-mix(in srgb, var(--divider-color) 55%, transparent) 0);
    -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 6px), #000 calc(100% - 5px));
    mask: radial-gradient(farthest-side, transparent calc(100% - 6px), #000 calc(100% - 5px));
  }
  .gauge-num {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    font-size: 15px;
    font-weight: 600;
    color: var(--primary-text-color);
    font-variant-numeric: tabular-nums;
  }

  /* Probability meters */
  .meter-row { display: flex; align-items: center; gap: 8px; font-size: 11px; }
  .meter-label {
    color: var(--secondary-text-color);
    white-space: nowrap;
    min-width: 64px;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .meter {
    flex: 1;
    height: 4px;
    border-radius: 2px;
    background: color-mix(in srgb, var(--divider-color) 55%, transparent);
    overflow: hidden;
  }
  .meter i {
    display: block;
    height: 100%;
    border-radius: 2px;
    background: var(--okr-rain);
  }
  .meter-val {
    color: var(--primary-text-color);
    font-weight: 500;
    font-variant-numeric: tabular-nums;
    min-width: 30px;
    text-align: right;
  }

  /* ── Forecast strip with temperature range bars ─────────────────────── */
  .forecast {
    display: flex;
    justify-content: space-between;
    gap: 4px;
    overflow: hidden;
  }
  .fc-slot {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
    flex: 1;
    min-width: 0;
  }
  .fc-label {
    font-size: 10.5px;
    color: var(--secondary-text-color);
    text-transform: capitalize;
    white-space: nowrap;
  }
  .fc-slot.today .fc-label { color: var(--okr-accent); font-weight: 600; }
  .fc-slot ha-icon {
    --mdc-icon-size: 22px;
    color: color-mix(in srgb, var(--secondary-text-color) 90%, transparent);
  }
  .fc-slot.today ha-icon { color: var(--okr-accent); }
  .fc-temp {
    font-size: 13px;
    font-weight: 600;
    color: var(--primary-text-color);
    font-variant-numeric: tabular-nums;
  }
  .fc-bar {
    position: relative;
    width: 4px;
    height: 30px;
    border-radius: 2px;
    background: color-mix(in srgb, var(--divider-color) 55%, transparent);
    margin: 1px 0;
  }
  .fc-bar i {
    position: absolute;
    left: 0;
    right: 0;
    border-radius: 2px;
    min-height: 4px;
  }
  .fc-lo {
    font-size: 11px;
    color: var(--secondary-text-color);
    font-variant-numeric: tabular-nums;
  }
  .fc-precip {
    font-size: 10px;
    min-height: 12px;
    color: var(--okr-rain);
    font-variant-numeric: tabular-nums;
  }
`;

// ── Shared base class ───────────────────────────────────────────────────────

class OKRBaseCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._forecast = undefined;
    this._forecastKey = null;
    this._forecastDataKey = null;
    this._forecastFailures = 0;
    this._forecastRetry = undefined;
    this._unsubPromise = undefined;

    // Static skeleton: the stylesheet is parsed once; renders only swap the
    // markup below it. One delegated listener replaces per-element handlers.
    const style = document.createElement("style");
    style.textContent = STYLES;
    this._root = document.createElement("div");
    this.shadowRoot.append(style, this._root);
    this.shadowRoot.addEventListener("click", (ev) => {
      const target = ev
        .composedPath()
        .find((el) => el instanceof HTMLElement && el.dataset?.entity);
      if (!target) return;
      ev.stopPropagation();
      this.dispatchEvent(
        new CustomEvent("hass-more-info", {
          bubbles: true,
          composed: true,
          detail: { entityId: target.dataset.entity },
        })
      );
    });
  }

  set hass(hass) {
    this._hass = hass;
    const fp = this._computeFingerprint();
    if (fp !== this._fingerprint) {
      this._fingerprint = fp;
      this._render();
    }
    this._manageForecast();
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    this._forecastKey = null; // force a resubscribe
    if (this._hass && this._config) {
      this._manageForecast();
      this._render();
    }
  }

  disconnectedCallback() {
    this._dropForecastSub();
    this._forecastKey = null;
  }

  /** Whether this card needs the weather forecast subscription. */
  _wantsForecast() {
    return false;
  }

  /** Background mode used when the config doesn't set one. */
  _defaultBackground() {
    return "none";
  }

  /**
   * Resolve the card's ambience (accent + wash palette) from the
   * `background` config: follow the live condition, a fixed preset,
   * custom colors, or flat ("none" — accent still follows the weather).
   */
  _ambience(weather) {
    const conditionTheme =
      (weather && CONDITION_THEMES[weather.state]) || DEFAULT_THEME;
    const mode = this._config.background || this._defaultBackground();
    let theme = conditionTheme;
    const wash = mode !== "none";
    if (mode === "custom") {
      theme = {
        accent: cssColor(this._config.custom_accent, conditionTheme.accent),
        washA: cssColor(this._config.custom_wash_a, conditionTheme.washA),
        washB: cssColor(this._config.custom_wash_b, conditionTheme.washB),
      };
    } else if (BACKGROUND_PRESETS[mode]) {
      theme = BACKGROUND_PRESETS[mode];
    }
    const raw = Number(this._config.background_intensity);
    const tint = Number.isFinite(raw) ? Math.max(0, Math.min(2, raw / 100)) : 1;
    return { ...theme, wash, tint };
  }

  _ambienceStyle(amb) {
    return (
      `--okr-accent:${esc(amb.accent)};--okr-wash-a:${esc(amb.washA)};` +
      `--okr-wash-b:${esc(amb.washB)};--okr-rain:${RAIN_COLOR};` +
      `--okr-tint:${amb.tint}`
    );
  }

  // ── Entity resolution ──────────────────────────────────────────────────

  /** translation_key → entity_id for every entity on the station's device. */
  _map() {
    const hass = this._hass;
    if (!hass) return {};
    if (this._entityMap && this._entitiesRef === hass.entities) {
      return this._entityMap;
    }
    const map = {};
    const deviceId = hass.entities?.[this._config.entity]?.device_id;
    if (deviceId) {
      for (const [id, reg] of Object.entries(hass.entities)) {
        if (
          reg.device_id === deviceId &&
          reg.platform === INTEGRATION_DOMAIN &&
          reg.translation_key
        ) {
          map[reg.translation_key] = id;
        }
      }
    }
    this._entityMap = map;
    this._entitiesRef = hass.entities;
    return map;
  }

  _stateObj(key) {
    const id = this._map()[key];
    return id ? this._hass.states[id] : undefined;
  }

  /** Formatted state (translated, with unit) or null when missing/unknown. */
  _fmt(key) {
    const stateObj = this._stateObj(key);
    if (!isKnown(stateObj)) return null;
    try {
      return this._hass.formatEntityState(stateObj);
    } catch (e) {
      return stateObj.state;
    }
  }

  _num(key) {
    const stateObj = this._stateObj(key);
    if (!isKnown(stateObj)) return null;
    const value = Number(stateObj.state);
    return Number.isNaN(value) ? null : value;
  }

  _attr(key, attr) {
    const stateObj = this._stateObj(key);
    return isKnown(stateObj) ? stateObj.attributes[attr] : undefined;
  }

  /** First existing entity id among the given translation keys. */
  _anchor(...keys) {
    const map = this._map();
    for (const key of keys) {
      if (map[key]) return map[key];
    }
    return "";
  }

  _computeFingerprint() {
    if (!this._hass || !this._config) return "";
    const parts = [this._hass.language, this._config.entity];
    const weather = this._hass.states[this._config.entity];
    parts.push(weather ? weather.last_updated : "-");
    for (const id of Object.values(this._map())) {
      const stateObj = this._hass.states[id];
      parts.push(stateObj ? stateObj.last_updated : "-");
    }
    return parts.join("|");
  }

  // ── Forecast subscription ──────────────────────────────────────────────

  async _manageForecast() {
    if (!this._hass || !this._config) return;
    const want = this._wantsForecast() && this.isConnected;
    const key = want
      ? `${this._config.entity}|${this._config.forecast_type}`
      : null;
    if (key === this._forecastKey) return;
    this._dropForecastSub();
    this._forecastKey = key;
    if (!key) {
      this._forecast = undefined;
      this._forecastDataKey = null;
      return;
    }
    // Keep already-fetched data across a reattach (tab switch, conditional
    // card) to the same entity/type — only a genuinely different
    // subscription starts from a blank forecast.
    if (this._forecastDataKey !== key) {
      this._forecast = undefined;
      this._forecastDataKey = key;
      this._forecastFailures = 0;
    }
    const attempt = this._hass.connection.subscribeMessage(
      (event) => {
        this._forecastFailures = 0;
        this._forecast = event.forecast;
        this._forecastDataKey = key;
        this._render();
      },
      {
        type: "weather/subscribe_forecast",
        forecast_type: this._config.forecast_type,
        entity_id: this._config.entity,
      }
    );
    this._unsubPromise = attempt;
    try {
      await attempt;
    } catch (e) {
      if (this._forecastKey !== key) return; // superseded meanwhile
      this._unsubPromise = undefined;
      this._forecastKey = null; // allow another attempt
      this._forecastFailures += 1;
      if (this._forecastFailures <= 5) {
        // Transient (reconnect, HA restart) — retry with growing backoff.
        clearTimeout(this._forecastRetry);
        this._forecastRetry = setTimeout(
          () => this._manageForecast(),
          Math.min(5000 * 2 ** (this._forecastFailures - 1), 60000)
        );
      } else {
        // Persistent (e.g. unsupported forecast_type) — stop asking.
        this._forecastKey = key;
        this._forecast = [];
      }
    }
  }

  _dropForecastSub() {
    clearTimeout(this._forecastRetry);
    if (this._unsubPromise) {
      this._unsubPromise
        .then((unsub) => unsub())
        .catch(() => undefined);
      this._unsubPromise = undefined;
    }
  }

  // ── Shared formatting helpers ──────────────────────────────────────────

  _t(key) {
    const lang = (this._hass?.language || "en").startsWith("pl") ? "pl" : "en";
    return STRINGS[lang][key] ?? STRINGS.en[key] ?? key;
  }

  _formatNumber(value, digits = 1) {
    const lang = this._hass?.language || "en";
    try {
      return new Intl.NumberFormat(lang, {
        maximumFractionDigits: digits,
      }).format(value);
    } catch (e) {
      return String(value);
    }
  }

  _formatShortTime(iso) {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return String(iso);
    return date.toLocaleString(this._hass.language || "en", {
      weekday: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  // ── Shared section builders (return html, or null when no data) ───────

  _status(key) {
    const stateObj = this._stateObj(key);
    const label = this._fmt(key);
    if (!isKnown(stateObj) || label == null) return "";
    return `
      <span class="status">
        <i style="background:${rankColor(key, stateObj.state)}"></i>${esc(label)}
      </span>`;
  }

  _kvRow(label, value) {
    if (value == null || value === "") return "";
    return `
      <div class="tile-row">
        <span>${esc(label)}</span><span>${esc(value)}</span>
      </div>`;
  }

  _meterRow(label, percent) {
    if (percent == null) return "";
    const clamped = Math.min(Math.max(percent, 0), 100);
    return `
      <div class="meter-row">
        <span class="meter-label">${esc(label)}</span>
        <div class="meter"><i style="width:${clamped}%"></i></div>
        <span class="meter-val">${Math.round(clamped)}%</span>
      </div>`;
  }

  _detailsGrid(fields) {
    const windDir = bearingToCardinal(this._num("wind_bearing"));
    const wind = this._fmt("wind_speed");
    const defs = [
      ["temperature", this._t("temperature"), this._fmt("temperature")],
      ["apparent_temperature", this._t("apparent"), this._fmt("apparent_temperature")],
      [
        "wind_speed",
        this._t("wind"),
        wind ? `${wind}${windDir ? ` ${windDir}` : ""}` : null,
      ],
      ["wind_gust", this._t("gust"), this._fmt("wind_gust")],
      ["humidity", this._t("humidity"), this._fmt("humidity")],
      ["pressure", this._t("pressure"), this._fmt("pressure")],
      ["precipitation_rate", this._t("rain_rate"), this._fmt("precipitation_rate")],
      ["precipitation_today", this._t("rain_today"), this._fmt("precipitation_today")],
      ["uv_index", this._t("uv"), this._fmt("uv_index")],
      ["solar_radiation", this._t("solar_rad"), this._fmt("solar_radiation")],
      ["dew_point", this._t("dew_point"), this._fmt("dew_point")],
    ];
    const items = defs.filter(
      ([id, , value]) => fields.includes(id) && value != null
    );
    if (!items.length) return null;
    const map = this._map();
    return `
      <div class="details">
        ${items
          .map(
            ([key, label, value]) => `
          <div class="detail" data-entity="${esc(map[key] || "")}">
            <span class="detail-value">${esc(value)}</span>
            <span class="detail-label">${esc(label)}</span>
          </div>`
          )
          .join("")}
      </div>
    `;
  }

  _airBody() {
    const aqi = this._num("aqi");
    const pm25 = this._fmt("pm2_5");
    const pm10 = this._fmt("pm10");
    if (aqi == null && pm25 == null && pm10 == null) return null;

    const map = this._map();
    const color = aqiColor(aqi);
    const pm = [pm25 && `PM2.5 ${pm25}`, pm10 && `PM10 ${pm10}`]
      .filter(Boolean)
      .join(" · ");

    let track = "";
    if (aqi != null) {
      const pos = Math.min(Math.max(aqi, 0), 400) / 4; // % of 0-400 scale
      let prev = 0;
      const segments = AQI_BANDS.map(([bound, bandColor]) => {
        const width = ((bound - prev) / 400) * 100;
        prev = bound;
        return `<i style="width:${width}%;background:${bandColor}"></i>`;
      }).join("");
      track = `
        <div class="aqi-track">
          ${segments}
          <span class="aqi-marker" style="left:${pos}%;background:${color}"></span>
        </div>`;
    }

    return `
      <div class="aqi" data-entity="${esc(map.aqi || map.pm2_5 || "")}">
        <div class="aqi-head">
          ${aqi != null ? `<span class="aqi-value" style="color:${color}">AQI ${Math.round(aqi)}</span>` : ""}
          ${pm ? `<span class="aqi-pm">${esc(pm)}</span>` : ""}
        </div>
        ${track}
      </div>
    `;
  }

  _alertBanner(alert, sub, grave) {
    const color = alertSeverityColor(alert.severity);
    return `
      <div class="alert-banner ${grave ? "grave" : ""}" style="--alert-color:${color}"
           data-entity="${esc(this._anchor("active_alerts_count"))}">
        <ha-icon icon="mdi:alert"></ha-icon>
        <div class="alert-text">
          <span class="alert-title">${esc(alert.title || this._t("alerts"))}</span>
          <span class="alert-sub">${sub}</span>
        </div>
      </div>`;
  }

  _forecastStrip(weather) {
    if (!Array.isArray(this._forecast) || !this._forecast.length) return null;
    const slots = this._forecast.slice(
      0,
      Math.max(3, Math.min(8, Number(this._config.forecast_slots) || 5))
    );
    const lang = this._hass.language || "en";
    const type = this._config.forecast_type;
    const daily = type === "daily";

    const label = (item) => {
      const date = new Date(item.datetime);
      if (Number.isNaN(date.getTime())) return "";
      if (type === "hourly") {
        return date.toLocaleTimeString(lang, { hour: "numeric" });
      }
      const day = date.toLocaleDateString(lang, { weekday: "short" });
      if (type === "twice_daily") {
        return `${day}${item.is_daytime === false ? " ☾" : ""}`;
      }
      return day;
    };

    // Shared scale for the temperature range bars.
    let lo = Infinity;
    let hi = -Infinity;
    if (daily) {
      for (const item of slots) {
        if (item.temperature != null) hi = Math.max(hi, item.temperature);
        if (item.templow != null) lo = Math.min(lo, item.templow);
      }
    }
    const span = hi - lo || 1;
    const bars = daily && Number.isFinite(lo) && Number.isFinite(hi);

    return `
      <div class="forecast">
        ${slots
          .map((item, index) => {
            const icon =
              CONDITION_ICONS[item.condition] || "mdi:weather-cloudy";
            const precip =
              item.precipitation_probability != null &&
              item.precipitation_probability > 0
                ? `<span class="fc-precip">${Math.round(item.precipitation_probability)}%</span>`
                : `<span class="fc-precip"></span>`;
            let barHtml = "";
            if (bars && item.temperature != null && item.templow != null) {
              const top = ((hi - item.temperature) / span) * 100;
              const bottom = ((item.templow - lo) / span) * 100;
              barHtml = `
                <div class="fc-bar">
                  <i style="top:${top}%;bottom:${bottom}%;
                     background:linear-gradient(180deg,${tempColor(item.temperature)},${tempColor(item.templow)})"></i>
                </div>`;
            }
            const low =
              item.templow != null
                ? `<span class="fc-lo">${Math.round(item.templow)}°</span>`
                : "";
            const temp =
              item.temperature != null
                ? `${Math.round(item.temperature)}°`
                : "–";
            return `
            <div class="fc-slot ${index === 0 ? "today" : ""}">
              <span class="fc-label">${esc(label(item))}</span>
              <ha-icon icon="${icon}"></ha-icon>
              <span class="fc-temp">${temp}</span>
              ${barHtml}
              ${low}
              ${precip}
            </div>`;
          })
          .join("")}
      </div>
    `;
  }

  // ── Insight definitions (shared by full-card tiles and feature cards) ─

  _defComfort({ factors = false } = {}) {
    const score = this._num("comfort_score");
    if (score == null) return null;
    const color = comfortColor(score);
    const lead = `
      <div class="gauge" role="img" aria-label="${Math.round(score)}%">
        <div class="gauge-ring" style="--p:${Math.min(Math.max(score, 0), 100)}%;--c:${color}"></div>
        <div class="gauge-num">${Math.round(score)}</div>
      </div>`;
    const rows = [];
    if (factors) {
      const factorDefs = [
        ["temperature_score", this._t("temperature")],
        ["humidity_score", this._t("humidity")],
        ["wind_score", this._t("wind")],
        ["uv_score", "UV"],
        ["aqi_score", "AQI"],
      ];
      for (const [attr, label] of factorDefs) {
        const value = this._attr("comfort_score", attr);
        if (typeof value === "number") rows.push(this._meterRow(label, value));
      }
    }
    return {
      entityId: this._anchor("comfort_score", "comfort_label"),
      title: this._t("comfort"),
      lead,
      main: this._status("comfort_label"),
      rows,
      note: this._attr("comfort_score", "description"),
    };
  }

  _defRadar() {
    const trend = this._fmt("radar_trend");
    const intensityObj = this._stateObj("radar_intensity");
    if (trend == null && !isKnown(intensityObj)) return null;
    const eta = this._num("radar_rain_eta");
    const intensity = this._status("radar_intensity");
    return {
      entityId: this._anchor("radar_trend", "radar_intensity"),
      title: this._t("radar"),
      main: trend ? esc(trend) : intensity,
      rows: [
        trend && intensity
          ? `<div class="tile-row"><span></span>${intensity}</div>`
          : "",
        this._kvRow(
          this._t("eta"),
          eta != null ? `${eta} ${this._t("min")}` : null
        ),
        this._kvRow(this._t("closest_rain"), this._fmt("radar_closest_rain")),
        this._kvRow(this._t("rain_rate"), this._fmt("radar_rain_rate")),
        this._meterRow(this._t("rain_30"), this._num("rain_probability_30min")),
        this._meterRow(this._t("rain_60"), this._num("rain_probability_60min")),
      ],
    };
  }

  _defStorm() {
    const proximity = this._stateObj("storm_proximity");
    if (!isKnown(proximity)) return null;
    const eta = this._num("storm_eta");
    const intensity = this._status("storm_intensity");
    return {
      entityId: this._anchor("storm_proximity", "storm_intensity"),
      title: this._t("storm"),
      main: this._status("storm_proximity"),
      rows: [
        intensity ? `<div class="tile-row"><span></span>${intensity}</div>` : "",
        this._kvRow(
          this._t("eta"),
          eta != null ? `${eta} ${this._t("min")}` : null
        ),
        this._kvRow(this._t("lightning_30"), this._fmt("lightning_count_30min")),
        this._kvRow(this._t("distance"), this._fmt("storm_lightning_distance")),
      ],
      note: this._attr("storm_proximity", "advisory"),
    };
  }

  _defPressure() {
    const level = this._stateObj("pressure_alert_level");
    if (!isKnown(level)) return null;
    return {
      entityId: this._anchor("pressure_alert_level", "pressure_trend"),
      title: this._t("pressure"),
      main: this._status("pressure_alert_level"),
      rows: [
        this._kvRow(this._t("trend"), this._fmt("pressure_trend")),
        this._kvRow(this._t("change_rate"), this._fmt("pressure_change_rate")),
        this._kvRow("Δ 3 h", this._attr("pressure_alert_level", "delta_3h_hpa")),
        this._kvRow("Δ 6 h", this._attr("pressure_alert_level", "delta_6h_hpa")),
      ],
      note: this._attr("pressure_alert_level", "alert_text"),
    };
  }

  _defFrost() {
    const level = this._stateObj("frost_level");
    const probability = this._num("frost_probability");
    if (!isKnown(level) && probability == null) return null;
    const start = this._attr("frost_probability", "window_start");
    const end = this._attr("frost_probability", "window_end");
    const window =
      start && end
        ? `${this._formatShortTime(start)} – ${this._formatShortTime(end)}`
        : null;
    return {
      entityId: this._anchor("frost_probability", "frost_level"),
      title: this._t("frost"),
      main: this._status("frost_level"),
      rows: [
        this._meterRow(this._t("probability"), probability),
        this._kvRow(this._t("window"), window),
      ],
      note: this._attr("frost_probability", "advisory"),
    };
  }

  _defSolar() {
    const total = this._fmt("solar_total_kwh");
    if (total == null) return null;
    const label = this._status("solar_production_label");
    return {
      entityId: this._anchor("solar_total_kwh", "solar_production_label"),
      title: this._t("solar"),
      main: `<span class="big">${esc(total)}</span>`,
      rows: [
        label ? `<div class="tile-row"><span></span>${label}</div>` : "",
        this._kvRow(this._t("peak"), this._fmt("solar_peak_kw")),
        this._kvRow(this._t("efficiency"), this._fmt("solar_efficiency")),
      ],
      note: this._attr("solar_total_kwh", "summary"),
    };
  }

  _defAirTrend() {
    const trend = this._stateObj("air_quality_trend");
    if (!isKnown(trend)) return null;
    return {
      entityId: this._anchor("air_quality_trend"),
      title: this._t("air_trend"),
      main: this._status("air_quality_trend"),
      rows: [
        this._kvRow(this._t("category"), this._attr("air_quality_trend", "category")),
      ],
      note: this._attr("air_quality_trend", "advisory"),
    };
  }

  _insightBody(def, showNote) {
    const rowsHtml = (def.rows || []).filter(Boolean).join("");
    return `
      <div class="tile-body">
        ${def.lead || ""}
        <div class="tile-col">
          ${def.main ? `<div class="tile-main">${def.main}</div>` : ""}
          ${rowsHtml ? `<div class="tile-rows">${rowsHtml}</div>` : ""}
        </div>
      </div>
      ${
        def.note && showNote
          ? `<div class="tile-note">${esc(def.note)}</div>`
          : ""
      }`;
  }
}

// ── Full station card ───────────────────────────────────────────────────────

class OKRWeatherCard extends OKRBaseCard {
  constructor() {
    super();
    this._animatedOnce = false;
  }

  static async getConfigElement() {
    await loadHaForm();
    return document.createElement("okrweather-card-editor");
  }

  static getStubConfig(hass) {
    return { entity: findStationWeather(hass) };
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error(
        'okrweather-card: set "entity" to the weather entity of an OKRWeather station'
      );
    }
    this._config = { ...DEFAULT_CONFIG, ...config };
    if (!Array.isArray(this._config.insights)) {
      this._config.insights = ALL_INSIGHTS;
    }
    this._fingerprint = undefined;
    this._entityMap = undefined;
    if (this._hass) {
      this._manageForecast();
      this._render();
    }
  }

  _wantsForecast() {
    return !!this._config?.show_forecast;
  }

  _defaultBackground() {
    return "condition";
  }

  getCardSize() {
    if (!this._config) return 4;
    let size = 2;
    if (this._config.show_details) size += 2;
    if (this._config.show_forecast) size += 2;
    if (this._config.insights?.length) size += 2;
    return size;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  _render() {
    if (!this._hass || !this._config) return;
    const config = this._config;
    const weather = this._hass.states[config.entity];
    const amb = this._ambience(weather);

    let body;
    if (!weather) {
      body = `<div class="warning">${this._t("no_entity")}: ${esc(
        config.entity
      )}</div>`;
    } else {
      const sections = [];
      if (config.show_alerts) sections.push(this._renderAlertsSection());
      if (config.show_current) sections.push(this._renderHeader(weather));
      sections.push(this._renderOffline());
      if (config.show_details) {
        const grid = this._detailsGrid(DEFAULT_DETAIL_FIELDS);
        if (grid) sections.push(`${this._sectionTitle("details")}${grid}`);
      }
      if (config.show_air_quality) {
        const air = this._airBody();
        if (air) sections.push(`${this._sectionTitle("air_quality")}${air}`);
      }
      if (config.insights?.length) sections.push(this._renderInsights());
      if (config.show_forecast) {
        const strip = this._forecastStrip(weather);
        if (strip) sections.push(`${this._sectionTitle("forecast")}${strip}`);
      }
      body = sections
        .filter(Boolean)
        .map((html, i) => `<div class="sec" style="--i:${i}">${html}</div>`)
        .join("");
    }

    const animate = !this._animatedOnce;
    this._animatedOnce = true;

    this._root.innerHTML = `
      <ha-card class="${animate ? "animate" : ""}" style="${this._ambienceStyle(amb)}">
        ${amb.wash ? '<div class="wash"></div>' : ""}
        <div class="content">${body}</div>
      </ha-card>
    `;
  }

  _sectionTitle(key) {
    if (this._config.compact) return "";
    return `<div class="section-title"><span>${this._t(key)}</span></div>`;
  }

  _heroTemperature(weather) {
    const tempObj = this._stateObj("temperature");
    let value = null;
    let unit = "°C";
    if (isKnown(tempObj) && !Number.isNaN(Number(tempObj.state))) {
      value = Number(tempObj.state);
      unit = tempObj.attributes.unit_of_measurement || unit;
    } else if (weather.attributes.temperature != null) {
      value = weather.attributes.temperature;
      unit = weather.attributes.temperature_unit || unit;
    }
    return value == null
      ? null
      : { value: this._formatNumber(value, 1), unit };
  }

  _renderHeader(weather) {
    const config = this._config;
    const icon = CONDITION_ICONS[weather.state] || "mdi:weather-cloudy";
    const name =
      config.name || weather.attributes.friendly_name || config.entity;

    const hero = this._heroTemperature(weather);
    let condition;
    try {
      condition = this._hass.formatEntityState(weather);
    } catch (e) {
      condition = weather.state;
    }
    const feels = this._fmt("apparent_temperature");

    // Today's span, once the daily forecast has arrived.
    let range = "";
    if (
      this._config.forecast_type === "daily" &&
      Array.isArray(this._forecast) &&
      this._forecast.length
    ) {
      const today = this._forecast[0];
      if (today.temperature != null && today.templow != null) {
        range = `<span class="range">
            <span class="hi">↑${Math.round(today.temperature)}°</span>
            <span class="lo">↓${Math.round(today.templow)}°</span>
          </span>`;
      }
    }

    return `
      <div class="header" data-entity="${esc(this._config.entity)}">
        <div class="header-left">
          <div class="overline">${esc(name)}</div>
          <div class="temp">
            ${
              hero
                ? `<span class="temp-value">${esc(hero.value)}</span><span class="temp-unit">${esc(hero.unit)}</span>`
                : `<span class="temp-value">—</span>`
            }
          </div>
          <div class="cond">
            <span>${esc(condition)}</span>
            ${feels ? `<span class="dot">·</span><span>${this._t("feels_like")} ${esc(feels)}</span>` : ""}
            ${range}
          </div>
        </div>
        <div class="header-icon"><ha-icon icon="${icon}"></ha-icon></div>
      </div>
    `;
  }

  _renderOffline() {
    const online = this._stateObj("station_online");
    if (!isKnown(online) || online.state !== "off") return "";
    return `
      <div class="offline">
        <ha-icon icon="mdi:lan-disconnect"></ha-icon>
        ${this._t("station_offline")}
      </div>
    `;
  }

  _renderAlertsSection() {
    const count = this._num("active_alerts_count");
    if (!count) return "";
    const alerts = this._attr("active_alerts_count", "alerts") || [];
    const first = alerts[0] || {};
    const severity = String(first.severity || "").toLowerCase();
    const grave = severity === "extreme" || severity === "severe";
    const sub = `${count} ${count === 1 ? this._t("alert") : this._t("alerts_n")}${
      first.area ? ` · ${esc(first.area)}` : ""
    }`;
    return this._alertBanner(first, sub, grave);
  }

  _renderInsights() {
    const wanted = this._config.insights;
    const defs = [
      wanted.includes("comfort") && this._defComfort(),
      wanted.includes("radar") && this._defRadar(),
      wanted.includes("storm") && this._defStorm(),
      wanted.includes("pressure") && this._defPressure(),
      wanted.includes("frost") && this._defFrost(),
      wanted.includes("solar") && this._defSolar(),
      wanted.includes("air_trend") && this._defAirTrend(),
    ].filter(Boolean);
    if (!defs.length) return "";
    const tiles = defs
      .map(
        (def) => `
        <div class="tile" data-entity="${esc(def.entityId || "")}">
          <div class="tile-head">
            <span class="tile-title">${esc(def.title)}</span>
          </div>
          ${this._insightBody(def, !this._config.compact)}
        </div>`
      )
      .join("");
    return `
      ${this._sectionTitle("insights")}
      <div class="insights">${tiles}</div>
    `;
  }
}

// ── Feature cards (small, single-purpose) ───────────────────────────────────

const FEATURE_CARDS = [
  {
    type: "okrweather-comfort-card",
    name: "OKRWeather Comfort Card",
    description: "Comfort index ring with the per-factor breakdown.",
    titleKey: "comfort",
    defaults: { show_note: true, show_factors: true },
    size: 3,
    render: (card) => {
      const def = card._defComfort({ factors: card._config.show_factors });
      return def
        ? card._insightBody(def, card._config.show_note !== false)
        : null;
    },
  },
  {
    type: "okrweather-radar-card",
    name: "OKRWeather Rain Radar Card",
    description: "AI radar analysis — trend, intensity, ETA, rain probability.",
    titleKey: "radar",
    defaults: { show_note: true },
    size: 3,
    render: (card) => {
      const def = card._defRadar();
      return def
        ? card._insightBody(def, card._config.show_note !== false)
        : null;
    },
  },
  {
    type: "okrweather-storm-card",
    name: "OKRWeather Storm Card",
    description: "Storm tracker — proximity, intensity, ETA, lightning.",
    titleKey: "storm",
    defaults: { show_note: true },
    size: 3,
    render: (card) => {
      const def = card._defStorm();
      return def
        ? card._insightBody(def, card._config.show_note !== false)
        : null;
    },
  },
  {
    type: "okrweather-pressure-card",
    name: "OKRWeather Pressure Card",
    description: "Pressure alert level, trend and change rate.",
    titleKey: "pressure",
    defaults: { show_note: true },
    size: 3,
    render: (card) => {
      const def = card._defPressure();
      return def
        ? card._insightBody(def, card._config.show_note !== false)
        : null;
    },
  },
  {
    type: "okrweather-frost-card",
    name: "OKRWeather Frost Card",
    description: "Frost probability, level and expected window.",
    titleKey: "frost",
    defaults: { show_note: true },
    size: 3,
    render: (card) => {
      const def = card._defFrost();
      return def
        ? card._insightBody(def, card._config.show_note !== false)
        : null;
    },
  },
  {
    type: "okrweather-solar-card",
    name: "OKRWeather Solar Card",
    description: "Solar forecast — today's kWh, peak power, efficiency.",
    titleKey: "solar",
    defaults: { show_note: true },
    size: 3,
    render: (card) => {
      const def = card._defSolar();
      return def
        ? card._insightBody(def, card._config.show_note !== false)
        : null;
    },
  },
  {
    type: "okrweather-air-trend-card",
    name: "OKRWeather Air Trend Card",
    description: "AI air-quality trend with advisory.",
    titleKey: "air_trend",
    defaults: { show_note: true },
    size: 2,
    render: (card) => {
      const def = card._defAirTrend();
      return def
        ? card._insightBody(def, card._config.show_note !== false)
        : null;
    },
  },
  {
    type: "okrweather-air-quality-card",
    name: "OKRWeather Air Quality Card",
    description: "EPA-banded AQI meter with PM2.5 / PM10.",
    titleKey: "air_quality",
    defaults: {},
    size: 2,
    render: (card) => card._airBody(),
  },
  {
    type: "okrweather-alerts-card",
    name: "OKRWeather Alerts Card",
    description: "All active government weather alerts for the station area.",
    titleKey: "alerts",
    defaults: {},
    size: 2,
    render: (card) => {
      const stateObj = card._stateObj("active_alerts_count");
      if (!isKnown(stateObj)) return null;
      const alerts = stateObj.attributes.alerts || [];
      if (!alerts.length) {
        return `
          <div class="empty ok">
            <ha-icon icon="mdi:shield-check-outline"></ha-icon>
            ${card._t("no_alerts")}
          </div>`;
      }
      return `
        <div class="alert-list">
          ${alerts
            .map((alert) => {
              const severity = String(alert.severity || "").toLowerCase();
              const grave = severity === "extreme" || severity === "severe";
              const parts = [
                alert.severity,
                alert.area,
                alert.expires_at
                  ? `${card._t("until")} ${card._formatShortTime(alert.expires_at)}`
                  : null,
              ].filter(Boolean);
              return card._alertBanner(alert, esc(parts.join(" · ")), grave);
            })
            .join("")}
        </div>`;
    },
  },
  {
    type: "okrweather-forecast-card",
    name: "OKRWeather Forecast Card",
    description: "Forecast strip with temperature range bars.",
    titleKey: "forecast",
    defaults: { forecast_type: "daily", forecast_slots: 5 },
    size: 3,
    forecast: true,
    extraSchema: (option) => [
      {
        type: "grid",
        name: "",
        schema: [
          {
            name: "forecast_type",
            selector: {
              select: {
                mode: "dropdown",
                options: ["daily", "hourly", "twice_daily"].map(option),
              },
            },
          },
          {
            name: "forecast_slots",
            selector: { number: { min: 3, max: 8, mode: "slider" } },
          },
        ],
      },
    ],
    render: (card) => {
      const weather = card._hass.states[card._config.entity];
      return weather ? card._forecastStrip(weather) : null;
    },
  },
  {
    type: "okrweather-details-card",
    name: "OKRWeather Details Card",
    description: "Live station readings — pick exactly which values to show.",
    titleKey: "details",
    defaults: { fields: DEFAULT_DETAIL_FIELDS },
    size: 3,
    extraSchema: (option) => [
      {
        name: "fields",
        selector: {
          select: {
            multiple: true,
            mode: "list",
            // "pressure" doubles as the insight label ("Pressure alert") in
            // EDITOR_LABELS, so the field picker uses its own label key.
            options: ALL_DETAIL_FIELDS.map((value) =>
              value === "pressure"
                ? { value, label: option("pressure_field").label }
                : option(value)
            ),
          },
        },
      },
    ],
    render: (card) => {
      const fields = Array.isArray(card._config.fields)
        ? card._config.fields
        : DEFAULT_DETAIL_FIELDS;
      return card._detailsGrid(fields);
    },
  },
];

function defineFeatureCard(spec) {
  class OKRFeatureCard extends OKRBaseCard {
    static async getConfigElement() {
      await loadHaForm();
      const editor = document.createElement("okrweather-feature-editor");
      editor.spec = spec;
      return editor;
    }

    static getStubConfig(hass) {
      return { entity: findStationWeather(hass) };
    }

    setConfig(config) {
      if (!config || !config.entity) {
        throw new Error(
          `${spec.type}: set "entity" to the weather entity of an OKRWeather station`
        );
      }
      this._config = {
        name: "",
        show_title: true,
        background: "none",
        background_intensity: 100,
        ...spec.defaults,
        ...config,
      };
      this._fingerprint = undefined;
      this._entityMap = undefined;
      if (this._hass) {
        this._manageForecast();
        this._render();
      }
    }

    _wantsForecast() {
      return !!spec.forecast;
    }

    getCardSize() {
      return spec.size || 3;
    }

    getGridOptions() {
      return { columns: 6, min_columns: 3 };
    }

    _render() {
      if (!this._hass || !this._config) return;
      const weather = this._hass.states[this._config.entity];
      const amb = this._ambience(weather);

      let body;
      if (!weather) {
        body = `<div class="warning">${this._t("no_entity")}: ${esc(
          this._config.entity
        )}</div>`;
      } else {
        body =
          spec.render(this) ||
          `<div class="empty">
             <ha-icon icon="mdi:timer-sand"></ha-icon>${this._t("empty")}
           </div>`;
      }

      const station = weather?.attributes.friendly_name || "";
      const title = this._config.show_title !== false
        ? `<div class="mini-head">
             <span class="overline">${esc(this._config.name || this._t(spec.titleKey))}</span>
             ${station ? `<span class="mini-station">${esc(station)}</span>` : ""}
           </div>`
        : "";

      this._root.innerHTML = `
        <ha-card class="mini" style="${this._ambienceStyle(amb)}">
          ${amb.wash ? '<div class="wash"></div>' : ""}
          <div class="content">${title}${body}</div>
        </ha-card>
      `;
    }
  }

  customElements.define(spec.type, OKRFeatureCard);
  window.customCards.push({
    type: spec.type,
    name: spec.name,
    description: spec.description,
    preview: true,
    documentationURL: DOCS_URL,
  });
}

// ── Visual editors ──────────────────────────────────────────────────────────

async function loadHaForm() {
  if (customElements.get("ha-form")) return;
  const helpers = await window.loadCardHelpers?.();
  if (!helpers) return;
  // The entities-card editor pulls in ha-form + all selectors.
  const card = await helpers.createCardElement({ type: "entities", entities: [] });
  await card.constructor.getConfigElement?.();
  await customElements.whenDefined("ha-form");
}

const EDITOR_LABELS = {
  en: {
    entity: "Weather entity (OKRWeather station)",
    name: "Title override",
    background: "Background",
    background_intensity: "Background intensity (%)",
    condition: "Follow the weather",
    none: "Theme default (flat)",
    custom: "Custom colors",
    sunrise: "Sunrise",
    amber: "Amber",
    forest: "Forest",
    ocean: "Ocean",
    dusk: "Dusk",
    midnight: "Midnight",
    graphite: "Graphite",
    custom_accent: "Accent color",
    custom_wash_a: "Background color 1",
    custom_wash_b: "Background color 2",
    show_current: "Current conditions",
    show_details: "Details grid",
    show_air_quality: "Air quality",
    show_alerts: "Weather alerts",
    show_forecast: "Forecast",
    show_title: "Show title",
    show_note: "Show advisory text",
    show_factors: "Factor breakdown",
    compact: "Compact mode",
    forecast_type: "Forecast type",
    forecast_slots: "Forecast items",
    insights: "AI insight sections (premium)",
    fields: "Values to show",
    daily: "Daily",
    hourly: "Hourly",
    twice_daily: "Twice daily",
    comfort: "Comfort index",
    radar: "Rain radar",
    storm: "Storm tracker",
    pressure: "Pressure alert",
    frost: "Frost alert",
    solar: "Solar forecast",
    air_trend: "Air quality trend",
    temperature: "Temperature",
    apparent_temperature: "Feels like",
    wind_speed: "Wind",
    wind_gust: "Gust",
    humidity: "Humidity",
    precipitation_rate: "Rain rate",
    precipitation_today: "Rain today",
    uv_index: "UV index",
    solar_radiation: "Solar radiation",
    dew_point: "Dew point",
  },
  pl: {
    entity: "Encja pogody (stacja OKRWeather)",
    name: "Własny tytuł",
    background: "Tło",
    background_intensity: "Intensywność tła (%)",
    condition: "Zgodnie z pogodą",
    none: "Domyślne tło motywu",
    custom: "Własne kolory",
    sunrise: "Świt",
    amber: "Bursztyn",
    forest: "Las",
    ocean: "Ocean",
    dusk: "Zmierzch",
    midnight: "Północ",
    graphite: "Grafit",
    custom_accent: "Kolor akcentu",
    custom_wash_a: "Kolor tła 1",
    custom_wash_b: "Kolor tła 2",
    show_current: "Bieżące warunki",
    show_details: "Siatka szczegółów",
    show_air_quality: "Jakość powietrza",
    show_alerts: "Alerty pogodowe",
    show_forecast: "Prognoza",
    show_title: "Pokaż tytuł",
    show_note: "Pokaż tekst porady",
    show_factors: "Podział na czynniki",
    compact: "Tryb kompaktowy",
    forecast_type: "Rodzaj prognozy",
    forecast_slots: "Liczba pozycji prognozy",
    insights: "Sekcje analiz AI (premium)",
    fields: "Wyświetlane wartości",
    daily: "Dzienna",
    hourly: "Godzinowa",
    twice_daily: "Dwa razy dziennie",
    comfort: "Indeks komfortu",
    radar: "Radar opadów",
    storm: "Śledzenie burz",
    pressure: "Alert ciśnieniowy",
    frost: "Alert przymrozkowy",
    solar: "Prognoza solarna",
    air_trend: "Trend jakości powietrza",
    temperature: "Temperatura",
    apparent_temperature: "Odczuwalna",
    wind_speed: "Wiatr",
    wind_gust: "Porywy",
    humidity: "Wilgotność",
    precipitation_rate: "Natężenie opadu",
    precipitation_today: "Deszcz dziś",
    uv_index: "Indeks UV",
    solar_radiation: "Nasłonecznienie",
    dew_point: "Punkt rosy",
  },
};
// The details field selector reuses the sensor label for "pressure".
EDITOR_LABELS.en.pressure_field = "Pressure";
EDITOR_LABELS.pl.pressure_field = "Ciśnienie";

const BACKGROUND_SCHEMA = (option) => [
  {
    type: "grid",
    name: "",
    schema: [
      {
        name: "background",
        selector: {
          select: { mode: "dropdown", options: BACKGROUND_MODES.map(option) },
        },
      },
      {
        name: "background_intensity",
        selector: { number: { min: 0, max: 200, step: 10, mode: "slider" } },
      },
    ],
  },
];

const CUSTOM_COLOR_SCHEMA = [
  {
    type: "grid",
    name: "",
    schema: [
      { name: "custom_accent", selector: { color_rgb: {} } },
      { name: "custom_wash_a", selector: { color_rgb: {} } },
      { name: "custom_wash_b", selector: { color_rgb: {} } },
    ],
  },
];

class OKRWeatherCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _labels() {
    const lang = (this._hass?.language || "en").startsWith("pl") ? "pl" : "en";
    return EDITOR_LABELS[lang];
  }

  _schema() {
    const labels = this._labels();
    const option = (value) => ({ value, label: labels[value] ?? value });
    return [
      {
        name: "entity",
        required: true,
        selector: {
          entity: {
            filter: [{ integration: INTEGRATION_DOMAIN, domain: "weather" }],
          },
        },
      },
      { name: "name", selector: { text: {} } },
      ...BACKGROUND_SCHEMA(option),
      ...(this._config?.background === "custom" ? CUSTOM_COLOR_SCHEMA : []),
      {
        type: "grid",
        name: "",
        schema: [
          { name: "show_current", selector: { boolean: {} } },
          { name: "show_details", selector: { boolean: {} } },
          { name: "show_air_quality", selector: { boolean: {} } },
          { name: "show_alerts", selector: { boolean: {} } },
          { name: "show_forecast", selector: { boolean: {} } },
          { name: "compact", selector: { boolean: {} } },
        ],
      },
      {
        type: "grid",
        name: "",
        schema: [
          {
            name: "forecast_type",
            selector: {
              select: {
                mode: "dropdown",
                options: ["daily", "hourly", "twice_daily"].map(option),
              },
            },
          },
          {
            name: "forecast_slots",
            selector: { number: { min: 3, max: 8, mode: "slider" } },
          },
        ],
      },
      {
        name: "insights",
        selector: {
          select: {
            multiple: true,
            mode: "list",
            options: ALL_INSIGHTS.map(option),
          },
        },
      },
    ];
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => {
        ev.stopPropagation();
        const config = { ...this._config, ...ev.detail.value };
        this._config = config;
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            bubbles: true,
            composed: true,
            detail: { config },
          })
        );
      });
      this.appendChild(this._form);
    }
    // Memoize per language + background mode / per config object — ha-form
    // dirty-checks by reference, and `hass` is re-assigned on every state
    // change. The schema gains color pickers when background is "custom".
    const lang = (this._hass.language || "en").startsWith("pl") ? "pl" : "en";
    const schemaKey = `${lang}|${this._config?.background === "custom"}`;
    if (this._schemaKey !== schemaKey) {
      this._schemaKey = schemaKey;
      this._schemaCache = this._schema();
      const labels = this._labels();
      this._computeLabel = (schema) => labels[schema.name] ?? schema.name;
    }
    if (this._dataFor !== this._config) {
      this._dataFor = this._config;
      this._dataCache = { ...DEFAULT_CONFIG, ...this._config };
    }
    this._form.hass = this._hass;
    this._form.data = this._dataCache;
    this._form.schema = this._schemaCache;
    this._form.computeLabel = this._computeLabel;
  }
}

class OKRFeatureEditor extends HTMLElement {
  set spec(spec) {
    this._spec = spec;
    this._schemaLang = undefined;
    this._render();
  }

  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _labels() {
    const lang = (this._hass?.language || "en").startsWith("pl") ? "pl" : "en";
    return EDITOR_LABELS[lang];
  }

  _schema() {
    const spec = this._spec;
    const labels = this._labels();
    const option = (value) => ({ value, label: labels[value] ?? value });
    const toggles = [{ name: "show_title", selector: { boolean: {} } }];
    for (const key of Object.keys(spec.defaults)) {
      if (typeof spec.defaults[key] === "boolean") {
        toggles.push({ name: key, selector: { boolean: {} } });
      }
    }
    return [
      {
        name: "entity",
        required: true,
        selector: {
          entity: {
            filter: [{ integration: INTEGRATION_DOMAIN, domain: "weather" }],
          },
        },
      },
      { name: "name", selector: { text: {} } },
      ...BACKGROUND_SCHEMA(option),
      ...(this._config?.background === "custom" ? CUSTOM_COLOR_SCHEMA : []),
      { type: "grid", name: "", schema: toggles },
      ...(spec.extraSchema ? spec.extraSchema(option) : []),
    ];
  }

  _render() {
    if (!this._hass || !this._config || !this._spec) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => {
        ev.stopPropagation();
        const config = { ...this._config, ...ev.detail.value };
        this._config = config;
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            bubbles: true,
            composed: true,
            detail: { config },
          })
        );
      });
      this.appendChild(this._form);
    }
    const lang = (this._hass.language || "en").startsWith("pl") ? "pl" : "en";
    const schemaKey = `${lang}|${this._config?.background === "custom"}`;
    if (this._schemaKey !== schemaKey) {
      this._schemaKey = schemaKey;
      this._schemaCache = this._schema();
      const labels = this._labels();
      this._computeLabel = (schema) => labels[schema.name] ?? schema.name;
    }
    if (this._dataFor !== this._config) {
      this._dataFor = this._config;
      this._dataCache = {
        name: "",
        show_title: true,
        background: "none",
        background_intensity: 100,
        ...this._spec.defaults,
        ...this._config,
      };
    }
    this._form.hass = this._hass;
    this._form.data = this._dataCache;
    this._form.schema = this._schemaCache;
    this._form.computeLabel = this._computeLabel;
  }
}

// ── Registration ────────────────────────────────────────────────────────────

window.customCards = window.customCards || [];

if (!customElements.get(CARD_TYPE)) {
  customElements.define(CARD_TYPE, OKRWeatherCard);
  customElements.define("okrweather-card-editor", OKRWeatherCardEditor);
  customElements.define("okrweather-feature-editor", OKRFeatureEditor);
  window.customCards.push({
    type: CARD_TYPE,
    name: "OKRWeather Card",
    description:
      "Hyperlocal station widget for Pogoda OKR — live readings, air quality, alerts, forecast and premium AI insights.",
    preview: true,
    documentationURL: DOCS_URL,
  });
  for (const spec of FEATURE_CARDS) {
    defineFeatureCard(spec);
  }
}

// The cards ship inside the integration; their version is the integration
// version (manifest.json), which also drives the ?v= cache-buster.
console.info(
  "%c OKRWEATHER-CARDS %c loaded ",
  "background:#1565c0;color:#fff;padding:2px 6px;border-radius:4px 0 0 4px;font-weight:700",
  "background:#37474f;color:#fff;padding:2px 6px;border-radius:0 4px 4px 0"
);
