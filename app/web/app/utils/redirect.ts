/**
 * Same-origin navigation guard for user-supplied paths.
 *
 * `redirect` query values and notification links are attacker-controlled: a
 * crafted `https://app.example.com/login?redirect=//evil.example` would,
 * without this check, send a freshly authenticated user straight to another
 * site (CWE-601, open redirect). Only a path on this origin is accepted.
 *
 * `//host` and `/\host` are protocol-relative URLs — browsers treat both as an
 * absolute URL on another origin — so they are rejected explicitly rather than
 * merely requiring a leading slash.
 */
export function safeInternalPath(value: unknown, fallback = '/'): string {
  if (typeof value !== 'string') return fallback
  const candidate = value.trim()
  if (!candidate.startsWith('/')) return fallback
  if (candidate.startsWith('//') || candidate.startsWith('/\\')) return fallback
  // Control characters can smuggle a scheme or a header through later parsing.
  // Checked as code points rather than a regex so the guard needs no lint
  // suppression for control characters in a pattern.
  for (const character of candidate) {
    const code = character.codePointAt(0) ?? 0
    if (code < 0x20 || code === 0x7f) return fallback
  }
  return candidate
}
