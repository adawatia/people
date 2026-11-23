/**
 * Format a human-readable device/browser label from a User-Agent string.
 *
 * Handles standard browsers (Chrome, Edge, Safari, Firefox, Opera, Brave),
 * operating systems (Windows, macOS, iOS, Android, Linux, ChromeOS),
 * and server/CLI clients (Node.js, curl, Python, Postman).
 */
export function formatDeviceLabel(userAgent?: string | null): string {
  if (!userAgent || !userAgent.trim()) {
    return 'Unknown device'
  }
  const ua = userAgent.trim()

  // Common CLI / server environments
  if (/^node(\b|[-/])/i.test(ua)) return 'Node.js (Server / CLI)'
  if (/^python/i.test(ua)) return 'Python client'
  if (/^postman/i.test(ua)) return 'Postman'
  if (/^curl/i.test(ua)) return 'cURL'

  // Operating systems
  let os = ''
  if (/windows nt 10/i.test(ua)) os = 'Windows 10/11'
  else if (/windows nt 6\.3/i.test(ua)) os = 'Windows 8.1'
  else if (/windows nt 6\.2/i.test(ua)) os = 'Windows 8'
  else if (/windows nt 6\.1/i.test(ua)) os = 'Windows 7'
  else if (/windows/i.test(ua)) os = 'Windows'
  else if (/iphone/i.test(ua)) os = 'iPhone'
  else if (/ipad/i.test(ua)) os = 'iPad'
  else if (/macintosh|mac os x/i.test(ua)) os = 'macOS'
  else if (/android/i.test(ua)) os = 'Android'
  else if (/cros/i.test(ua)) os = 'ChromeOS'
  else if (/linux/i.test(ua)) os = 'Linux'

  // Browsers (ordered to check specific vendors before base engines)
  let browser = ''
  if (/edg([ea]|ios)?\//i.test(ua)) browser = 'Edge'
  else if (/opr\/|opera/i.test(ua)) browser = 'Opera'
  else if (/brave/i.test(ua)) browser = 'Brave'
  else if (/chrome|crios/i.test(ua)) browser = 'Chrome'
  else if (/firefox|fxios/i.test(ua)) browser = 'Firefox'
  else if (/version\/.*safari/i.test(ua) || /safari/i.test(ua)) browser = 'Safari'

  if (browser && os) {
    return `${browser} on ${os}`
  }
  if (browser) return browser
  if (os) return os

  // Fallback: extract the primary token inside parentheses if available (e.g. "Windows NT 10.0; Win64; x64")
  const match = ua.match(/\(([^)]+)\)/)
  if (match?.[1]) {
    const candidate = match[1].split(';')[0]?.trim()
    if (candidate) return candidate
  }

  return ua.length > 35 ? `${ua.slice(0, 35)}…` : ua
}
