/**
 * CellChain product mark — a hex cell with a luminous chain node.
 * Original artwork, not a third-party trademark.
 */
export default function Logo({ size = 32 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label="CellChain"
      style={{ display: 'block', flex: '0 0 auto', filter: 'drop-shadow(0 0 8px rgba(6,182,212,0.55))' }}
    >
      <defs>
        <linearGradient id="cc-hex" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#22d3ee" />
          <stop offset="100%" stopColor="#0891b2" />
        </linearGradient>
      </defs>
      <polygon
        points="16,2 28,9 28,23 16,30 4,23 4,9"
        fill="#04151c"
        stroke="url(#cc-hex)"
        strokeWidth="1.6"
      />
      <path d="M10 20.5 L16 9.5 L19.2 15.2 L13.6 20.5 Z" fill="#22d3ee" />
      <circle cx="20.6" cy="18.8" r="3.4" fill="none" stroke="#10b981" strokeWidth="2.1" />
    </svg>
  );
}
