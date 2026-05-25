# OKRWeather (Pogoda OKR)

Hyperlocal weather data for **Powiat Krapkowicki** (Opolskie, Poland) — live readings from physical stations in Gogolin, Krapkowice and surrounding villages, plus forecasts, alerts and AI-derived advisories.

## What you get

**Free (no API key):**
- Live weather (temperature, humidity, wind, pressure, UV, dew point, soil moisture, ground temp, precipitation)
- Air quality (PM2.5, PM10, CO, NO₂, NH₃)
- Hourly and daily forecasts as a HA `weather` entity
- Weather alerts (warning sensor + binary)

**Premium (with API key):**
- Comfort index 0–100
- Frost alert (probability, window, advisory)
- Solar production forecast (kWh, peak kW, efficiency)
- Running & cycling condition scores
- Laundry drying conditions (VPD-based)
- Outfit recommendations
- Pressure-headache alert
- Storm tracker
- Air-quality trend

## After installing

Add the integration via **Settings → Devices & Services → Add integration → OKRWeather**.

Provide your Appwrite API key only if you have a premium subscription — leave blank for free public data.
