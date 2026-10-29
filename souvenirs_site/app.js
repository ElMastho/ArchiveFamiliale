/* « Nos souvenirs » : consultation de l'archive, sans Internet ni installation.
   Les données (liste des fichiers de ce disque) sont dans donnees.js, écrit par Archive Familiale. */
"use strict";

const D = window.SOUVENIRS;
const MONTHS = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
  "septembre", "octobre", "novembre", "décembre"];
const SHOWABLE = new Set(["jpg", "jpeg", "jpe", "jfif", "png", "gif", "bmp", "webp", "avif"]);
const PLAYABLE = new Set(["mp4", "m4v", "mov", "webm", "ogv"]);
const AUDIBLE = new Set(["mp3", "m4a", "aac", "wav", "ogg", "oga", "opus", "flac"]);
const DOCS = ["Textes", "Tableurs", "Présentations", "PDF"];
const ICONS = { Textes: "📝", Tableurs: "📊", "Présentations": "📽️", PDF: "📕", audio: "🎵", mail: "✉️",
  other: "📄", photo: "🖼️", video: "🎬" };
const SLIDE_MS = 5000;
const PAGE = 300;   // lignes affichées d'un coup dans les longues listes

const $ = (sel) => document.querySelector(sel);
const main = $("#main");

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fmtInt(n) { return n.toLocaleString("fr-FR"); }
function fmtSize(b) {
  const u = ["o", "Ko", "Mo", "Go", "To"];
  let i = 0;
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
  return (i ? b.toLocaleString("fr-FR", { maximumFractionDigits: 1 }) : b) + " " + u[i];
}
function plural(n, one, many) { return fmtInt(n) + " " + (n > 1 ? many : one); }

if (!D) {
  main.innerHTML = '<p class="empty">Les données de l\'archive sont introuvables sur ce disque. Ouvrez Archive ' +
    'Familiale et cliquez sur « Mettre à jour Nos souvenirs ».</p>';
  throw new Error("donnees.js manquant");
}

/* Fichiers : [chemin, famille, année, mois, album, taille, vignette] */
const FILES = D.files.map((r, i) => {
  const name = r[0].split("/").pop();
  const dot = name.lastIndexOf(".");
  return { i, path: r[0], fam: r[1], y: r[2], m: r[3], album: r[4], size: r[5], thumb: r[6], name,
    ext: dot > 0 ? name.slice(dot + 1).toLowerCase() : "", low: name.toLowerCase() };
});
const MEDIA = FILES.filter((f) => f.fam === "photo" || f.fam === "video");
const byDate = (a, b) => (a.y - b.y) || (a.m - b.m) || a.album.localeCompare(b.album, "fr") || a.name.localeCompare(b.name, "fr");
MEDIA.sort(byDate);

function url(path) { return "../../" + path.split("/").map(encodeURIComponent).join("/"); }
function thumbUrl(f) { return f.thumb ? `v/${f.thumb.slice(0, 2)}/${f.thumb}.jpg` : null; }
function when(f) {
  if (!f.y) return "date inconnue";
  return (f.m ? MONTHS[f.m] + " " : "") + f.y;
}
function period(list) {
  const ys = list.map((f) => f.y).filter(Boolean);
  if (!ys.length) return "";
  const a = Math.min(...ys), b = Math.max(...ys);
  return a === b ? `en ${a}` : `de ${a} à ${b}`;
}
function groupBy(list, key) {
  const m = new Map();
  for (const f of list) {
    const k = key(f);
    if (!m.has(k)) m.set(k, []);
    m.get(k).push(f);
  }
  return m;
}

/* ---------- Navigation ---------- */
const SECTIONS = [
  ["#/", "Accueil"],
  ["#/photos", "Photos et vidéos"],
  ["#/documents", "Documents"],
  ["#/musique", "Musique"],
  ["#/autres", "Autres fichiers"],
];
document.title = D.title;
$("#title").textContent = D.title;

function renderNav(hash) {
  $("#nav").innerHTML = SECTIONS.map(([h, label]) => {
    const on = h === "#/" ? hash === "#/" : hash.startsWith(h);
    return `<a href="${h}" class="${on ? "on" : ""}">${label}</a>`;
  }).join("");
}

