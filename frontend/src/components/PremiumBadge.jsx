/**
 * Bootstrap Icons (v1.13) has no crown glyph at all, so the premium mark is
 * a tiny inline SVG — it renders on the site, in the panel and in emails
 * without depending on the icon font.
 */
export function CrownIcon({ size = 12 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
      style={{ display: 'inline-block', verticalAlign: '-0.125em', flex: 'none' }}
    >
      <path d="M8 1.6l1.9 3.7 4.1.6-3 2.9.7 4.1L8 11l-3.7 1.9.7-4.1-3-2.9 4.1-.6L8 1.6z" />
      <path d="M2.8 13.1h10.4v1.5H2.8z" />
    </svg>
  )
}

/**
 * The 👑 next to a name. The server decides who gets it
 * (`is_premium` on the user / comment author — paid plan, not expired);
 * the frontend only draws it.
 */
export default function PremiumBadge({ compact = false }) {
  return (
    <span className={`premium-badge${compact ? ' compact' : ''}`} title="Obunachi">
      <CrownIcon size={11} />
      {!compact && <span>Obunachi</span>}
    </span>
  )
}
