/* Mikrofon-Taste: Das Tablet nimmt auf, der PC erkennt und antwortet.
 *
 * Ablauf: Tippen -> Mikrofon oeffnen -> Aufnahme. Sie endet, wenn man ein
 * paar Sekunden nichts mehr sagt (oder durch erneutes Tippen oder nach der
 * Hoechstdauer). Der Ton geht als 16-Bit-PCM an den PC (/api/sprache), der
 * ihn lokal erkennt. Die Antwort kommt als Text zurueck und wird am PC
 * ueber die Kopfhoerer gesprochen.
 */
"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const knopf = $("mikro"), panel = $("mikro-panel"), statusZeile = $("mikro-status");
  const balken = $("mikro-pegel"), frageZeile = $("mikro-frage"), antwortZeile = $("mikro-antwort");
  const hinweisZeile = $("mikro-hinweis"), banner = $("mikro-banner");
  if (!knopf) return;

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const BLOCK = 2048;
  const LEERLAUF_MS = 45000; // so lange bleibt das Mikrofon nach einer Frage offen
  let einstellungen = { mikrofon: false, https_port: 0, ca: false, stille_sekunden: 1,
                        max_sekunden: 8, feste_sekunden: 0, warten_sekunden: 5 };

  let zustand = "bereit"; // bereit | oeffnen | hoert | sendet
  let stream = null, ctx = null, quelle = null, erfasser = null, stumm = null;
  let leerlauf = null, ausblenden = null, aufnahme = null;

  function setzen(neu, text) {
    zustand = neu;
    knopf.dataset.zustand = neu;
    knopf.setAttribute("aria-label", { bereit: "Frage stellen", oeffnen: "Mikrofon wird geöffnet",
      hoert: "Aufnahme beenden", sendet: "Wird ausgewertet" }[neu]);
    if (text !== undefined) { statusZeile.textContent = text; panel.hidden = false; }
    clearTimeout(ausblenden);
  }

  function zeigeErgebnis(frage, antwort, hinweis) {
    frageZeile.innerHTML = frage ? `<span class="leise">Du:</span> „${esc(frage)}“` : "";
    antwortZeile.innerHTML = antwort ? `<span class="leise">Ingenieur:</span> ${esc(antwort)}` : "";
    hinweisZeile.textContent = hinweis || "";
    hinweisZeile.hidden = !hinweis;
    ausblenden = setTimeout(() => { if (zustand === "bereit") panel.hidden = true; }, 25000);
  }

  function leeren() {
    frageZeile.textContent = antwortZeile.textContent = hinweisZeile.textContent = "";
    hinweisZeile.hidden = true;
    balken.style.width = "0%";
  }

  /* ---------------------------------------------------------------- */
  /* Mikrofon                                                          */
  /* ---------------------------------------------------------------- */
  const WORKLET = `
    class Erfasser extends AudioWorkletProcessor {
      constructor() { super(); this.puffer = new Float32Array(${BLOCK}); this.n = 0; }
      process(eingaenge) {
        const kanal = eingaenge[0] && eingaenge[0][0];
        if (kanal) for (let i = 0; i < kanal.length; i++) {
          this.puffer[this.n++] = kanal[i];
          if (this.n === ${BLOCK}) { this.port.postMessage(this.puffer.slice(0)); this.n = 0; }
        }
        return true;
      }
    }
    registerProcessor("erfasser", Erfasser);`;

  async function mikrofonOeffnen() {
    if (stream && ctx && ctx.state !== "closed") {
      if (ctx.state === "suspended") await ctx.resume();
      return;
    }
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: false, noiseSuppression: true, autoGainControl: true },
    });
    const AC = window.AudioContext || window.webkitAudioContext;
    ctx = new AC({ latencyHint: "interactive" });
    if (ctx.state === "suspended") await ctx.resume();
    quelle = ctx.createMediaStreamSource(stream);
    stumm = ctx.createGain();
    stumm.gain.value = 0; // nichts auf den Lautsprecher legen
    stumm.connect(ctx.destination);
    if (ctx.audioWorklet) {
      const url = URL.createObjectURL(new Blob([WORKLET], { type: "text/javascript" }));
      await ctx.audioWorklet.addModule(url);
      erfasser = new AudioWorkletNode(ctx, "erfasser");
      erfasser.port.onmessage = (e) => block(e.data);
    } else {
      erfasser = ctx.createScriptProcessor(BLOCK, 1, 1);
      erfasser.onaudioprocess = (e) => block(e.inputBuffer.getChannelData(0).slice(0));
    }
    quelle.connect(erfasser);
    erfasser.connect(stumm);
  }

  function mikrofonSchliessen() {
    clearTimeout(leerlauf);
    try { stream && stream.getTracks().forEach((t) => t.stop()); } catch (e) { /* egal */ }
    try { ctx && ctx.close(); } catch (e) { /* egal */ }
    stream = ctx = quelle = erfasser = stumm = null;
  }

  /* ---------------------------------------------------------------- */
  /* Aufnahme mit Stille-Erkennung                                     */
  /* ---------------------------------------------------------------- */
  function neueAufnahme() {
    return { bloecke: [], proben: 0, rauschen: [], grenze: 0.02, laut: 0, sprachStart: null,
             letzteSprache: 0, fertig: false, spitze: 0 };
  }

  function effektiv(x) {
    let s = 0;
    for (let i = 0; i < x.length; i++) s += x[i] * x[i];
    return Math.sqrt(s / x.length);
  }

  function block(x) {
    const a = aufnahme;
    if (!a || a.fertig) return;
    a.bloecke.push(x);
    a.proben += x.length;
    const t = a.proben / ctx.sampleRate;
    const dauer = x.length / ctx.sampleRate;
    const pegel = effektiv(x);
    balken.style.width = Math.min(100, (pegel / 0.15) * 100) + "%";

    // Die ersten 0,35 s: Grundrauschen messen (und das Antippen ueberhoeren)
    if (t <= 0.35) { a.rauschen.push(pegel); return; }
    if (a.rauschen.length) {
      const s = a.rauschen.slice().sort((p, q) => p - q);
      a.grenze = Math.max(0.012, s[Math.floor(s.length / 2)] * 3.5);
      a.rauschen = [];
    }
    a.spitze = Math.max(a.spitze, pegel);
    if (pegel > a.grenze) {
      a.laut++;
      a.letzteSprache = t;
      if (a.sprachStart === null && a.laut >= 3) a.sprachStart = t - a.laut * dauer;
    } else if (a.sprachStart === null) {
      a.laut = 0;
    }

    const e = einstellungen;
    if (e.feste_sekunden > 0) {
      if (t >= e.feste_sekunden) beenden("zeit");
    } else if (a.sprachStart !== null && t - a.letzteSprache >= stilleSekunden()) {
      beenden("stille");
    } else if (a.sprachStart === null && t >= e.warten_sekunden) {
      beenden("nichts");
    } else if (t >= e.max_sekunden) {
      beenden("max");
    }
  }

  function zusammenfuegen(a) {
    const rate = ctx.sampleRate;
    const alle = new Float32Array(a.proben);
    let pos = 0;
    for (const b of a.bloecke) { alle.set(b, pos); pos += b.length; }
    const von = Math.max(0, Math.floor((a.sprachStart - 0.5) * rate));
    const bis = Math.min(alle.length, Math.floor((a.letzteSprache + 0.6) * rate));
    const teil = alle.subarray(von, Math.max(bis, von + 1));
    const pcm = new Int16Array(teil.length);
    for (let i = 0; i < teil.length; i++) {
      const v = Math.max(-1, Math.min(1, teil[i]));
      pcm[i] = v < 0 ? v * 32768 : v * 32767;
    }
    return { pcm, rate };
  }

  async function beenden(grund) {
    const a = aufnahme;
    if (!a || a.fertig) return;
    a.fertig = true;
    balken.style.width = "0%";
    leerlauf = setTimeout(mikrofonSchliessen, LEERLAUF_MS);
    if (a.sprachStart === null) {
      // Es war nichts zu hoeren: gar nicht erst an den PC schicken
      aufnahme = null;
      pcEnde();
      const db = a.spitze > 0 ? Math.round(20 * Math.log10(a.spitze)) : -99;
      setzen("bereit", "Ich habe nichts gehört.");
      zeigeErgebnis("", "", `Sprich gleich nach dem Tippen los und etwas näher am Tablet. ` +
                            `(Lauteste Stelle: ${db} dB)`);
      return;
    }
    setzen("sendet", "Ich verstehe …");
    const { pcm, rate } = zusammenfuegen(a);
    aufnahme = null;
    try {
      const antwort = await fetch(`/api/sprache?rate=${Math.round(rate)}`, {
        method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: pcm.buffer,
      });
      const d = await antwort.json();
      setzen("bereit", d.ok ? (d.text ? "Fertig." : "Nichts verstanden.") : "Fehler");
      if (d.ok) zeigeErgebnis(d.text, d.antwort, d.hinweis);
      else zeigeErgebnis("", "", d.fehler || "Das hat nicht geklappt.");
    } catch (e) {
      pcEnde();
      setzen("bereit", "Keine Verbindung zum PC.");
    }
  }

  function pcEnde() {  // der Ingenieur darf wieder reden
    fetch("/api/sprache/ende", { method: "POST", headers: { "Content-Type": "application/json" },
                                 body: "{}" }).catch(() => {});
  }

  async function starten() {
    if (!einstellungen.mikrofon) {
      setzen("bereit", "Die Spracheingabe ist am PC nicht bereit.");
      zeigeErgebnis("", "", "Im Fenster von start.bat steht, was fehlt.");
      return;
    }
    if (!window.isSecureContext || !navigator.mediaDevices) {
      setzen("bereit", "Mikrofon gesperrt: Seite ist nicht verschlüsselt.");
      zeigeErgebnis("", "", "Öffne die verschlüsselte Adresse (siehe Hinweis oben).");
      return;
    }
    leeren();
    clearTimeout(leerlauf);
    setzen("oeffnen", "Mikrofon wird geöffnet …");
    try {
      await mikrofonOeffnen();
    } catch (e) {
      mikrofonSchliessen();
      setzen("bereit", e && e.name === "NotFoundError" ? "Kein Mikrofon gefunden."
        : "Mikrofon nicht freigegeben.");
      zeigeErgebnis("", "", e && e.name === "NotFoundError"
        ? "Dieses Tablet meldet kein Mikrofon."
        : "Tippe in Chrome auf das Schloss-Symbol neben der Adresse und erlaube das Mikrofon.");
      return;
    }
    fetch("/api/sprache/start", { method: "POST", headers: { "Content-Type": "application/json" },
                                  body: "{}" }).catch(() => {});
    aufnahme = neueAufnahme();
    if (navigator.vibrate) navigator.vibrate(30);
    setzen("hoert", "Ich höre zu … Tippen = fertig");
  }

  knopf.addEventListener("click", () => {
    if (zustand === "bereit") starten();
    else if (zustand === "hoert") beenden("getippt");
  });

  /* ---------------------------------------------------------------- */
  /* Einstellungen und Hinweis auf die verschluesselte Adresse         */
  /* ---------------------------------------------------------------- */
  async function infoHolen() {
    try {
      einstellungen = await (await fetch("/api/info", { cache: "no-store" })).json();
    } catch (e) { return; }
    knopf.classList.toggle("aus", !einstellungen.mikrofon);
    const unsicher = einstellungen.mikrofon && !window.isSecureContext && einstellungen.https_port;
    banner.hidden = !unsicher;
    if (unsicher) {
      const adresse = `https://${location.hostname}:${einstellungen.https_port}/`;
      banner.innerHTML = `<b>Für das Mikrofon brauchst du die verschlüsselte Adresse:</b>
        <a href="${esc(adresse)}">${esc(adresse)}</a><br>
        <span class="leise">Beim ersten Öffnen kommt eine Warnung „Verbindung nicht privat“:
        auf <b>Erweitert</b> und dann <b>Weiter</b> tippen.
        ${einstellungen.ca ? `Ohne Warnung geht es, wenn du <a href="/ca.crt">dieses Zertifikat</a>
        einmal am Tablet installierst (siehe Anleitung).` : ""}</span>`;
    }
  }

  /* Pause bis zum Ende der Aufnahme: am Tablet einstellbar (gilt nur fuer dieses Geraet) */
  const STILLE_SCHLUESSEL = "renningenieur.stille";
  function gespeicherteStille() {
    try {
      const wert = parseFloat(localStorage.getItem(STILLE_SCHLUESSEL));
      return wert > 0 ? wert : null;
    } catch (e) { return null; }
  }
  function stilleSekunden() {
    return gespeicherteStille() ?? einstellungen.stille_sekunden;
  }
  function stilleWahlZeigen() {
    const wahl = document.getElementById("stille-wahl");
    if (!wahl) return;
    const aktuell = stilleSekunden();
    if (![...wahl.options].some((o) => parseFloat(o.value) === aktuell)) {
      const o = document.createElement("option");
      o.value = String(aktuell); o.textContent = String(aktuell).replace(".", ",");
      wahl.appendChild(o);
    }
    if (document.activeElement !== wahl) wahl.value = String(aktuell);
  }
  const stilleWahl = document.getElementById("stille-wahl");
  if (stilleWahl) {
    stilleWahl.addEventListener("change", () => {
      try { localStorage.setItem(STILLE_SCHLUESSEL, stilleWahl.value); } catch (e) { /* ohne Speicher gilt die Einstellung vom PC */ }
    });
  }

  infoHolen().then(stilleWahlZeigen);
  setInterval(() => infoHolen().then(stilleWahlZeigen), 10000);
  window.addEventListener("pagehide", mikrofonSchliessen);
})();
