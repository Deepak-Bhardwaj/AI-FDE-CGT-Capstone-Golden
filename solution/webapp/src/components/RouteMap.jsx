/**
 * Route map.
 *
 * Inline SVG on an equirectangular projection. Landmasses are coarse hand-drawn polygons and
 * coordinates come from the API's local reference table — the component issues no network
 * request of any kind, so it works with external communication disabled.
 *
 * It is a schematic for orientation, not a navigational chart.
 */

const WIDTH = 960;
const HEIGHT = 420;

const project = (lat, lon) => [
  ((lon + 180) / 360) * WIDTH,
  ((90 - lat) / 180) * HEIGHT,
];

const toPath = (points) =>
  `${points.map(([lon, lat], i) => {
    const [x, y] = project(lat, lon);
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(' ')} Z`;

// Deliberately coarse outlines: enough to orient a marker, not a cartographic product.
const LANDMASSES = [
  [[-168, 65], [-140, 70], [-125, 60], [-123, 49], [-117, 33], [-105, 23], [-97, 18],
   [-83, 10], [-80, 25], [-75, 35], [-66, 45], [-56, 50], [-64, 60], [-78, 70], [-95, 72], [-125, 72]],
  [[-45, 60], [-20, 70], [-25, 83], [-60, 83], [-58, 70]],
  [[-81, 8], [-70, 12], [-60, 5], [-50, 0], [-35, -5], [-38, -15], [-48, -25], [-58, -35],
   [-65, -45], [-72, -52], [-75, -45], [-71, -30], [-70, -18], [-80, -5]],
  [[-10, 36], [0, 44], [10, 38], [18, 40], [28, 41], [30, 45], [40, 48], [30, 60], [28, 70],
   [10, 63], [5, 58], [-5, 50], [-10, 43]],
  [[-17, 15], [0, 16], [15, 32], [32, 31], [43, 12], [51, 12], [40, -5], [40, -18], [32, -26],
   [20, -35], [15, -30], [12, -5], [8, 4], [-8, 5]],
  [[30, 45], [45, 42], [60, 45], [75, 40], [90, 28], [100, 22], [105, 10], [110, 20], [122, 30],
   [130, 43], [140, 50], [150, 60], [160, 70], [130, 72], [100, 78], [70, 72], [50, 70], [35, 65], [30, 55]],
  [[113, -22], [130, -12], [142, -11], [147, -19], [153, -28], [150, -38], [140, -38], [130, -32], [115, -35]],
  [[-6, 50], [-2, 50], [1, 52], [-1, 58], [-5, 58]],
  [[130, 32], [140, 36], [142, 43], [145, 44], [140, 40], [134, 34]],
];

export default function RouteMap({ route, status }) {
  if (!route) return null;

  const { origin, destination, position } = route;
  const [ox, oy] = project(origin.lat, origin.lon);
  const [dx, dy] = project(destination.lat, destination.lon);
  const [px, py] = project(position.lat, position.lon);

  // Curve the leg so long-haul routes read as an arc rather than a chord.
  const mx = (ox + dx) / 2;
  const my = (oy + dy) / 2 - Math.min(70, Math.abs(dx - ox) * 0.22);

  const inTransit = position.estimated;

  return (
    <figure className="routemap">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img"
           aria-label={`Route from ${origin.city} to ${destination.city}`}>
        <rect width={WIDTH} height={HEIGHT} className="routemap__ocean" />

        {[-60, -30, 0, 30, 60].map((lat) => (
          <line key={`lat${lat}`} x1={0} x2={WIDTH}
                y1={project(lat, 0)[1]} y2={project(lat, 0)[1]} className="routemap__grid" />
        ))}
        {[-120, -60, 0, 60, 120].map((lon) => (
          <line key={`lon${lon}`} y1={0} y2={HEIGHT}
                x1={project(0, lon)[0]} x2={project(0, lon)[0]} className="routemap__grid" />
        ))}

        {LANDMASSES.map((shape, i) => (
          <path key={i} d={toPath(shape)} className="routemap__land" />
        ))}

        <path d={`M${ox} ${oy} Q${mx} ${my} ${dx} ${dy}`} className="routemap__leg" />
        {inTransit && (
          <path d={`M${ox} ${oy} Q${mx} ${my} ${dx} ${dy}`} className="routemap__leg-done"
                style={{ strokeDasharray: 1000, strokeDashoffset: 1000 * (1 - position.fraction) }} />
        )}

        <g className="routemap__pin">
          <circle cx={ox} cy={oy} r="6" className="routemap__origin" />
          <text x={ox} y={oy - 12} textAnchor="middle">{origin.city}</text>
        </g>
        <g className="routemap__pin">
          <circle cx={dx} cy={dy} r="6" className="routemap__dest" />
          <text x={dx} y={dy - 12} textAnchor="middle">{destination.city}</text>
        </g>

        {inTransit && (
          <g className="routemap__pin">
            <circle cx={px} cy={py} r="9" className="routemap__now-halo" />
            <circle cx={px} cy={py} r="4.5" className="routemap__now" />
            <text x={px} y={py + 22} textAnchor="middle">Estimated position</text>
          </g>
        )}
      </svg>

      <figcaption className="routemap__caption">
        <span>
          <strong>{origin.city}</strong>{origin.country ? `, ${origin.country}` : ''} →{' '}
          <strong>{destination.city}</strong>{destination.country ? `, ${destination.country}` : ''}
          {' · '}{route.distance_km.toLocaleString()} km great-circle
          {' · '}{status}
        </span>
        <span className="routemap__note">
          Schematic drawn from locally held coordinates. No mapping service is contacted.
          {inTransit && ' Position is estimated from elapsed time against the service level, not from carrier telemetry.'}
        </span>
      </figcaption>
    </figure>
  );
}
