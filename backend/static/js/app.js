const API_BASE = "";

const form = document.getElementById("search-form");
const input = document.getElementById("query-input");
const submitBtn = form.querySelector(".query-line__submit");
const resultsGrid = document.getElementById("results-grid");
const resultsTitle = document.getElementById("results-title");
const intentTagsEl = document.getElementById("intent-tags");
const emptyState = document.getElementById("empty-state");
const cardTemplate = document.getElementById("card-template");
const profilePanel = document.getElementById("profile-panel");
const profileTagsEl = document.getElementById("profile-tags");

function getSessionId() {
  let id = localStorage.getItem("playfinder_session");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("playfinder_session", id);
  }
  return id;
}

const sessionId = getSessionId();

async function runSearch(query) {
  if (!query.trim()) return;

  submitBtn.disabled = true;
  submitBtn.textContent = "...";
  resultsTitle.textContent = "Searching";

  try {
    const res = await fetch(`${API_BASE}/api/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, session_id: sessionId }),
    });

    if (!res.ok) throw new Error(`Search failed (${res.status})`);

    const data = await res.json();
    renderResults(data);
  } catch (err) {
    resultsTitle.textContent = "Something went wrong";
    console.error(err);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "search";
  }
}

function renderResults(data) {
  resultsGrid.innerHTML = "";
  intentTagsEl.innerHTML = "";

  const { results, detected_intent, query } = data;

  resultsTitle.textContent = results.length
    ? `${results.length} match${results.length === 1 ? "" : "es"} for "${query}"`
    : `No matches for "${query}"`;

  const detectedGenres = detected_intent?.genres || [];
  detectedGenres.forEach((g) => {
    const tag = document.createElement("span");
    tag.className = "intent-tag";
    tag.textContent = g;
    intentTagsEl.appendChild(tag);
  });

  emptyState.classList.toggle("hidden", results.length > 0);

  results.forEach((game) => resultsGrid.appendChild(buildCard(game, query)));
}

function buildCard(game, query) {
  const node = cardTemplate.content.cloneNode(true);

  node.querySelector(".card__title").textContent = game.title;
  node.querySelector(".card__rating").textContent = `★ ${game.rating}`;
  node.querySelector(".card__year").textContent = game.year;
  node.querySelector(".card__description").textContent = game.description;

  const tagsEl = node.querySelector(".card__tags");
  [...game.genres, ...game.tags.slice(0, 3)].forEach((t) => {
    const pill = document.createElement("span");
    pill.className = "card__tag";
    pill.textContent = t;
    tagsEl.appendChild(pill);
  });

  const matchPct = Math.max(0, Math.min(100, Math.round(game.match_score * 100)));
  node.querySelector(".card__match-fill").style.width = `${matchPct}%`;

  const likeBtn = node.querySelector(".card__like");
  likeBtn.classList.toggle("liked", game.liked);
  likeBtn.textContent = game.liked ? "\u2665" : "\u2661";
  likeBtn.addEventListener("click", () => toggleLike(game.id, likeBtn));

  return node;
}

async function toggleLike(gameId, btn) {
  const isLiked = btn.classList.contains("liked");
  const method = isLiked ? "DELETE" : "POST";

  btn.disabled = true;
  try {
    await fetch(`${API_BASE}/api/like`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, game_id: gameId }),
    });
    btn.classList.toggle("liked");
    btn.textContent = btn.classList.contains("liked") ? "\u2665" : "\u2661";
    refreshProfile();
  } catch (err) {
    console.error(err);
  } finally {
    btn.disabled = false;
  }
}

async function refreshProfile() {
  try {
    const res = await fetch(`${API_BASE}/api/profile/${sessionId}`);
    if (!res.ok) return;
    const profile = await res.json();

    if (!profile.liked_games.length) {
      profilePanel.classList.add("hidden");
      return;
    }

    profilePanel.classList.remove("hidden");
    profileTagsEl.innerHTML = "";
    profile.top_genres.forEach(([genre]) => {
      const tag = document.createElement("span");
      tag.className = "profile-tag";
      tag.textContent = genre;
      profileTagsEl.appendChild(tag);
    });
  } catch (err) {
    console.error(err);
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  runSearch(input.value);
});

document.getElementById("examples").addEventListener("click", (e) => {
  const chip = e.target.closest(".example-chip");
  if (!chip) return;
  input.value = chip.dataset.query;
  runSearch(chip.dataset.query);
});

// ---------------------------------------------------------------------
// View tabs
// ---------------------------------------------------------------------

const viewTabs = document.getElementById("view-tabs");
const matchmakerView = document.getElementById("matchmaker-view");
const searchView = document.getElementById("search-view");

viewTabs.addEventListener("click", (e) => {
  const tab = e.target.closest(".view-tab");
  if (!tab) return;

  viewTabs.querySelectorAll(".view-tab").forEach((t) => t.classList.remove("active"));
  tab.classList.add("active");

  const view = tab.dataset.view;
  matchmakerView.classList.toggle("hidden", view !== "matchmaker");
  searchView.classList.toggle("hidden", view !== "search");
});

// ---------------------------------------------------------------------
// AI Game Matchmaker
// ---------------------------------------------------------------------

const matchmakerForm = document.getElementById("matchmaker-form");
const matchmakerInput = document.getElementById("matchmaker-input");
const matchmakerSubmit = matchmakerForm.querySelector(".query-line__submit");
const matchmakerGrid = document.getElementById("matchmaker-grid");
const matchmakerTitle = document.getElementById("matchmaker-title");
const matchmakerIntentTags = document.getElementById("matchmaker-intent-tags");
const matchmakerEmpty = document.getElementById("matchmaker-empty");
const posterTemplate = document.getElementById("poster-card-template");

const FALLBACK_COVER =
  "data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='533'%3E%3Crect width='400' height='533' fill='%231c1f29'/%3E%3Ctext x='200' y='266' font-family='sans-serif' font-size='20' fill='%238b90a0' text-anchor='middle'%3ENo cover%3C/text%3E%3C/svg%3E";

async function runMatchmaker(query) {
  if (!query.trim()) return;

  matchmakerSubmit.disabled = true;
  matchmakerSubmit.textContent = "...";
  matchmakerTitle.textContent = "Finding your match";

  try {
    const res = await fetch(`${API_BASE}/api/matchmaker`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, session_id: sessionId }),
    });

    if (!res.ok) throw new Error(`Matchmaker failed (${res.status})`);

    const data = await res.json();
    renderMatchmakerResults(data);
  } catch (err) {
    matchmakerTitle.textContent = "Something went wrong";
    console.error(err);
  } finally {
    matchmakerSubmit.disabled = false;
    matchmakerSubmit.textContent = "find my match";
  }
}

function renderMatchmakerResults(data) {
  matchmakerGrid.innerHTML = "";
  matchmakerIntentTags.innerHTML = "";

  const { results, detected_intent, query, semantic_search_enabled } = data;

  matchmakerTitle.textContent = results.length
    ? `${results.length} pick${results.length === 1 ? "" : "s"} for "${query}"${
        semantic_search_enabled ? "" : " (semantic search offline - using text match)"
      }`
    : `No matches for "${query}"`;

  const chips = [];
  if (detected_intent?.mood) chips.push(detected_intent.mood);
  (detected_intent?.genres || []).forEach((g) => chips.push(g));
  if (detected_intent?.multiplayer === true) chips.push("multiplayer");
  if (detected_intent?.multiplayer === false) chips.push("single-player");
  if (detected_intent?.playtime_minutes) chips.push(`~${detected_intent.playtime_minutes} min`);
  if (detected_intent?.difficulty) chips.push(detected_intent.difficulty);

  chips.forEach((c) => {
    const tag = document.createElement("span");
    tag.className = "intent-tag";
    tag.textContent = c;
    matchmakerIntentTags.appendChild(tag);
  });

  matchmakerEmpty.classList.toggle("hidden", results.length > 0);

  results.forEach((game) => matchmakerGrid.appendChild(buildPosterCard(game)));
}

function buildPosterCard(game) {
  const node = posterTemplate.content.cloneNode(true);

  const img = node.querySelector(".poster-card__image");
  img.src = game.cover_image || FALLBACK_COVER;
  img.alt = `${game.title} cover art`;
  img.onerror = () => {
    img.src = FALLBACK_COVER;
  };

  node.querySelector(".poster-card__match-badge").textContent = `\u2605 ${game.match_percentage}% Match`;
  node.querySelector(".poster-card__title").textContent = game.title;
  node.querySelector(".poster-card__description").textContent = game.description;

  const genresEl = node.querySelector(".poster-card__genres");
  game.genres.slice(0, 3).forEach((g) => {
    const pill = document.createElement("span");
    pill.className = "card__tag";
    pill.textContent = g;
    genresEl.appendChild(pill);
  });

  const whyList = node.querySelector(".poster-card__why-list");
  (game.why || []).forEach((reason) => {
    const li = document.createElement("li");
    li.textContent = reason;
    whyList.appendChild(li);
  });

  const likeBtn = node.querySelector(".poster-card__like");
  likeBtn.classList.toggle("liked", game.liked);
  likeBtn.textContent = game.liked ? "\u2665" : "\u2661";
  likeBtn.addEventListener("click", () => toggleLike(game.id, likeBtn));

  const detailsToggle = node.querySelector(".poster-card__details-toggle");
  const detailsPanel = node.querySelector(".poster-card__details");
  detailsPanel.innerHTML = `
    <span class="card__tag">${game.year}</span>
    <span class="card__tag">\u2605 ${game.rating}</span>
    <span class="card__tag">${game.platforms.join(", ")}</span>
  `;
  detailsToggle.addEventListener("click", () => {
    const isHidden = detailsPanel.classList.toggle("hidden");
    detailsToggle.textContent = isHidden ? "View details" : "Hide details";
  });

  return node;
}

matchmakerForm.addEventListener("submit", (e) => {
  e.preventDefault();
  runMatchmaker(matchmakerInput.value);
});

document.getElementById("matchmaker-examples").addEventListener("click", (e) => {
  const chip = e.target.closest(".example-chip");
  if (!chip) return;
  matchmakerInput.value = chip.dataset.query;
  runMatchmaker(chip.dataset.query);
});

refreshProfile();
