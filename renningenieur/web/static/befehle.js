/* Reiter "Befehle": alle Befehle ansehen, ausprobieren und eigene bauen. */
"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  if (!$("befehle")) return;

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  let daten = null;      // Antwort von /api/befehle
  let entwurf = null;    // Befehl, der gerade gebaut wird
  let vorschauFrage = "";
  let vorschauTimer = null;
  let geladen = false;

  async function post(pfad, koerper) {
    const antwort = await fetch(pfad, { method: "POST", headers: { "Content-Type": "application/json" },
                                        body: JSON.stringify(koerper) });
    return antwort.json();
  }

  /* ------------------------------------------------------------------ */
  /* Laden und Anzeigen                                                  */
  /* ------------------------------------------------------------------ */
  async function laden() {
    try {
      daten = await (await fetch("/api/befehle", { cache: "no-store" })).json();
    } catch (e) {
      $("bf-eigene").innerHTML = `<div class="hinweis">Keine Verbindung zum PC.</div>`;
      return;
    }
    geladen = true;
    $("bf-daten-hinweis").textContent = daten.daten === "live"
      ? "Es läuft gerade ein Spiel: Antworten kommen aus den Live-Daten."
      : "Kein Spiel aktiv: Antworten kommen aus Beispieldaten (ein simuliertes Rennen). So kannst du Befehle auch am Schreibtisch bauen.";
    zeichneEigene();
    zeichneEingebaut();
    zeichneFahrerNennen();
  }

  const infoTitel = (key) => (daten.infos.find((i) => i.key === key) || { titel: key }).titel;
  const zielTitel = (z) => {
    const def = daten.ziele.find((d) => d.art === z.art) || { titel: z.art };
    if (z.art === "platz") return `${def.titel}: Platz ${z.platz}`;
    if (z.art === "name") return `${def.titel}: ${z.name}`;
    if (z.art === "top" || z.art === "um_mich") return `${def.titel} (${z.n})`;
    return def.titel;
  };

  function zeichneEigene() {
    const liste = daten.eigene;
    if (!liste.length) {
      $("bf-eigene").innerHTML = `<div class="hinweis">Noch keine eigenen Befehle. Tippe auf „+ Neuer Befehl“.</div>`;
      return;
    }
    $("bf-eigene").innerHTML = liste.map((b) => `
      <div class="bf-karte${b.aktiv ? "" : " aus"}" data-id="${esc(b.id)}">
        <div class="bf-karte-kopf">
          <h3>${esc(b.name)}</h3>
          <label class="schalter"><input type="checkbox" data-aktion="aktiv" ${b.aktiv ? "checked" : ""}> aktiv</label>
          <button class="klein" data-aktion="testen" type="button">Testen</button>
          <button class="text" data-aktion="bearbeiten" type="button">Bearbeiten</button>
          <button class="text gefahr" data-aktion="loeschen" type="button">Löschen</button>
        </div>
        <div class="bf-zeile"><span class="leise">Springt an bei:</span></div>
        <div class="bf-chips">${b.ausloeser.map((a) => `<span class="bf-chip">${esc(a)}</span>`).join("")}</div>
        <div class="bf-zeile"><span class="leise">Fahrer:</span> ${esc(zielTitel(b.ziel))}</div>
        <div class="bf-zeile"><span class="leise">Infos:</span> ${b.infos.map((k) => esc(infoTitel(k))).join(", ")}</div>
        ${b.text ? `<div class="bf-zeile"><span class="leise">Antworttext:</span> ${esc(b.text)}</div>` : ""}
        <div class="bf-ergebnis" hidden></div>
      </div>`).join("");
  }

  function zeichneEingebaut() {
    const suche = $("bf-suche").value.trim().toLowerCase();
    const treffer = daten.eingebaut.filter((b) => !suche || [b.titel, b.beschreibung, ...b.beispiele, ...b.stichwoerter]
      .join(" ").toLowerCase().includes(suche));
    $("bf-eingebaut").innerHTML = treffer.length ? treffer.map((b) => `
      <details class="bf-karte">
        <summary>${esc(b.titel)}${b.fahrer ? `<span class="bf-tag">kann einen Fahrer meinen</span>` : ""}</summary>
        <div class="bf-zeile">${esc(b.beschreibung)}</div>
        <div class="bf-zeile"><span class="leise">Beispiele zum Ausprobieren:</span></div>
        <div class="bf-chips">${b.beispiele.map((s) =>
          `<button class="bf-beispiel klein" data-beispiel="${esc(s)}" type="button">${esc(s)}</button>`).join("")}</div>
        <div class="bf-zeile"><span class="leise">Springt an bei:</span></div>
        <div class="bf-chips">${b.stichwoerter.map((w) => `<span class="bf-chip">${esc(w)}</span>`).join("")}</div>
      </details>`).join("") : `<div class="hinweis">Nichts gefunden.</div>`;
  }

  function zeichneFahrerNennen() {
    $("bf-fahrer-nennen").innerHTML = `<thead><tr><th>Du sagst zum Beispiel</th><th>Gemeint ist</th></tr></thead><tbody>`
      + daten.fahrer_nennen.map((f) => `<tr><td>${esc(f.wie)}</td><td>${esc(f.wen)}</td></tr>`).join("") + "</tbody>";
  }

  /* ------------------------------------------------------------------ */
  /* Ausprobieren                                                        */
  /* ------------------------------------------------------------------ */
  function ergebnisHtml(r) {
    const quelle = r.daten === "live" ? "Live-Daten" : "Beispieldaten";
    return `<div class="von">${esc(r.von)} · ${quelle}</div><div class="antwort">${esc(r.antwort)}</div>`;
  }

  async function testen(text, ziel, sprechen) {
    if (!text.trim()) return;
    const r = await post("/api/befehle/pruefen", { text, sprechen: !!sprechen });
    ziel.innerHTML = ergebnisHtml(r);
    ziel.hidden = false;
  }

  $("bf-test-form").addEventListener("submit", (e) => {
    e.preventDefault();
    testen($("bf-test-text").value, $("bf-test-ergebnis"), $("bf-test-sprechen").checked);
  });
  $("bf-suche").addEventListener("input", () => daten && zeichneEingebaut());

  $("befehle").addEventListener("click", async (e) => {
    const beispiel = e.target.closest("[data-beispiel]");
    if (beispiel) {
      $("bf-test-text").value = beispiel.dataset.beispiel;
      window.scrollTo({ top: 0, behavior: "smooth" });
      testen(beispiel.dataset.beispiel, $("bf-test-ergebnis"), false);
      return;
    }
    const karte = e.target.closest(".bf-karte[data-id]");
    const aktion = e.target.closest("[data-aktion]");
    if (!karte || !aktion) return;
    const befehl = daten.eigene.find((b) => b.id === karte.dataset.id);
    if (!befehl) return;
    if (aktion.dataset.aktion === "testen") {
      testen(befehl.ausloeser[0], karte.querySelector(".bf-ergebnis"), false);
    } else if (aktion.dataset.aktion === "bearbeiten") {
      editorOeffnen(befehl);
    } else if (aktion.dataset.aktion === "loeschen") {
      if (confirm(`Den Befehl „${befehl.name}“ wirklich löschen?`)) {
        const r = await post("/api/befehle/loeschen", { id: befehl.id });
        daten.eigene = r.eigene;
        zeichneEigene();
      }
    }
  });
  $("befehle").addEventListener("change", async (e) => {
    const aktion = e.target.closest("[data-aktion=aktiv]");
    if (!aktion) return;
    const karte = aktion.closest(".bf-karte[data-id]");
    const befehl = daten.eigene.find((b) => b.id === karte.dataset.id);
    const r = await post("/api/befehle/speichern", { befehl: { ...befehl, aktiv: aktion.checked } });
    daten.eigene = r.eigene;
    zeichneEigene();
  });

  /* ------------------------------------------------------------------ */
  /* Baukasten                                                           */
  /* ------------------------------------------------------------------ */
  function leererEntwurf() {
    return { name: "", aktiv: true, ausloeser: [], ziel: { art: "aus_frage" }, infos: [], text: "" };
  }

  function editorOeffnen(befehl) {
    entwurf = befehl ? JSON.parse(JSON.stringify(befehl)) : leererEntwurf();
    vorschauFrage = entwurf.ausloeser[0] || "";
    editorZeichnen();
    $("bf-editor").hidden = false;
    $("bf-editor").scrollIntoView({ behavior: "smooth", block: "start" });
    vorschauPlanen();
  }

  function editorSchliessen() {
    $("bf-editor").hidden = true;
    entwurf = null;
  }

  function editorZeichnen() {
    const neu = !entwurf.id;
    const hatTextEigen = entwurf._eigen ?? !!entwurf.text;
    const gruppen = [...new Set(daten.infos.map((i) => i.gruppe))];
    const keinFahrer = entwurf.ziel.art === "keiner";
    const infoHtml = gruppen.map((g) => `
      <div class="bf-gruppe"><div class="gruppenname">${esc(g)}${daten.infos.find((i) => i.gruppe === g && !i.fahrer)
        ? " (ohne Fahrer)" : ""}</div>
        <div class="bf-infos">${daten.infos.filter((i) => i.gruppe === g).map((i) => {
          const an = entwurf.infos.includes(i.key);
          const aus = keinFahrer && i.fahrer;
          return `<label class="bf-info${an ? " gewaehlt" : ""}${aus ? " deaktiviert" : ""}">
            <input type="checkbox" data-info="${esc(i.key)}" ${an ? "checked" : ""} ${aus ? "disabled" : ""}>
            <span><span class="t">${esc(i.titel)}</span><br><span class="b">${esc(i.beschreibung)}</span></span></label>`;
        }).join("")}</div></div>`).join("");

    const zielHtml = daten.ziele.map((z) => {
      const an = entwurf.ziel.art === z.art;
      let param = "";
      if (z.parameter === "platz") {
        param = `<input type="number" min="1" max="24" data-param="platz" value="${esc(entwurf.ziel.platz ?? 3)}" aria-label="Platz">`;
      } else if (z.parameter === "name") {
        param = `<input type="text" list="bf-fahrerliste" data-param="name" value="${esc(entwurf.ziel.name ?? "")}"
                  placeholder="Name, z. B. Verstappen" aria-label="Fahrername">`;
      } else if (z.parameter === "n") {
        param = `<input type="number" min="1" max="${z.art === "top" ? 10 : 5}" data-param="n" value="${esc(entwurf.ziel.n ?? 3)}" aria-label="Anzahl">`;
      }
      return `<div class="bf-ziel${an ? " gewaehlt" : ""}">
        <label class="bf-ziel-kopf"><input type="radio" name="bf-ziel" value="${esc(z.art)}" ${an ? "checked" : ""}>
          <b>${esc(z.titel)}</b></label>
        ${z.beschreibung ? `<div class="beschr">${esc(z.beschreibung)}</div>` : ""}
        ${param && an ? `<div class="param">${param}</div>` : ""}</div>`;
    }).join("");

    const platzhalter = ["name", ...entwurf.infos].map((k) =>
      `<button type="button" class="klein" data-platzhalter="${esc(k)}">{${esc(k)}}</button>`).join(" ");

    $("bf-editor").innerHTML = `
      <div class="block-kopf"><h2>${neu ? "Neuer Befehl" : "Befehl bearbeiten"}</h2></div>

      <div class="bf-feld"><label class="titel" for="bf-name">1. Wie soll er heißen?</label>
        <input id="bf-name" type="text" maxlength="40" value="${esc(entwurf.name)}" placeholder="z. B. Reifen der Nachbarn"></div>

      <div class="bf-feld"><span class="titel">2. Bei welchen Wörtern soll er antworten?</span>
        <p class="hinweis-klein">Alle Wörter eines Auslösers müssen in deiner Frage vorkommen, die Reihenfolge ist egal.
          Schreib am besten den Wortanfang: „reifen“ passt auch auf „Reifenverschleiß“. Du kannst mehrere Auslöser anlegen.</p>
        <div class="bf-eingabezeile"><input id="bf-ausloeser-neu" type="text" maxlength="60" placeholder="z. B. reifen nachbar"
          autocomplete="off"><button type="button" id="bf-ausloeser-add">Hinzufügen</button></div>
        <div class="bf-chips">${entwurf.ausloeser.map((a, i) => `<span class="bf-chip">${esc(a)}
          <button type="button" data-ausloeser-weg="${i}" aria-label="Entfernen">×</button></span>`).join("")}</div></div>

      <div class="bf-feld"><span class="titel">3. Von welchem Fahrer kommen die Infos?</span>
        <div class="bf-ziele">${zielHtml}</div>
        <datalist id="bf-fahrerliste">${daten.fahrer.map((f) => `<option value="${esc(f.name)}">`).join("")}</datalist></div>

      <div class="bf-feld"><span class="titel">4. Was soll er sagen?</span>
        <p class="hinweis-klein">Wähle eine oder mehrere Infos. Sie werden nacheinander vorgelesen.
          ${keinFahrer ? "Ohne Fahrer sind nur die allgemeinen Infos möglich." : ""}</p>${infoHtml}</div>

      <div class="bf-feld"><span class="titel">5. Wie soll die Antwort klingen?</span>
        <div><label class="schalter"><input type="radio" name="bf-textart" value="auto" ${hatTextEigen ? "" : "checked"}>
          Automatisch zusammenstellen („Verstappen: Platz 1, Reifen Soft, …“)</label></div>
        <div><label class="schalter"><input type="radio" name="bf-textart" value="eigen" ${hatTextEigen ? "checked" : ""}>
          Eigener Text</label></div>
        <div id="bf-textbereich" ${hatTextEigen ? "" : "hidden"}>
          <p class="hinweis-klein">Mit den Platzhaltern setzt du die Werte ein, die du oben ausgewählt hast. Beispiel:
            <i>{name} liegt auf {position} und fährt {reifen}.</i></p>
          <textarea id="bf-text" maxlength="300">${esc(entwurf.text)}</textarea>
          <div class="bf-chips">${platzhalter}</div></div></div>

      <div class="bf-feld"><span class="titel">So antwortet er (Vorschau)</span>
        <div class="bf-eingabezeile"><input id="bf-vorschau-frage" type="text" value="${esc(vorschauFrage)}"
          placeholder="Beispielfrage, z. B. Steckbrief von Verstappen"></div>
        <div id="bf-vorschau" class="bf-vorschau" style="margin-top:8px"></div></div>

      <div id="bf-editor-fehler" class="bf-fehler" hidden></div>
      <div class="bf-knoepfe"><button type="button" id="bf-speichern" class="primaer">Speichern</button>
        <button type="button" id="bf-abbrechen">Abbrechen</button></div>`;
  }

  function entwurfLesen() {
    const e = entwurf;
    e.name = ($("bf-name") || {}).value ?? e.name;
    const art = (document.querySelector("input[name=bf-ziel]:checked") || {}).value || e.ziel.art;
    const ziel = { art };
    document.querySelectorAll("[data-param]").forEach((p) => {
      ziel[p.dataset.param] = p.dataset.param === "name" ? p.value : Number(p.value);
    });
    e.ziel = ziel;
    e.infos = [...document.querySelectorAll("[data-info]:checked")].map((c) => c.dataset.info);
    const gewaehlt = (document.querySelector("input[name=bf-textart]:checked") || {}).value;
    const eigen = gewaehlt ? gewaehlt === "eigen" : !!e._eigen;
    e._eigen = eigen;
    e.text = eigen && $("bf-text") ? $("bf-text").value : "";
    return e;
  }

  function vorschauPlanen() {
    clearTimeout(vorschauTimer);
    vorschauTimer = setTimeout(vorschauAktualisieren, 350);
  }

  async function vorschauAktualisieren() {
    if (!entwurf || !$("bf-vorschau")) return;
    const feld = $("bf-vorschau");
    const frage = ($("bf-vorschau-frage") || {}).value || "";
    vorschauFrage = frage;
    const r = await post("/api/befehle/vorschau", { befehl: entwurfLesen(), frage });
    if (!entwurf) return;
    if (r.ok) {
      feld.className = "bf-vorschau";
      feld.innerHTML = `<div class="von leise">Auf die Frage „${esc(r.frage)}“ · ${r.daten === "live" ? "Live-Daten" : "Beispieldaten"}</div>
        <div class="antwort">${esc(r.antwort)}</div>`;
    } else {
      feld.className = "bf-vorschau fehler";
      feld.innerHTML = `Noch nicht fertig: ${r.fehler.map(esc).join(" ")}`;
    }
  }

  async function speichern() {
    const r = await post("/api/befehle/speichern", { befehl: entwurfLesen() });
    const box = $("bf-editor-fehler");
    if (!r.ok) {
      box.hidden = false;
      box.innerHTML = `<b>Das fehlt noch:</b><ul>${r.fehler.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>`;
      return;
    }
    daten.eigene = r.eigene;
    editorSchliessen();
    zeichneEigene();
    const karte = document.querySelector(`.bf-karte[data-id="${r.befehl.id}"]`);
    if (karte) { karte.scrollIntoView({ behavior: "smooth", block: "center" }); testen(r.befehl.ausloeser[0], karte.querySelector(".bf-ergebnis"), false); }
  }

  function ausloeserHinzufuegen() {
    const feld = $("bf-ausloeser-neu");
    const wert = feld.value.trim();
    if (!wert) return;
    entwurfLesen();
    if (!entwurf.ausloeser.includes(wert)) entwurf.ausloeser.push(wert);
    if (!vorschauFrage) vorschauFrage = wert;
    editorZeichnen();
    $("bf-ausloeser-neu").focus();
    vorschauPlanen();
  }

  const editor = $("bf-editor");
  editor.addEventListener("click", (e) => {
    if (e.target.id === "bf-speichern") speichern();
    else if (e.target.id === "bf-abbrechen") editorSchliessen();
    else if (e.target.id === "bf-ausloeser-add") ausloeserHinzufuegen();
    else if (e.target.dataset.ausloeserWeg !== undefined) {
      entwurfLesen();
      entwurf.ausloeser.splice(Number(e.target.dataset.ausloeserWeg), 1);
      editorZeichnen();
      vorschauPlanen();
    } else if (e.target.dataset.platzhalter) {
      const ta = $("bf-text");
      const eintrag = `{${e.target.dataset.platzhalter}}`;
      const von = ta.selectionStart ?? ta.value.length;
      ta.value = ta.value.slice(0, von) + eintrag + ta.value.slice(ta.selectionEnd ?? von);
      ta.focus();
      ta.selectionStart = ta.selectionEnd = von + eintrag.length;
      vorschauPlanen();
    }
  });
  editor.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.id === "bf-ausloeser-neu") { e.preventDefault(); ausloeserHinzufuegen(); }
  });
  editor.addEventListener("change", (e) => {
    const t = e.target;
    if (t.name === "bf-ziel" || t.name === "bf-textart" || t.dataset.info !== undefined) {
      entwurfLesen();
      editorZeichnen();
      if (t.name === "bf-textart" && t.value === "eigen") $("bf-text").focus();
    }
    vorschauPlanen();
  });
  editor.addEventListener("input", (e) => {
    if (e.target.id === "bf-vorschau-frage" || e.target.id === "bf-text" || e.target.dataset.param) vorschauPlanen();
  });

  $("bf-neu").addEventListener("click", () => editorOeffnen(null));

  /* ------------------------------------------------------------------ */
  document.querySelector(".reiter").addEventListener("click", (e) => {
    if (e.target.closest("[data-reiter=befehle]")) laden();
  });
  setInterval(() => { // Fahrerliste und Datenquelle aktuell halten, solange der Reiter offen ist
    if ($("befehle").classList.contains("aktiv") && geladen && $("bf-editor").hidden) laden();
  }, 20000);
})();
