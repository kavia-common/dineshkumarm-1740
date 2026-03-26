async function fetchJson(path) {
  const res = await fetch(path, { credentials: "include" });
  const text = await res.text();
  try {
    return { ok: res.ok, status: res.status, json: JSON.parse(text) };
  } catch {
    return { ok: res.ok, status: res.status, json: { raw: text } };
  }
}

function pretty(obj) {
  return JSON.stringify(obj, null, 2);
}

async function main() {
  const sessionEl = document.getElementById("session");
  const statusEl = document.getElementById("status");

  const session = await fetchJson("/api/session");
  sessionEl.textContent = pretty(session.json);

  const status = await fetchJson("/api/dataset/status");
  statusEl.textContent = pretty(status.json);
}

main().catch((e) => {
  console.error(e);
});
