/* Renningenieur - Tablet-Seite (ohne Fremdbibliotheken). */
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const komma = (zahl, stellen = 1) => zahl.toFixed(stellen).replace(".", ",");

const MISCHUNGEN = [
  { kurz: "S", name: "Soft", farbe: "#e8002d" },
  { kurz: "M", name: "Medium", farbe: "#ffd12e" },
  { kurz: "H", name: "Hard", farbe: "#f0f0ec" },
  { kurz: "I", name: "Intermediate", farbe: "#43b02a" },
  { kurz: "W", name: "Regenreifen", farbe: "#0067ad" },
];

/* Schriftfarbe passend zur Fuellfarbe (dunkle Schrift auf Gelb/Weiss). */
function schriftfarbe(hex) {
  const n = parseInt(hex.slice(1), 16);
  const hell = (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
  return hell > 0.6 ? "#14181d" : "#ffffff";
}
function reifenPunkt(kurz, farbe) {
  return `<span class="punkt" style="background:${esc(farbe)};color:${schriftfarbe(farbe)}">${esc(kurz)}</span>`;
}
function rundenzeit(ms) {
  if (!ms) return "–";
  const s = ms / 1000;
  const m = Math.floor(s / 60);
  const rest = (s - m * 60).toFixed(3).padStart(6, "0").replace(".", ",");
  return `${m}:${rest}`;
}
function abstand(ms, runden) {
  if (runden >= 1) return `+${runden} Rd.`;
  if (!ms) return "–";
  if (ms >= 60000) return `+${Math.floor(ms / 60000)}:${komma((ms % 60000) / 1000).padStart(4, "0")}`;
  return `+${komma(ms / 1000)}`;
}
function uhr(sekunden) {
  const m = Math.floor(sekunden / 60);
  return `${m}:${String(Math.floor(sekunden % 60)).padStart(2, "0")}`;
}

/* ------------------------------------------------------------------ */
/* Strategie-Tabelle (Live und Rückblick)                              */
/* ------------------------------------------------------------------ */
function legende(el) {
  el.innerHTML = MISCHUNGEN.map((m) => `<span>${reifenPunkt(m.kurz, m.farbe)}${m.name}</span>`).join("")
    + `<span>▼ Boxenstopp</span>`;
}

function rundenGesamt(daten) {
  let max = daten.session.runden_gesamt || 0;
  for (const a of daten.autos) {
    for (const s of a.stints) max = Math.max(max, s.end_runde || 0, s.start_runde || 0);
    max = Math.max(max, a.runde || 0);
  }
  return Math.max(max, 1);
}

function verlauf(a, gesamt, aktuelleRunde, live) {
  let html = "";
  const KURZ = 0.45; // Anteil einer Runde fuer einen Stint ohne volle Runde
  a.stints.forEach((s, i) => {
    const laeuft = s.end_runde == null;
    const ende = laeuft ? Math.max(a.runde || aktuelleRunde || s.start_runde, s.start_runde) : s.end_runde;
    const davor = a.stints[i - 1];
    const danach = a.stints[i + 1];
    // Zwei Stints in derselben Runde (Wechsel unter roter Flagge): nebeneinander zeichnen
    let von = Math.min(s.start_runde, gesamt) - 1;
    if (davor && davor.end_runde != null && davor.end_runde >= s.start_runde) von += KURZ;
    let bis = Math.min(ende, gesamt);
    if (danach && danach.start_runde <= ende) bis = Math.min(s.start_runde, gesamt) - 1 + KURZ;
    const links = (von / gesamt) * 100;
    const breite = (Math.max(bis - von, 0.3) / gesamt) * 100;
    const runden = Math.max(ende - s.start_runde + 1, 0);
    const tipp = `${s.mischung}|Runde ${s.start_runde}–${ende}${laeuft ? " (läuft)" : ""} · ${runden} ${runden === 1 ? "Runde" : "Runden"}`
      + (s.alter_start ? `|Gebrauchter Satz: ${s.alter_start} ${s.alter_start === 1 ? "Runde" : "Runden"} alt beim Aufziehen` : "")
      + `|${a.name}, Stint ${i + 1}`;
    html += `<div class="stint${laeuft && live ? " laeuft" : ""}" data-tipp="${esc(tipp)}"
      style="left:calc(${links}% + 1px);width:calc(${breite}% - 2px);background:${esc(s.farbe)};color:${schriftfarbe(s.farbe)}">${esc(s.kurz)}</div>`;
  });
  for (const b of a.boxenstopps) {
    html += `<div class="stopp" style="left:${(Math.min(b.runde, gesamt) / gesamt) * 100}%"></div>`;
  }
  if (live && aktuelleRunde) {
    html += `<div class="jetzt" style="left:${(Math.min(aktuelleRunde - 0.5, gesamt) / gesamt) * 100}%"></div>`;
  }
  return `<div class="bahn">${html}</div>`;
}

function skala(gesamt) {
  const schmal = window.innerWidth < 760;
  const schritt = gesamt <= (schmal ? 8 : 15) ? 1 : gesamt <= (schmal ? 20 : 30) ? 5 : 10;
  let html = "";
  for (let r = schritt; r <= gesamt; r += schritt) {
    html += `<span style="left:${((r - 0.5) / gesamt) * 100}%">${r}</span>`;
  }
  return `<div class="skala">${html}</div>`;
}

function strategieTabelle(el, daten, { live = false, kompakt = false } = {}) {
  const gesamt = rundenGesamt(daten);
  const runde = live ? daten.session.runde : 0;
  const kopfLive = `<th class="r">Abstand</th><th class="r nur-breit">Intervall</th><th>Reifen</th>
    <th class="r nur-breit">Verschl.</th><th class="r">Stopps</th>`;
  const kopfAlt = kompakt ? `<th class="r">Stopps</th>`
    : `<th class="r nur-breit">Start</th><th class="r nur-breit">Beste Runde</th><th class="r">Stopps</th>`;
  let html = `<table class="strat"><thead><tr class="achse"><th></th><th>Fahrer</th>${live ? kopfLive : kopfAlt}
    <th>${skala(gesamt)}</th></tr></thead><tbody>`;
  for (const a of daten.autos) {
    const klassen = [a.ist_spieler ? "ich" : "", a.result_status > 3 ? "raus" : ""].join(" ").trim();
    const zusatz = (a.in_box ? `<span class="box">BOX</span>` : "")
      + (!a.ki && !a.ist_spieler ? `<span class="mensch">Mitspieler</span>` : "")
      + (a.result_status > 3 ? ` <span class="leise">${esc(a.status)}</span>` : "");
    let mitte;
    if (live) {
      const r = a.reifen;
      mitte = `<td class="r">${a.position === 1 ? "Führt" : abstand(a.rueckstand_ms, a.runden_zurueck)}</td>
        <td class="r nur-breit">${a.position === 1 ? "" : abstand(a.intervall_ms, 0)}</td>
        <td>${reifenPunkt(r.kurz, r.farbe)} <span class="leise">${a.reifenalter} Rd.</span></td>
        <td class="r nur-breit">${a.verschleiss == null ? "–" : Math.round(a.verschleiss) + " %"}</td>
        <td class="r">${a.boxenstopps_anzahl}</td>`;
    } else if (kompakt) {
      mitte = `<td class="r">${a.boxenstopps_anzahl ?? "–"}</td>`;
    } else {
      mitte = `<td class="r nur-breit">${a.startplatz || "–"}</td>
        <td class="r nur-breit">${rundenzeit(a.beste_runde_ms)}</td>
        <td class="r">${a.boxenstopps_anzahl ?? "–"}</td>`;
    }
    html += `<tr class="${klassen}"><td class="pos">${a.position}</td>
      <td class="name"><span class="team" style="background:${esc(a.farbe)}"></span>${esc(a.name)}${zusatz}</td>
      ${mitte}<td class="verlauf">${verlauf(a, gesamt, runde, live)}</td></tr>`;
  }
  el.innerHTML = html + "</tbody></table>";
}

function wetterverlauf(el, log, gesamtRunden, aktuelleRunde) {
  if (!log || !log.length) { el.innerHTML = `<span class="leise">Keine Wetterdaten.</span>`; return; }
  const ende = Math.max(aktuelleRunde || 0, gesamtRunden || 0, log[log.length - 1].runde + 1, 1);
  el.innerHTML = log.map((w, i) => {
    const bis = i + 1 < log.length ? log[i + 1].runde : ende;
    const dauer = Math.max(bis - w.runde, 0.6);
    const regen = w.wetter >= 3 ? " regen" : "";
    return `<div class="wv${regen}" style="flex-grow:${dauer}" data-tipp="${esc(
      `${w.wetter_name}|ab Runde ${Math.max(w.runde, 1)} (Minute ${Math.floor(w.zeit / 60)})|Strecke ${w.streckentemperatur} °C, Luft ${w.lufttemperatur} °C`)}">
      <b>${esc(w.wetter_name)}</b> ab Rd. ${Math.max(w.runde, 1)}</div>`;
  }).join("");
}

function ereignisliste(el, liste) {
  el.innerHTML = liste.length
    ? liste.slice().reverse().map((e) =>
      `<li><span class="zeit">Rd. ${e.runde} · ${uhr(e.zeit)}</span>${esc(e.text)}</li>`).join("")
    : `<li class="leise">Noch nichts passiert.</li>`;
}

/* ------------------------------------------------------------------ */
/* Tooltip (Finger oder Maus)                                          */
/* ------------------------------------------------------------------ */
const tipp = $("tipp");
function tippZeigen(ziel, x, y) {
  const [titel, ...zeilen] = ziel.dataset.tipp.split("|");
  tipp.innerHTML = `<b>${esc(titel)}</b>${zeilen.map(esc).join("<br>")}`;
  tipp.hidden = false;
  const b = tipp.getBoundingClientRect();
  tipp.style.left = Math.max(8, Math.min(x + 12, window.innerWidth - b.width - 8)) + "px";
  tipp.style.top = Math.max(8, y - b.height - 12) + "px";
}
document.addEventListener("pointerover", (e) => {
  const ziel = e.target.closest("[data-tipp]");
  if (ziel) tippZeigen(ziel, e.clientX, e.clientY); else tipp.hidden = true;
});
document.addEventListener("pointerdown", (e) => {
  const ziel = e.target.closest("[data-tipp]");
  if (ziel) tippZeigen(ziel, e.clientX, e.clientY); else tipp.hidden = true;
});

/* ------------------------------------------------------------------ */
/* Live                                                                */
/* ------------------------------------------------------------------ */
let letzteFrage = null;

function karte(id, titel, wert, zusatz = "") {
  $(id).innerHTML = `<div class="titel">${esc(titel)}</div><div class="wert">${wert}</div>
    <div class="zusatz">${zusatz}</div>`;
}

function liveZeichnen(d) {
  const aktiv = !!d.aktiv;
  $("live-leer").hidden = aktiv;
  $("live-inhalt").hidden = !aktiv;
  const marken = [];
  if (!aktiv) {
    $("titel").textContent = "Renningenieur";
    $("untertitel").textContent = "Warte auf Telemetrie …";
    $("marken").innerHTML = "";
    return;
  }
  const s = d.session;
  $("titel").textContent = `${s.strecke} · ${s.typ_name}`;
  $("untertitel").textContent = s.ist_rennen
    ? `Runde ${Math.min(s.runde, s.runden_gesamt)} von ${s.runden_gesamt} · ${uhr(s.zeit)}`
    : `Session-Zeit ${uhr(s.zeit)}`;
  if (s.rote_flagge) marken.push(`<span class="marke gefahr">Rote Flagge</span>`);
  if (s.safety_car === 1) marken.push(`<span class="marke warn">Safety Car</span>`);
  if (s.safety_car === 2) marken.push(`<span class="marke warn">Virtuelles Safety Car</span>`);
  if (s.safety_car === 3) marken.push(`<span class="marke">Einführungsrunde</span>`);
  if (s.beendet) marken.push(`<span class="marke">Beendet</span>`);
  marken.push(`<span class="marke gut">Live</span>`);
  $("marken").innerHTML = marken.join("");

  const ich = d.autos.find((a) => a.ist_spieler);
  karte("k-runde", "Position", ich ? `P${ich.position}` : "–",
    s.ist_rennen ? `Runde ${Math.min(ich ? ich.runde : s.runde, s.runden_gesamt)} / ${s.runden_gesamt}` : esc(s.typ_name));
  const regen = d.prognose.find((p) => p.wetter >= 3);
  const trocken = d.prognose.find((p) => p.wetter < 3);
  let wetterZusatz = `Strecke ${s.streckentemperatur} °C · Luft ${s.lufttemperatur} °C`;
  if (s.wetter < 3 && regen) wetterZusatz = regen.minuten > 0 ? `Regen in ca. ${regen.minuten} min` : "Regen setzt ein";
  else if (s.wetter >= 3 && trocken && trocken.minuten > 0) wetterZusatz = `Trocken in ca. ${trocken.minuten} min`;
  karte("k-wetter", "Wetter", esc(s.wetter_name), esc(wetterZusatz));
  if (ich) {
    const vorne = d.autos.find((a) => a.position === ich.position - 1);
    const hinten = d.autos.find((a) => a.position === ich.position + 1);
    karte("k-vorne", "Vor dir", vorne ? abstand(ich.intervall_ms, 0) : "–",
      vorne ? `${esc(vorne.name)} · ${esc(vorne.reifen.kurz)} ${vorne.reifenalter} Rd.` : "Du führst");
    karte("k-hinten", "Hinter dir", hinten ? abstand(hinten.intervall_ms, 0) : "–",
      hinten ? `${esc(hinten.name)} · ${esc(hinten.reifen.kurz)} ${hinten.reifenalter} Rd.` : "Niemand");
    karte("k-reifen", "Deine Reifen", `${reifenPunkt(ich.reifen.kurz, ich.reifen.farbe)} ${esc(ich.reifen.name)}`,
      `${ich.reifenalter} ${ich.reifenalter === 1 ? "Runde" : "Runden"} alt` + (ich.verschleiss == null ? "" : ` · ${Math.round(ich.verschleiss)} % Verschleiß`));
  } else {
    for (const id of ["k-vorne", "k-hinten", "k-reifen"]) karte(id, "", "–");
  }

  $("prognose").innerHTML = d.prognose.length
    ? d.prognose.map((p) => `<div class="prog${p.wetter >= 3 ? " regen" : ""}">
        <div class="wann">${p.minuten === 0 ? "jetzt" : "+" + p.minuten + " min"}</div>
        <div class="was">${esc(p.wetter_name)}</div>
        <div class="proz">Regen ${p.regen_prozent} %</div></div>`).join("")
      + (d.prognose_genau ? "" : `<div class="prog"><div class="wann">Hinweis</div><div class="was">ungefähr</div><div class="proz">Prognose ungenau</div></div>`)
    : `<span class="leise">Keine Prognose für diese Session.</span>`;
  wetterverlauf($("wetterverlauf"), d.wetter_log, s.runden_gesamt, s.runde);
  strategieTabelle($("strategie"), d, { live: true });
  ereignisliste($("ereignisse"), d.ereignisse);
  const funk = (d.funk || []).slice().reverse();
  $("funk").innerHTML = (letzteFrage ? `<li class="antwort">${esc(letzteFrage)}</li>` : "")
    + (funk.length ? funk.map((t) => `<li>${esc(t)}</li>`).join("") : `<li class="leise">Noch keine Funksprüche.</li>`);
}

async function liveHolen() {
  if (!$("live").classList.contains("aktiv") || document.hidden) return;
  try {
    const antwort = await fetch("/api/live", { cache: "no-store" });
    liveZeichnen(await antwort.json());
  } catch (e) {
    $("marken").innerHTML = `<span class="marke gefahr">Keine Verbindung zum PC</span>`;
  }
}

$("frage-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("frage-text").value.trim();
  if (!text) return;
  $("frage-text").value = "";
  try {
    const antwort = await fetch("/api/frage", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
    });
    const d = await antwort.json();
    letzteFrage = `„${d.frage}“ → ${d.antwort}`;
  } catch (err) {
    letzteFrage = "Frage konnte nicht gesendet werden.";
  }
  liveHolen();
});