function route() {
  const hash = location.hash || "#/";
  const [, section, arg] = decodeURIComponent(hash).split("/");
  renderNav(hash);
  window.scrollTo(0, 0);
  if (section === "photos" && arg) return yearView(arg === "inconnue" ? 0 : Number(arg));
  if (section === "photos") return yearsView();
  if (section === "documents") return docsView(arg || "");
  if (section === "musique") return musicView();
  if (section === "autres") return othersView();
  if (section === "recherche") return searchView(arg || "");
  return homeView();
}
window.addEventListener("hashchange", route);
$("#search-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("#search").value.trim();
  location.hash = "#/recherche/" + encodeURIComponent(q);
});

/* ---------- Accueil ---------- */
function cover(list, icon) {
  const imgs = list.filter((f) => f.thumb);
  if (!imgs.length) return `<div class="cover icon">${icon}</div>`;
  const pick = [];
  for (let k = 0; k < 4; k++) pick.push(imgs[Math.floor((k + 0.5) * imgs.length / 4)]);
  return `<div class="cover">${pick.map((f) => `<img src="${thumbUrl(f)}" alt="" loading="lazy">`).join("")}</div>`;
}

function homeView() {
  const photos = MEDIA.filter((f) => f.fam === "photo"), videos = MEDIA.filter((f) => f.fam === "video");
  const docs = FILES.filter((f) => DOCS.includes(f.fam));
  const music = FILES.filter((f) => f.fam === "audio");
  const others = FILES.filter((f) => f.fam === "mail" || f.fam === "other");
  const byYear = groupBy(MEDIA.filter((f) => f.y), (f) => f.y);
  let best = null;
  for (const [y, l] of byYear) if (!best || l.length > best[1]) best = [y, l.length];
  const facts = [];
  if (MEDIA.length) facts.push(`<b>${plural(photos.length, "photo", "photos")}</b> et <b>${plural(videos.length, "vidéo", "vidéos")}</b>, ${period(MEDIA)}.`);
  if (best) facts.push(`L'année la plus riche en souvenirs : <b>${best[0]}</b>, avec ${plural(best[1], "photo ou vidéo", "photos et vidéos")}.`);
  if (docs.length) facts.push(`<b>${plural(docs.length, "document", "documents")}</b> (textes, tableurs, présentations, PDF), ${period(docs)}.`);
  const note = D.others && D.others.length ? `<p class="note">Cette archive est répartie sur plusieurs disques. Ce disque,
    « ${esc(D.disk)} », en contient une partie. Les autres fichiers sont sur : ${D.others.map((o) => `« ${esc(o.name)} »
    (${plural(o.files, "fichier", "fichiers")})`).join(", ")}.</p>` : "";
  main.innerHTML = `
    <h1>Bienvenue dans ${esc(D.title.toLowerCase().startsWith("nos ") ? D.title.toLowerCase() : D.title)}</h1>
    <p class="lead">Toutes les photos, vidéos et documents de la famille, réunis et rangés. Cliquez sur une rubrique
      pour commencer. Rien ne peut être effacé ni modifié depuis cette page.</p>
    ${note}
    <ul class="facts">${facts.map((f) => `<li>${f}</li>`).join("")}</ul>
    <div class="tiles">
      ${tile("#/photos", "Photos et vidéos", plural(MEDIA.length, "souvenir", "souvenirs"), cover(MEDIA, "🖼️"))}
      ${tile("#/documents", "Documents", plural(docs.length, "document", "documents"), `<div class="cover icon">📂</div>`)}
      ${tile("#/musique", "Musique", plural(music.length, "morceau", "morceaux"), `<div class="cover icon">🎵</div>`)}
      ${tile("#/autres", "Autres fichiers", plural(others.length, "fichier", "fichiers"), `<div class="cover icon">🗂️</div>`)}
    </div>`;
}
function tile(href, name, count, coverHtml) {
  if (count.startsWith("0 ")) return "";   // rubrique vide : pas de tuile
  return `<a class="tile" href="${href}">${coverHtml}<div class="body"><div class="name">${name}</div>
    <div class="count">${count}</div></div></a>`;
}

