/**
 * CellChain product mark.
 *
 * An original application logo in the corporate style (charcoal tile, signature yellow
 * accent). It is deliberately NOT the EY corporate logo, which is a registered trademark
 * and must not be reproduced by an application.
 *
 * The mark reads as a chain link crossing a beam: the chain of identity travelling through
 * the manufacturing journey.
 */
export default function Logo({ size = 32 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label="CellChain"
      style={{ display: 'block', flex: '0 0 auto' }}
    >
      <rect width="32" height="32" rx="5" fill="#FFE600" />
      <path d="M6.5 22.5 L15 7.5 L18.6 13.8 L12.2 22.5 Z" fill="#2E2E38" />
      <circle cx="21.6" cy="19.4" r="4.3" fill="none" stroke="#2E2E38" strokeWidth="2.6" />
    </svg>
  );
}
