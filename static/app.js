const tbody = document.getElementById("tbody");
const search = document.getElementById("search");
const sort = document.getElementById("sort");
const order = document.getElementById("order");
const refreshBtn = document.getElementById("refresh");
const autoRefresh = document.getElementById("autoRefresh");
const tokenInput = document.getElementById("token");

let timer = null;

function humanBytes(n) {
  if (!n && n !== 0) return "";
  const units = ["B","KB","MB","GB","TB"];
  let i = 0, v = n;
  while (v >= 1024 && i < units.length-1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${units[i]}`;
}

function portCell(ports) {
  if (!ports || !ports.length) return "";
  return ports.slice(0,4).map(p => {
    const l = p.local || "";
    const r = p.remote || "";
    const s = p.status || "";
    return `<div class="port-pill" title="${s}">${l}${r ? " → "+r : ""}</div>`;
  }).join("") + (ports.length > 4 ? `<div class="more">+${ports.length-4}</div>` : "");
}

async function fetchProcesses() {
  const q = search.value.trim();
  const params = new URLSearchParams({
    q, sort: sort.value, order: order.value
  });
  const res = await fetch(`/api/processes?${params}`, {
    headers: {"X-Auth-Token": tokenInput.value || ""}
  });
  if (!res.ok) {
    tbody.innerHTML = `<tr><td colspan="9" class="error">Erreur: ${res.status}</td></tr>`;
    return;
  }
  const data = await res.json();
  renderRows(data.items || []);
}

function renderRows(items) {
  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty">Aucun processus</td></tr>`;
    return;
  }
  tbody.innerHTML = items.map(p => {
    const cmd = (p.cmdline && p.cmdline.length) ? p.cmdline.join(" ") : "";
    return `
      <tr>
        <td>${p.pid}</td>
        <td><span class="name">${p.name || ""}</span></td>
        <td>${p.username || ""}</td>
        <td>${(p.cpu_percent || 0).toFixed(1)}</td>
        <td>${humanBytes(p.memory_rss)}</td>
        <td>${portCell(p.ports)}</td>
        <td class="cmd">${cmd}</td>
        <td>
          <input type="number" class="nice-input" value="${p.nice}" data-pid="${p.pid}" />
          <button class="btn renice" data-pid="${p.pid}">OK</button>
        </td>
        <td class="actions">
          <button class="btn warn" data-action="signal" data-sig="TERM" data-pid="${p.pid}">Stop</button>
          <button class="btn danger" data-action="signal" data-sig="KILL" data-pid="${p.pid}">Tuer</button>
          <button class="btn" data-action="signal" data-sig="HUP" data-pid="${p.pid}">HUP</button>
          <button class="btn" data-action="restart" data-pid="${p.pid}">Relancer</button>
        </td>
      </tr>
    `;
  }).join("");

  // Wire buttons
  tbody.querySelectorAll("button[data-action='signal']").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      const pid = e.currentTarget.dataset.pid;
      const sig = e.currentTarget.dataset.sig;
      await callSignal(pid, sig);
      await fetchProcesses();
    });
  });

  tbody.querySelectorAll("button.renice").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      const pid = e.currentTarget.dataset.pid;
      const input = tbody.querySelector(`input.nice-input[data-pid="${pid}"]`);
      const nice = parseInt(input.value || "0", 10);
      await callRenice(pid, nice);
      await fetchProcesses();
    });
  });

  tbody.querySelectorAll("button[data-action='restart']").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      const pid = e.currentTarget.dataset.pid;
      await callRestart(pid);
      await fetchProcesses();
    });
  });
}

async function callSignal(pid, signalName) {
  const res = await fetch(`/api/process/${pid}/signal`, {
    method: "POST",
    headers: {
      "Content-Type":"application/json",
      "X-Auth-Token": tokenInput.value || ""
    },
    body: JSON.stringify({signal: signalName})
  });
  if (!res.ok) alert(`Signal ${signalName} -> PID ${pid} a échoué (${res.status})`);
}

async function callRenice(pid, nice) {
  const res = await fetch(`/api/process/${pid}/renice`, {
    method: "POST",
    headers: {
      "Content-Type":"application/json",
      "X-Auth-Token": tokenInput.value || ""
    },
    body: JSON.stringify({nice})
  });
  if (!res.ok) alert(`Renice PID ${pid} a échoué (${res.status})`);
}

async function callRestart(pid) {
  const res = await fetch(`/api/process/${pid}/restart`, {
    method: "POST",
    headers: {
      "Content-Type":"application/json",
      "X-Auth-Token": tokenInput.value || ""
    }
  });
  if (!res.ok) alert(`Relance PID ${pid} a échoué (${res.status})`);
}

refreshBtn.addEventListener("click", fetchProcesses);
[search, sort, order, tokenInput].forEach(el => el.addEventListener("input", () => {
  fetchProcesses();
}));

function startAuto() {
  if (timer) clearInterval(timer);
  if (autoRefresh.checked) {
    timer = setInterval(fetchProcesses, 3000);
  }
}
autoRefresh.addEventListener("change", startAuto);

// Init
fetchProcesses();
startAuto();