/* ---------- Photos et vidéos ---------- */
function yearsView() {
  const years = [...groupBy(MEDIA, (f) => f.y)].sort((a, b) => (b[0] || -1) - (a[0] || -1));
  if (!years.length) { main.innerHTML = '<p class="empty">Aucune photo ni vidéo sur ce disque.</p>'; return; }
  main.innerHTML = `
    <h1>Photos et vidéos</h1>
    <p class="lead">${plural(MEDIA.length, "souvenir", "souvenirs")}, ${period(MEDIA)}. Choisissez une année.</p>
    <div class="years">${years.map(([y, l]) => {
      const withThumb = l.filter((f) => f.thumb);
      const c = withThumb.length ? withThumb[Math.floor(withThumb.length / 2)] : null;
      return `<a class="year ${c ? "" : "noimg"}" href="#/photos/${y || "inconnue"}">
        ${c ? `<img src="${thumbUrl(c)}" alt="" loading="lazy">` : ""}
        <span class="label"><b>${y || "Date inconnue"}</b>${plural(l.length, "souvenir", "souvenirs")}</span></a>`;
    }).join("")}</div>`;
}

function yearView(y) {
  const list = MEDIA.filter((f) => f.y === y);
  const years = [...new Set(MEDIA.map((f) => f.y))].sort((a, b) => a - b);
  const k = years.indexOf(y);
  const prev = k > 0 ? years[k - 1] : null, next = k >= 0 && k < years.length - 1 ? years[k + 1] : null;
  const yl = (v) => (v ? v : "inconnue");
  const groups = groupBy(list, (f) => f.album || (f.m ? "\u0000" + String(f.m).padStart(2, "0") : "\u0000"));
  const keys = [...groups.keys()].sort((a, b) => {
    const fa = groups.get(a)[0], fb = groups.get(b)[0];
    return (fa.m - fb.m) || a.localeCompare(b, "fr");
  });
  main.innerHTML = `
    <div class="bar">
      <a class="btn" href="#/photos">‹ Toutes les années</a>
      <span class="spacer"></span>
      ${prev !== null ? `<a class="btn" href="#/photos/${yl(prev)}">‹ ${prev || "Date inconnue"}</a>` : ""}
      ${next !== null ? `<a class="btn" href="#/photos/${yl(next)}">${next || "Date inconnue"} ›</a>` : ""}
    </div>
    <h1>${y || "Date inconnue"}</h1>
    <div class="bar"><p class="lead" style="margin:0">${plural(list.length, "souvenir", "souvenirs")}</p>
      <span class="spacer"></span><button class="btn primary" id="slideshow">▶ Diaporama de ${y || "ces photos"}</button></div>
    ${keys.map((key) => {
      const g = groups.get(key);
      const title = key.startsWith("\u0000") ? (g[0].m ? cap(MONTHS[g[0].m]) : "Autres") : key;
      const sub = key.startsWith("\u0000") ? "" : ` <span class="muted">· ${when(g[0])}</span>`;
      return `<h3>${esc(title)}${sub} <span class="muted">· ${fmtInt(g.length)}</span></h3>
        <div class="grid">${g.map(cell).join("")}</div>`;
    }).join("")}`;
  const order = keys.flatMap((key) => groups.get(key));
  main.querySelectorAll(".ph").forEach((el) => el.addEventListener("click", () => {
    openViewer(order, order.findIndex((f) => f.i === Number(el.dataset.i)));
  }));
  $("#slideshow").addEventListener("click", () => { openViewer(order, 0); toggleSlideshow(true); });
}
function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
function cell(f) {
  const t = thumbUrl(f);
  const video = f.fam === "video";
  let inner;
  if (t) inner = `<img src="${t}" alt="${esc(f.name)}" loading="lazy">`;
  else if (!video && SHOWABLE.has(f.ext)) inner = `<img src="${url(f.path)}" alt="${esc(f.name)}" loading="lazy">`;
  else inner = `<span class="ph-icon">${video ? "▶" : "🖼️"}<small>${esc(f.name)}</small></span>`;
  return `<button class="ph ${video ? "video" : ""}" data-i="${f.i}" title="${esc(f.name)} · ${when(f)}">${inner}
    ${video && t ? '<span class="badge">▶ vidéo</span>' : ""}</button>`;
}

