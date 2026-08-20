# Prague Transit 3D

Every tram, metro, bus, trolleybus, train and ferry in the Prague Integrated
Transport network, live, on a photorealistic 3D model of the city.

![status](https://img.shields.io/badge/build-single%20HTML%20file-4da3ff)

## What it does

| | |
|---|---|
| **Live vehicles** | Positions refresh every 4 s and are interpolated between updates, so motion is continuous rather than teleporting. |
| **Real rolling stock** | Vehicles render as correctly sized 3D bodies — a bus is one box, a Škoda 15T tram is three (31.4 m), a metro train is five cars (96.5 m). They appear automatically as you zoom in. |
| **Ground-relative height** | Trams and buses sit on the street, trains run below it, metro sits 22 m down — translucent and drawn through the city so it stays readable. |
| **Track network** | The physical rail network: tram, metro and heavy rail, coloured by type. |
| **Click a vehicle** | Draws that line and only that line, and shows delay, speed, vehicle number, air conditioning and step-free access. |
| **Click a stop** | Live departure board — line, destination, minutes away, delay. |
| **Stops layer** | PID's 17,000 stop records, clipped to Prague, deduplicated down to real stops. |

Controls: mode filters with live counts, line search, colour-by-delay, x-ray
through buildings, follow-cam, camera presets, auto-orbit.

## How it is built

Single HTML file, no dependencies to install. CesiumJS loads at runtime from
Cesium's own CDN with three mirrors behind it.

A few decisions worth knowing about if you read the source:

- **Interpolation.** The render clock deliberately runs a few seconds behind
  wall time, so each vehicle animates between its last two reported positions
  instead of jumping. Poll interval and clock lag move together.
- **Rate limiting.** The transit API allows 20 requests per 8 s. Every call goes
  through a sliding-window gate, and background work yields to live polling so a
  vehicle update always gets through.
- **Vehicle orientation.** Box axes come from an explicitly constructed
  right-handed basis (`right`, `forward`, `up`) rather than Cesium's
  heading/pitch/roll convention, verified numerically — a sign error there parks
  every tram sideways across the street.
- **Terrain.** Street heights are sampled from a *separate* Cesium World Terrain
  provider, not the rendered scene. Sampling the scene would hit the vehicle
  boxes and return the roof of a tram instead of the road.
- **Performance.** 3D bodies are limited to the nearest ~80–140 vehicles, scaled
  by camera altitude. Stops render as a `PointPrimitiveCollection` and tracks as
  a `PolylineCollection`, because a few thousand entities each would not hold
  frame rate.

---

## Data sources and licences

| Source | Used for | Licence |
|---|---|---|
| [Golemio / PID](https://api.golemio.cz) | Live vehicle positions, stops, departures | CC-BY |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) via [Overpass](https://overpass-api.de) | Track and route geometry | ODbL |
| [Cesium ion](https://cesium.com) + Google Photorealistic 3D Tiles | 3D city model, terrain | Cesium ion terms |

Rolling stock dimensions from the Škoda 15T, 81-71M/M1 and ČD 471 specifications.