/* ------------------------------------------------------------------ */
/* Rückblick                                                           */
/* ------------------------------------------------------------------ */
let sessions = [];
let offeneSession = null;

function folge(stints) {
  return stints.length
    ? `<span class="folge">${stints.map((s) => reifenPunkt(s.kurz, s.farbe)).join("")}</span>`
    : `<span class="leise">–</span>`;
}
function stoppText(n) {
  return n == null ? "– Stopps" : n === 1 ? "1 Stopp" : `${n} Stopps`;
}
function datum(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
}
function wetterKurz(s) {
  if (!s.wetter_folge || !s.wetter_folge.length) return "";
  const nassAmStart = s.wetter_folge[0] >= 3;
  if (!s.nass) return "trocken";
  return s.wetter_folge.every((w) => w >= 3) ? "nass" : nassAmStart ? "abtrocknend" : "Regen im Rennen";
}

async function sessionsLaden() {
  try {
    sessions = await (await fetch("/api/sessions", { cache: "no-store" })).json();
  } catch (e) { sessions = []; }
  listeZeichnen();
  vergleichZeichnen();
}

function listeZeichnen() {
  const nurRennen = $("rb-nur-rennen").checked;
  const gruppen = new Map();
  for (const s of sessions) {
    if (nurRennen && !s.ist_rennen) continue;
    if (!gruppen.has(s.saison_id)) gruppen.set(s.saison_id, { name: s.saison_name || "Ohne Saison", liste: [] });
    gruppen.get(s.saison_id).liste.push(s);
  }
  if (!gruppen.size) {
    $("rb-saisons").innerHTML = `<div class="hinweis">Noch nichts gespeichert. Nach dem ersten Rennen erscheint es hier.</div>`;
    return;
  }
  let html = "";
  for (const [id, g] of gruppen) {
    html += `<div class="saison"><div class="saison-kopf"><h3>${esc(g.name)}</h3>
      <span class="leise">${g.liste.length} Einträge</span>
      <button data-saison="${id}" data-name="${esc(g.name)}">Umbenennen</button></div>`;
    for (const s of g.liste) {
      html += `<button class="rennen" data-session="${s.id}">
        <span><span class="ort">${esc(s.strecke)}</span><br><span class="leise">${esc(s.typ_name)} · ${datum(s.begonnen)}</span></span>
        <span><span class="platz">${s.spieler_position ? "P" + s.spieler_position : "–"}</span>
          <span class="leise">${s.spieler_startplatz ? " von P" + s.spieler_startplatz : ""}</span></span>
        <span class="leise">${stoppText(s.spieler_stopps)}</span>
        <span>${folge(s.spieler_stints)}</span>
        <span class="leise">${esc(wetterKurz(s))}${s.beendet ? "" : " · unvollständig"}</span></button>`;
    }
    html += "</div>";
  }
  $("rb-saisons").innerHTML = html;
}