/* ---------- Visionneuse plein écran ---------- */
let V = { list: [], k: 0, timer: null };
function openViewer(list, k) {
  V.list = list; V.k = Math.max(0, k);
  $("#viewer").hidden = false;
  document.body.style.overflow = "hidden";
  showCurrent();
}
function closeViewer() {
  toggleSlideshow(false);
  $("#viewer").hidden = true;
  $("#viewer-stage").innerHTML = "";
  document.body.style.overflow = "";
}
function showCurrent() {
  const f = V.list[V.k];
  const stage = $("#viewer-stage");
  const src = url(f.path);
  if (f.fam === "photo" && SHOWABLE.has(f.ext)) {
    stage.innerHTML = `<img src="${src}" alt="${esc(f.name)}">`;
  } else if (f.fam === "video" && PLAYABLE.has(f.ext)) {
    stage.innerHTML = `<video src="${src}" controls autoplay></video>`;
    const v = stage.querySelector("video");
    v.addEventListener("ended", () => { if (V.timer) step(1); });
    v.addEventListener("error", () => cantShow(f));
  } else {
    cantShow(f);
  }
  const album = f.album ? `${esc(f.album)} · ` : "";
  $("#viewer-info").innerHTML = `<b>${esc(f.name)}</b><span>${album}${when(f)} · ${V.k + 1} sur ${fmtInt(V.list.length)}</span>`;
  $("#v-open").href = src;
  // Précharge la suivante : le diaporama reste fluide depuis un disque USB
  const n = V.list[V.k + 1];
  if (n && n.fam === "photo" && SHOWABLE.has(n.ext)) new Image().src = url(n.path);
}
function cantShow(f) {
  $("#viewer-stage").innerHTML = `<div class="cant"><div class="big">${f.fam === "video" ? "🎬" : "🖼️"}</div>
    <p>Ce fichier (${esc(f.ext.toUpperCase())}) ne peut pas s'afficher dans le navigateur.</p>
    <p><a class="pill" href="${url(f.path)}" target="_blank" rel="noopener">Ouvrir le fichier</a></p></div>`;
}
function step(d) {
  if (!V.list.length) return;
  V.k = (V.k + d + V.list.length) % V.list.length;
  showCurrent();
}
function toggleSlideshow(on) {
  if (on === undefined) on = !V.timer;
  clearInterval(V.timer);
  V.timer = null;
  if (on) {
    V.timer = setInterval(() => {
      const v = $("#viewer-stage video");
      if (v && !v.ended) return;   // on laisse la vidéo se terminer
      step(1);
    }, SLIDE_MS);
  }
  $("#v-play").textContent = on ? "⏸ Pause" : "▶ Diaporama";
}
$("#v-close").addEventListener("click", closeViewer);
$("#v-prev").addEventListener("click", () => step(-1));
$("#v-next").addEventListener("click", () => step(1));
$("#v-play").addEventListener("click", () => toggleSlideshow());
document.addEventListener("keydown", (e) => {
  if ($("#viewer").hidden) return;
  if (e.key === "Escape") closeViewer();
  else if (e.key === "ArrowRight") step(1);
  else if (e.key === "ArrowLeft") step(-1);
  else if (e.key === " ") { e.preventDefault(); toggleSlideshow(); }
});

/* ---------- Listes : documents, musique, autres ---------- */
function rows(list, onClick) {
  return list.map((f) => `<a class="row" ${onClick ? `data-i="${f.i}"` : `href="${url(f.path)}" target="_blank" rel="noopener"`}>
    <span class="ic">${ICONS[f.fam] || "📄"}</span>
    <span><span class="nm">${esc(f.name)}</span><br><span class="sub">${esc(f.path.split("/").slice(0, -1).join(" › "))}</span></span>
    <span class="sz">${when(f)} · ${fmtSize(f.size)}</span></a>`).join("");
}
function pagedList(container, list, onClick) {
  let shown = 0;
  const box = document.createElement("div");
  box.className = "list";
  const more = document.createElement("div");
  more.className = "more";
  container.append(box, more);
  const page = () => {
    box.insertAdjacentHTML("beforeend", rows(list.slice(shown, shown + PAGE), onClick));
    shown = Math.min(shown + PAGE, list.length);
    more.innerHTML = shown < list.length ? `<button class="btn">Afficher la suite (${fmtInt(list.length - shown)} de plus)</button>` : "";
    const b = more.querySelector("button");
    if (b) b.addEventListener("click", page);
  };
  page();
  if (onClick) box.addEventListener("click", (e) => {
    const r = e.target.closest(".row");
    if (r) onClick(FILES[Number(r.dataset.i)]);
  });
}
function byYearSections(list, onClick) {
  const years = [...groupBy(list, (f) => f.y)].sort((a, b) => (b[0] || -1) - (a[0] || -1));
  for (const [y, l] of years) {
    const h = document.createElement("h3");
    h.innerHTML = `${y || "Date inconnue"} <span class="muted">· ${fmtInt(l.length)}</span>`;
    main.append(h);
    l.sort((a, b) => a.name.localeCompare(b.name, "fr"));
    pagedList(main, l, onClick);
  }
}

