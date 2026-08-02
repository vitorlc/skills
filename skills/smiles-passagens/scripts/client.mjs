/** HTTP client — endpoint assembled at runtime (not stored in plain text in docs). */

function b64(s) {
  return Buffer.from(s, "base64").toString("utf8");
}

/** Optional override: CALENDAR_API_URL=https://host/path */
export function calendarEndpoint() {
  if (process.env.CALENDAR_API_URL) {
    return process.env.CALENDAR_API_URL.replace(/\/$/, "");
  }
  const host = b64("YXBpLWFpci1jYWxlbmRhci1wcmQuc21pbGVzLmNvbS5icg==");
  const path = b64("djEvYWlybGluZXMvY2FsZW5kYXIvbW9udGg=");
  return `https://${host}/${path}`;
}

function browserHeaders(host) {
  const originHost = b64("d3d3LnNtaWxlcy5jb20uYnI=");
  return {
    authority: host,
    accept: "application/json",
    "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    origin: `https://${originHost}`,
    referer: `https://${originHost}/`,
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent":
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
  };
}

export async function httpGetJson(url) {
  const u = new URL(url);
  const res = await fetch(url, {
    method: "GET",
    headers: browserHeaders(u.host),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    const err = new Error(`HTTP ${res.status}${body ? `: ${body.slice(0, 200)}` : ""}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}
