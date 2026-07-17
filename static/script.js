const body = document.body;
const page = body.dataset.page;

const audioPlayer = document.getElementById("audioPlayer");
const nowPlaying = document.getElementById("nowPlaying");
const albumArt = document.getElementById("albumArt");
const playlistEl = document.getElementById("playlist");

let currentSongId = null;
const DEFAULT_COVER = "/static/default-cover.svg";

// ---------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : text;
  return div.innerHTML;
}

function coverUrl(song) {
  return song.cover ? `/static/uploads/covers/${song.cover}` : DEFAULT_COVER;
}

// ---------------------------------------------------------------
// Render a list of songs into #playlist
// ---------------------------------------------------------------
function renderSongs(songs, emptyMessage) {
  if (!playlistEl) return;
  playlistEl.innerHTML = "";

  if (songs.length === 0) {
    playlistEl.innerHTML = `<li class="empty-msg">${escapeHtml(emptyMessage)}</li>`;
    return;
  }

  songs.forEach((song) => {
    const li = document.createElement("li");
    li.dataset.id = song.id;
    if (song.id === currentSongId) li.classList.add("active");

    const artistLink = page === "artist"
      ? escapeHtml(song.artist)
      : `<a class="artist-link" href="/artist/${encodeURIComponent(song.artist)}" onclick="event.stopPropagation()">${escapeHtml(song.artist)}</a>`;

    li.innerHTML = `
      <img class="thumb" src="${coverUrl(song)}" alt="">
      <div class="song-info" onclick='playSong(${JSON.stringify(song)})'>
        <span class="song-title">${escapeHtml(song.title)}</span>
        <span class="song-artist">${artistLink}</span>
      </div>
      <button class="fav-btn ${song.is_favorite ? "active" : ""}" title="Favorite" onclick="toggleFavorite(${song.id}, event)">${song.is_favorite ? "★" : "☆"}</button>
      <button class="delete-btn" onclick="deleteSong(${song.id}, event)">Delete</button>
    `;
    playlistEl.appendChild(li);
  });
}

// ---------------------------------------------------------------
// Play a selected song — updates audio, now-playing text, album art
// ---------------------------------------------------------------
function playSong(song) {
  currentSongId = song.id;
  audioPlayer.src = `/static/uploads/${song.filename}`;
  audioPlayer.play();
  if (nowPlaying) nowPlaying.textContent = `Now playing: ${song.title} — ${song.artist}`;
  if (albumArt) albumArt.src = coverUrl(song);
  refreshCurrentView();
}

// ---------------------------------------------------------------
// Favorite toggle
// ---------------------------------------------------------------
async function toggleFavorite(id, event) {
  event.stopPropagation();
  const res = await fetch(`/api/songs/${id}/favorite`, { method: "POST" });
  if (!res.ok) return;
  refreshCurrentView();
}

// ---------------------------------------------------------------
// Delete a song
// ---------------------------------------------------------------
async function deleteSong(id, event) {
  event.stopPropagation();
  if (!confirm("Delete this song?")) return;

  await fetch(`/api/songs/${id}`, { method: "DELETE" });

  if (id === currentSongId) {
    audioPlayer.pause();
    audioPlayer.src = "";
    if (nowPlaying) nowPlaying.textContent = "No song selected";
    if (albumArt) albumArt.src = DEFAULT_COVER;
    currentSongId = null;
  }

  refreshCurrentView();
}

// ---------------------------------------------------------------
// Page-specific loaders
// ---------------------------------------------------------------
async function loadHomePlaylist() {
  const res = await fetch("/api/songs");
  const songs = await res.json();
  renderSongs(songs, "No songs yet — upload one above.");
}

async function loadFavorites() {
  const res = await fetch("/api/songs?favorite=1");
  const songs = await res.json();
  renderSongs(songs, "No favorites yet — tap the star on a song to add one.");
}

async function loadArtistSongs(artist) {
  const res = await fetch(`/api/songs?artist=${encodeURIComponent(artist)}`);
  const songs = await res.json();
  renderSongs(songs, "No songs found for this artist.");
  const countEl = document.getElementById("artistCount");
  if (countEl) countEl.textContent = `${songs.length} song${songs.length === 1 ? "" : "s"}`;
}

async function loadArtistGrid() {
  const grid = document.getElementById("artistGrid");
  if (!grid) return;
  const res = await fetch("/api/artists");
  const artists = await res.json();

  grid.innerHTML = "";
  if (artists.length === 0) {
    grid.innerHTML = '<p class="empty-msg">No artists yet — upload a song first.</p>';
    return;
  }

  artists.forEach((a) => {
    const card = document.createElement("a");
    card.className = "artist-card";
    card.href = `/artist/${encodeURIComponent(a.artist)}`;
    card.innerHTML = `
      <img src="${a.cover ? `/static/uploads/covers/${a.cover}` : DEFAULT_COVER}" alt="">
      <div class="artist-card-name">${escapeHtml(a.artist)}</div>
      <div class="artist-card-count">${a.count} song${a.count === 1 ? "" : "s"}</div>
    `;
    grid.appendChild(card);
  });
}

function refreshCurrentView() {
  if (page === "home") loadHomePlaylist();
  else if (page === "favorites") loadFavorites();
  else if (page === "artist") loadArtistSongs(body.dataset.artist);
  else if (page === "artists") loadArtistGrid();
}

// ---------------------------------------------------------------
// Upload a new song (home page only)
// ---------------------------------------------------------------
const uploadForm = document.getElementById("uploadForm");
if (uploadForm) {
  const uploadStatus = document.getElementById("uploadStatus");

  uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const fileInput = document.getElementById("fileInput");
    const coverInput = document.getElementById("coverInput");
    const titleInput = document.getElementById("titleInput");
    const artistInput = document.getElementById("artistInput");

    if (!fileInput.files.length) {
      uploadStatus.textContent = "Please choose a file first.";
      uploadStatus.style.color = "#ef4444";
      return;
    }

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    formData.append("title", titleInput.value);
    formData.append("artist", artistInput.value);
    if (coverInput && coverInput.files.length) {
      formData.append("cover", coverInput.files[0]);
    }

    uploadStatus.textContent = "Uploading...";
    uploadStatus.style.color = "#facc15";

    const res = await fetch("/api/upload", {
      method: "POST",
      body: formData,
    });

    const data = await res.json();

    if (res.ok) {
      uploadStatus.textContent = "Uploaded successfully!";
      uploadStatus.style.color = "#34d399";
      uploadForm.reset();
      loadHomePlaylist();
    } else {
      uploadStatus.textContent = data.error || "Upload failed.";
      uploadStatus.style.color = "#ef4444";
    }
  });
}

// ---------------------------------------------------------------
// Initial load, based on which page we're on
// ---------------------------------------------------------------
refreshCurrentView();