function docsView(kind) {
  const all = FILES.filter((f) => DOCS.includes(f.fam));
  const list = kind ? all.filter((f) => f.fam === kind) : all;
  const counts = DOCS.map((k) => [k, all.filter((f) => f.fam === k).length]).filter(([, n]) => n);
  main.innerHTML = `
    <h1>Documents</h1>
    <p class="lead">${plural(all.length, "document", "documents")}, ${period(all)}. Cliquez sur un document pour
      l'ouvrir (les PDF s'ouvrent ici ; Word, Excel et PowerPoint avec le programme de l'ordinateur).</p>
    <div class="tabs"><a href="#/documents" class="${kind ? "" : "on"}">Tous</a>
      ${counts.map(([k, n]) => `<a href="#/documents/${encodeURIComponent(k)}" class="${k === kind ? "on" : ""}">${ICONS[k]} ${esc(cap(D.families[k] || k))} (${fmtInt(n)})</a>`).join("")}</div>`;
  if (!list.length) { main.insertAdjacentHTML("beforeend", '<p class="empty">Aucun document de ce type.</p>'); return; }
  byYearSections(list);
}

function playAudio(f) {
  const a = $("#audio");
  a.src = url(f.path);
  a.play().catch(() => {});
  $("#player-name").textContent = f.name;
  $("#player").hidden = false;
}
$("#player-close").addEventListener("click", () => { $("#audio").pause(); $("#player").hidden = true; });

function musicView() {
  const list = FILES.filter((f) => f.fam === "audio");
  main.innerHTML = `<h1>Musique</h1><p class="lead">${plural(list.length, "morceau", "morceaux")}. Cliquez sur un
    morceau pour l'écouter.</p>`;
  if (!list.length) { main.insertAdjacentHTML("beforeend", '<p class="empty">Aucune musique sur ce disque.</p>'); return; }
  const albums = [...groupBy(list, (f) => f.album || "Sans album")].sort((a, b) => a[0].localeCompare(b[0], "fr"));
  for (const [name, l] of albums) {
    const h = document.createElement("h3");
    h.innerHTML = `${esc(name)} <span class="muted">· ${fmtInt(l.length)}</span>`;
    main.append(h);
    l.sort((a, b) => a.name.localeCompare(b.name, "fr"));
    pagedList(main, l, (f) => (AUDIBLE.has(f.ext) ? playAudio(f) : window.open(url(f.path), "_blank")));
  }
}

function othersView() {
  const list = FILES.filter((f) => f.fam === "mail" || f.fam === "other");
  main.innerHTML = `<h1>Autres fichiers</h1><p class="lead">${plural(list.length, "fichier", "fichiers")} :
    e-mails, archives, fichiers de programmes… Cliquez pour ouvrir.</p>`;
  if (!list.length) { main.insertAdjacentHTML("beforeend", '<p class="empty">Aucun autre fichier.</p>'); return; }
  byYearSections(list);
}

/* ---------- Recherche ---------- */
function searchView(q) {
  $("#search").value = q;
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  const hits = words.length ? FILES.filter((f) => {
    const hay = f.low + " " + f.album.toLowerCase() + " " + f.y;
    return words.every((w) => hay.includes(w));
  }) : [];
  const media = hits.filter((f) => f.fam === "photo" || f.fam === "video").sort(byDate);
  const rest = hits.filter((f) => !(f.fam === "photo" || f.fam === "video"));
  main.innerHTML = `<h1>Recherche : « ${esc(q)} »</h1>
    <p class="lead">${hits.length ? plural(hits.length, "résultat", "résultats") : "Aucun résultat. Essayez un autre mot (un nom, un lieu, une année…)."}</p>`;
  if (media.length) {
    main.insertAdjacentHTML("beforeend", `<h2>Photos et vidéos</h2><div class="grid">${media.slice(0, 600).map(cell).join("")}</div>`);
    main.querySelectorAll(".ph").forEach((el) => el.addEventListener("click", () => {
      openViewer(media, media.findIndex((f) => f.i === Number(el.dataset.i)));
    }));
  }
  if (rest.length) {
    main.insertAdjacentHTML("beforeend", "<h2>Documents et autres fichiers</h2>");
    pagedList(main, rest, (f) => (f.fam === "audio" && AUDIBLE.has(f.ext) ? playAudio(f) : window.open(url(f.path), "_blank")));
  }
}

route();