function kennzahlen(d) {
  const sieger = d.autos.find((a) => a.position === 1);
  const ich = d.autos.find((a) => a.ist_spieler);
  const gewertet = d.autos.filter((a) => a.boxenstopps_anzahl != null);
  const stopps = gewertet.length ? gewertet.reduce((n, a) => n + a.boxenstopps_anzahl, 0) / gewertet.length : 0;
  const start = {};
  for (const a of d.autos) if (a.stints[0]) start[a.stints[0].kurz] = (start[a.stints[0].kurz] || 0) + 1;
  const startText = Object.entries(start).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${n}× ${k}`).join(", ");
  const wetter = d.wetter_log.map((w) => w.wetter_name).filter((w, i, alle) => i === 0 || w !== alle[i - 1]).join(" → ");
  const feld = (titel, wert) => `<div class="kennzahl"><div class="titel">${titel}</div><div class="wert">${wert}</div></div>`;
  return `<div class="kennzahlen">
    ${feld("Dein Ergebnis", ich ? `P${ich.position} <span class="leise">von P${ich.startplatz || "–"}</span>` : "–")}
    ${feld("Deine Reifen", ich ? folge(ich.stints) : "–")}
    ${feld("Sieger", sieger ? esc(sieger.name) + " " + folge(sieger.stints) : "–")}
    ${feld("Ø Stopps im Feld", komma(stopps))}
    ${feld("Startreifen", esc(startText) || "–")}
    ${feld("Wetter", esc(wetter) || "–")}</div>`;
}

async function sessionOeffnen(id) {
  const d = await (await fetch(`/api/session?id=${id}`, { cache: "no-store" })).json();
  if (!d.aktiv) return;
  offeneSession = id;
  const s = d.session;
  $("rb-liste").hidden = true;
  $("rb-detail").hidden = false;
  $("rb-kopf").innerHTML = `<div class="kopf-daten"><h3>${esc(s.strecke)} · ${esc(s.typ_name)}</h3>
    <span class="leise">${esc(s.saison_name || "")} · ${datum(s.begonnen)} · ${s.runden_gefahren || 0} von ${s.runden_gesamt || "?"} Runden
    ${s.rote_flaggen ? " · " + s.rote_flaggen + "× rote Flagge" : ""}${s.beendet ? "" : " · unvollständig"}</span></div>${kennzahlen(d)}`;
  wetterverlauf($("rb-wetter"), d.wetter_log, s.runden_gesamt, s.runden_gefahren);
  legende($("rb-legende"));
  strategieTabelle($("rb-strategie"), d);
  ereignisliste($("rb-ereignisse"), d.ereignisse);
  window.scrollTo(0, 0);
}

$("rb-saisons").addEventListener("click", async (e) => {
  const saison = e.target.closest("[data-saison]");
  if (saison) {
    const name = prompt("Name der Saison:", saison.dataset.name);
    if (name) {
      await fetch("/api/saison", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ saison_id: Number(saison.dataset.saison), name }) });
      sessionsLaden();
    }
    return;
  }
  const rennen = e.target.closest("[data-session]");
  if (rennen) sessionOeffnen(Number(rennen.dataset.session));
});
$("rb-zurueck").addEventListener("click", () => { $("rb-detail").hidden = true; $("rb-liste").hidden = false; });
$("rb-nur-rennen").addEventListener("change", listeZeichnen);
$("rb-loeschen").addEventListener("click", async () => {
  if (offeneSession == null || !confirm("Diese Session wirklich aus der Datenbank löschen?")) return;
  await fetch("/api/loeschen", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: offeneSession }) });
  $("rb-detail").hidden = true; $("rb-liste").hidden = false;
  sessionsLaden();
});

/* ------------------------------------------------------------------ */
/* Vergleich                                                           */
/* ------------------------------------------------------------------ */
function vergleichZeichnen() {
  const rennen = sessions.filter((s) => s.ist_rennen);
  // --- Saison-Matrix ---
  const saisons = [];
  const strecken = [];
  for (const s of rennen.slice().reverse()) {
    if (!saisons.some((x) => x.id === s.saison_id)) saisons.push({ id: s.saison_id, name: s.saison_name || "Ohne Saison" });
    if (!strecken.includes(s.strecke)) strecken.push(s.strecke);
  }
  if (!rennen.length) {
    $("vg-saisons").innerHTML = `<div class="hinweis">Noch keine Rennen gespeichert.</div>`;
  } else {
    let html = `<table class="matrix"><thead><tr><th>Strecke</th>${saisons.map((s) => `<th>${esc(s.name)}</th>`).join("")}</tr></thead><tbody>`;
    for (const strecke of strecken) {
      html += `<tr><th>${esc(strecke)}</th>`;
      for (const saison of saisons) {
        const treffer = rennen.filter((s) => s.strecke === strecke && s.saison_id === saison.id).reverse();
        html += "<td>" + (treffer.map((s) => `<div><span class="zelle-platz">${s.spieler_position ? "P" + s.spieler_position : "–"}</span>
          ${folge(s.spieler_stints)} <span class="leise">${stoppText(s.spieler_stopps)} · ${esc(wetterKurz(s))}</span></div>`).join("")
          || `<span class="leise">–</span>`) + "</td>";
      }
      html += "</tr>";
    }
    $("vg-saisons").innerHTML = html + "</tbody></table>";
  }
  // --- Auswahl fuer den Rennvergleich ---
  const optionen = rennen.map((s) =>
    `<option value="${s.id}">${esc(s.strecke)} · ${esc(s.saison_name || "")} · ${datum(s.begonnen)}</option>`).join("");
  for (const [id, standard] of [["vg-a", 0], ["vg-b", 1]]) {
    const alt = $(id).value;
    $(id).innerHTML = optionen;
    if (alt && rennen.some((s) => String(s.id) === alt)) $(id).value = alt;
    else if (rennen[standard]) $(id).value = rennen[standard].id;
  }
  rennenVergleichen();
}

async function rennenVergleichen() {
  const ziel = $("vg-rennen");
  const ids = [$("vg-a").value, $("vg-b").value].filter(Boolean);
  if (ids.length < 2) { ziel.innerHTML = `<div class="hinweis">Für den Vergleich braucht es zwei gespeicherte Rennen.</div>`; return; }
  const daten = await Promise.all(ids.map((id) => fetch(`/api/session?id=${id}`, { cache: "no-store" }).then((r) => r.json())));
  ziel.innerHTML = daten.map((d, i) => d.aktiv
    ? `<div class="vg-spalte"><h3>${esc(d.session.strecke)} <span class="leise">${esc(d.session.saison_name || "")} · ${datum(d.session.begonnen)}</span></h3>
        ${kennzahlen(d)}<div id="vg-tab-${i}"></div></div>`
    : `<div class="hinweis">Rennen nicht gefunden.</div>`).join("");
  daten.forEach((d, i) => { if (d.aktiv) strategieTabelle($(`vg-tab-${i}`), d, { kompakt: true }); });
}
$("vg-a").addEventListener("change", rennenVergleichen);
$("vg-b").addEventListener("change", rennenVergleichen);

/* ------------------------------------------------------------------ */
/* Reiter und Start                                                    */
/* ------------------------------------------------------------------ */
document.querySelector(".reiter").addEventListener("click", (e) => {
  const knopf = e.target.closest("[data-reiter]");
  if (!knopf) return;
  for (const b of document.querySelectorAll(".reiter button")) b.classList.toggle("aktiv", b === knopf);
  for (const a of document.querySelectorAll(".ansicht")) a.classList.toggle("aktiv", a.id === knopf.dataset.reiter);
  if (knopf.dataset.reiter === "live") liveHolen();
  else if (knopf.dataset.reiter !== "befehle") sessionsLaden();
});

legende($("legende"));
liveHolen();
setInterval(liveHolen, 1000);
