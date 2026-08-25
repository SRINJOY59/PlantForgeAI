// Where a backend actually lives, as opposed to where the build was told it
// lives.
//
// Every backend URL in this app is a VITE_* value baked in at build time, which
// means the build has to guess a scheme it cannot know: the same bundle is
// served over http and https, and a page on https may not call an http origin.
// The browser blocks it as active mixed content - killed in the tab, nothing on
// the network, nothing in any server log. The only symptom is a feature that
// works perfectly on one scheme and looks like a dead backend on the other.
//
// That has now cost us the freshness pill ("brain offline" on https) and the
// interview service, so the rule lives in one place instead of being
// rediscovered per client.
//
// The configured scheme is a DEFAULT, not an instruction. Upgrading http to
// https to match the page is always safe: an https page cannot reach an http
// backend at all, so a backend that is not also on https is already unusable
// from that page. Downgrading is never done - that would take a page the user
// loaded securely and start sending its traffic in clear.
//
// localhost is exempt, because the browser exempts it too: it counts as a
// secure context whatever the scheme, so `npm run dev` keeps working against a
// local service that has no certificate.

const LOOPBACK = /^http:\/\/(localhost|127\.0\.0\.1|\[::1\])(:|\/|$)/;

export function resolveBackendUrl(configured, fallback) {
  const url = configured || fallback;
  if (typeof window === "undefined") return url;          // SSR / tests
  if (window.location.protocol !== "https:") return url;  // page is not secure
  if (!url.startsWith("http://")) return url;             // already https/ws
  if (LOOPBACK.test(url)) return url;                     // dev, exempt anyway
  return "https://" + url.slice("http://".length);
}
