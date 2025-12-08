
# app.py — single-file Streamlit app (Spotify-compliant)
# Features:
# - Artist inputs become dropdowns when titles are present (with "Other" manual override).
# - Direct Spotify link buttons (safe fallback to Markdown links).
# - Auto genre-driven background; 🎸 emoji for any rock-related genre.
# - Standard (varied) recs + 🔁 Regenerate.
# - Niche buckets: Artists you may know / Discover (min 2 guaranteed) / Hidden gems (tracks) /
#   Songs from your genres (not your input artists) / Rising stars (informational).
# - Safe rendering & robust fallbacks. Client Credentials only (Search/Artist/Top Tracks/Related).

import os
import time
import json
import base64
import urllib.parse
import urllib.request
import urllib.error
import re
import unicodedata
import hashlib
import random
from datetime import datetime
from typing import List, Tuple, Dict, Optional

import streamlit as st

# =========================
#  UI: Page & Branding
# =========================
st.set_page_config(page_title="Song Recommendation (Spotify)", page_icon="🎵")
st.markdown("## 🎵 Song Recommendations")
st.caption("Each item includes an 'Open in Spotify' button for attribution.")
st.caption("Tip: typos are okay — we’ll fuzzy‑match your Title and Artist.")

# =========================
#  Secrets / Env
# =========================
def _get_secret(name: str) -> str:
    val = st.secrets.get(name, "") or os.getenv(name, "")
    return (val or "").strip()

CLIENT_ID = _get_secret("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = _get_secret("SPOTIFY_CLIENT_SECRET")

def link_button(label: str, url: str):
    """
    Safe link button:
      - Use st.link_button when available and URL non-empty.
      - Fallback to Markdown anchor if st.link_button isn’t available.
    """
    try:
        if url:
            st.link_button(label, url)
        else:
            st.write(label)
    except Exception:
        if url:
            st.markdown(f"{label}")
        else:
            st.write(label)

# =========================
#  Genre Themes (gradient & optional image)
# =========================
GENRE_THEMES = {
    "pop":        {"accent": "#FF62B3", "gradient": "linear-gradient(135deg,#ff9ac6 0%,#ffd1e0 100%)",
                   "image": "assets/bg_pop.jpg",        "emoji": "✨", "font": "system-ui"},
    "rock":       {"accent": "#FF3B3B", "gradient": "linear-gradient(135deg,#3f3f3f 0%,#0f0f0f 100%)",
                   "image": "assets/bg_rock.jpg",       "emoji": "🎸", "font": "system-ui"},
    "hip hop":    {"accent": "#FDBA3B", "gradient": "linear-gradient(135deg,#0e0e0e 0%,#1a1a 100%)",
                   "image": "assets/bg_hiphop.jpg",     "emoji": "🧢", "font": "system-ui"},
    "indie":      {"accent": "#66D9A3", "gradient": "linear-gradient(135deg,#94e3bf 0%,#e8fff4 100%)",
                   "image": "assets/bg_indie.jpg",      "emoji": "🍃", "font": "system-ui"},
    "electronic": {"accent": "#55C2FF", "gradient": "linear-gradient(135deg,#0b1d33 0%,#142a4d 100%)",
                   "image": "assets/bg_electronic.jpg", "emoji": "⚡", "font": "system-ui"},
    "jazz":       {"accent": "#9E7AFF", "gradient": "linear-gradient(135deg,#2e1a47 0%,#241a3a 100%)",
                   "image": "assets/bg_jazz.jpg",       "emoji": "🎷", "font": "Georgia, serif"},
    "classical":  {"accent": "#D3C4A4", "gradient": "linear-gradient(135deg,#f7f3e9 0%,#e6dcc7 100%)",
                   "image": "assets/bg_classical.jpg",  "emoji": "🎼", "font": "Georgia, serif"},
    "country":    {"accent": "#E39C5A", "gradient": "linear-gradient(135deg,#f2dcc1 0%,#e3c199 100%)",
                   "image": "assets/bg_country.jpg",    "emoji": "🤠", "font": "system-ui"},
    "latin":      {"accent": "#FF6F61", "gradient": "linear-gradient(135deg,#ffd4c6 0%,#ffc1b1 100%)",
                   "image": "assets/bg_latin.jpg",      "emoji": "💃", "font": "system-ui"},
    "k-pop":      {"accent": "#7AE0FF", "gradient": "linear-gradient(135deg,#7ae0ff 0%,#c2f2ff 100%)",
                   "image": "assets/bg_kpop.jpg",       "emoji": "🌈", "font": "system-ui"},
    "metal":      {"accent": "#A0A0A0", "gradient": "linear-gradient(135deg,#1a1a1a 0%,#2a2a2a 100%)",
                   "image": "assets/bg_metal.jpg",      "emoji": "🤘", "font": "system-ui"},
    "__default__":{"accent": "#1DB954", "gradient": "linear-gradient(135deg,#0b0b0b 0%,#141414 100%)",
                   "image": "assets/bg_default.jpg",    "emoji": "🎵", "font": "system-ui"},
}

def _interleave_lists(lists: List[List[Tuple[str, str]]]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    max_len = max((len(lst) for lst in lists), default=0)
    for i in range(max_len):
        for lst in lists:
            if i < len(lst):
                out.append(lst[i])
    return out

def build_css_theme(primary: dict, secondary: dict | None = None) -> dict:
    gradient = primary["gradient"] if not secondary else (
        f"linear-gradient(135deg,{primary['accent']}55 0%,{secondary['accent']}55 100%), {primary['gradient']}"
    )
    image_url = primary.get("image", "").strip()
    accent = primary["accent"]
    font = primary.get("font", "system-ui")
    css = f"""
    <style>
    .stApp {{
        background: {gradient};
        {"background-image: url('" + image_url + "'); background-size: cover; background-position: center;" if image_url else ""}
        font-family: {font};
    }}
    [data-testid="stAppViewContainer"] > .main {{
        background-color: rgba(0,0,0,0.25);
        border-radius: 12px;
        padding: 8px;
    }}
    .stButton>button {{
        background-color: {accent};
        color: white;
        border-radius: 10px;
        border: none;
        transition: transform .05s ease-in-out;
    }}
    .stButton>button:hover {{ transform: translateY(-1px); }}
    h1, h2, h3, h4, h5, h6 {{ color: {accent}; }}
    a {{ color: {accent}; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .badge {{
        display:inline-block; padding:4px 10px; margin:2px;
        border-radius: 999px; background-color: {accent}22; color: {accent};
        border: 1px solid {accent}55; font-size: 0.85rem;
    }}
    </style>
    """
    icon_set = {"artist": primary.get("emoji", "🎵"), "genre": "🏷️", "spark": "✨"}
    return {"css": css, "emoji": primary.get("emoji", "🎵"), "accent": accent, "icons": icon_set}

def _normalize_genre_label(g: str) -> str:
    """Canonical labels for theme mapping; treat anything containing 'rock' as 'rock'."""
    g_norm = (g or "").lower().strip()
    if "hip hop" in g_norm or "hip-hop" in g_norm or "rap" in g_norm:
        return "hip hop"
    if "k-pop" in g_norm or "kpop" in g_norm:
        return "k-pop"
    if "rock" in g_norm:
        return "rock"
    return g_norm

def pick_theme_by_genres(genres: List[str]) -> dict:
    counts: Dict[str, int] = {}
    for g in genres:
        g_norm = _normalize_genre_label(g)
        if g_norm in GENRE_THEMES:
            counts[g_norm] = counts.get(g_norm, 0) + 1
    top = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    if not top:
        theme = build_css_theme(GENRE_THEMES["__default__"])
        return theme
    primary = GENRE_THEMES.get(top[0][0], GENRE_THEMES["__default__"])
    secondary = GENRE_THEMES.get(top[1][0], GENRE_THEMES["__default__"]) if len(top) >= 2 else None
    theme = build_css_theme(primary, secondary)
    # Force guitar emoji/icons if any input genre mentions "rock"
    if any(("rock" in (g or "").lower()) for g in genres):
        theme["emoji"] = "🎸"
        theme["icons"]["artist"] = "🎸"
    return theme

# =========================
#  Spotify Client (Client Credentials; allowed endpoints only)
# =========================
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"

class SpotifyClient:
    def __init__(self, client_id: str, client_secret: str, market: str = "US"):
        self.client_id = (client_id or "").strip()
        self.client_secret = (client_secret or "").strip()
        self.market = (market or "US").upper()
        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0

    def _fetch_access_token(self) -> None:
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("utf-8")).decode("utf-8")
        data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")
        req = urllib.request.Request(
            SPOTIFY_TOKEN_URL,
            data=data,
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            self._access_token = payload["access_token"]
            self._expires_at = time.time() + float(payload.get("expires_in", 3600)) * 0.95

    def _ensure_token(self) -> str:
        if not self._access_token or time.time() >= self._expires_at:
            self._fetch_access_token()
        return self._access_token

    def _api_get(self, path: str, params: Dict[str, str] = None) -> Dict:
        token = self._ensure_token()
        url = f"{SPOTIFY_API_BASE}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"}, method="GET")
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # Search helpers
    def search_track(self, title: str, artist: str, limit: int = 50) -> List[Dict]:
        t = (title or "").strip()
        a = (artist or "").strip()
        if not t and not a: return []
        q = " ".join([f'track:"{t}"' if t else "", f'artist:"{a}"' if a else ""]).strip()
        data = self._api_get("/search", {"q": q, "type": "track", "limit": str(limit), "market": self.market})
        return (data.get("tracks", {}) or {}).get("items", []) or []

    def search_tracks_filtered(self, title: str = "", artist: str = "", limit: int = 10) -> List[Dict]:
        results: List[Dict] = []
        q = " ".join([f'track:"{title.strip()}"' if title else "", f'artist:"{artist.strip()}"' if artist else ""]).strip()
        if q:
            data = self._api_get("/search", {"q": q, "type": "track", "limit": str(limit), "market": self.market})
            results = (data.get("tracks") or {}).get("items", []) or []
        if not results:
            q2 = " ".join([f"track:{title.strip()}" if title else "", f"artist:{artist.strip()}" if artist else ""]).strip()
            if q2:
                data2 = self._api_get("/search", {"q": q2, "type": "track", "limit": str(limit), "market": self.market})
                results = (data2.get("tracks") or {}).get("items", []) or []
        return results

    def search_tracks_free(self, query: str, limit: int = 10) -> List[Dict]:
        q = (query or "").strip()
        if not q: return []
        data = self._api_get("/search", {"q": q, "type": "track", "limit": str(limit), "market": self.market})
        return (data.get("tracks") or {}).get("items", []) or []

    def search_artist_by_name(self, name: str, limit: int = 5) -> List[Dict]:
        n = (name or "").strip()
        if not n: return []
        data = self._api_get("/search", {"q": n, "type": "artist", "limit": str(limit), "market": self.market})
        return (data.get("artists") or {}).get("items", []) or []

    # Artist data
    def get_artist(self, artist_id: str) -> Dict:
        return self._api_get(f"/artists/{artist_id}", {})

    def get_artist_top_tracks(self, artist_id: str, limit: int = 10) -> List[Dict]:
        data = self._api_get(f"/artists/{artist_id}/top-tracks", {"market": self.market})
        items = data.get("tracks", []) or []
        return items[:limit]

    def get_related_artists(self, artist_id: str) -> List[Dict]:
        data = self._api_get(f"/artists/{artist_id}/related-artists", {})
        return data.get("artists", []) or []

    def search_artists_by_genre(self, genre: str, limit: int = 10, offset: int = 0) -> List[Dict]:
        g = (genre or "").strip()
        if not g: return []
        q = f'genre:"{g}"'
        data = self._api_get(
            "/search", {"q": q, "type": "artist", "limit": str(limit), "offset": str(offset), "market": self.market}
        )
        return (data.get("artists") or {}).get("items", []) or []

    @staticmethod
    def extract_track_core(track: Dict) -> Tuple[str, str, str, str, str]:
        tid = track.get("id") or ""
        tname = track.get("name") or ""
        artists = track.get("artists") or []
        a_id = artists[0].get("id") if artists else ""
        a_name = artists[0].get("name") if artists else ""
        turl = (track.get("external_urls") or {}).get("spotify") or (f"https://open.spotify.com/track/{tid}" if tid else "")
        return tid, tname, a_id, a_name, turl

# =========================
#  Fuzzy + Resolution helpers
# =========================
try:
    from rapidfuzz import fuzz
    def _ratio(a: str, b: str) -> float:
        return float(fuzz.token_sort_ratio(a, b))
except Exception:
    from difflib import SequenceMatcher
    def _ratio(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio() * 100.0

def _clean(s: str) -> str:
    s = s or ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _try_search_variants(sp: SpotifyClient, title: str, artist: str, limit: int = 10) -> List[dict]:
    results: List[dict] = []
    try:
        results = sp.search_tracks_filtered(title=title, artist=artist, limit=limit) or []
    except Exception:
        results = []
    if not results:
        try:
            q = " ".join([title or "", artist or ""]).strip()
            if q:
                results = sp.search_tracks_free(q, limit=limit) or []
        except Exception:
            results = []
    if not results:
        try: results = sp.search_track(title, artist, limit=limit) or []
        except Exception: results = []
    if not results and title:
        try: results = sp.search_track(title, "", limit=limit) or []
        except Exception: pass
    if not results and artist:
        try: results = sp.search_track("", artist, limit=limit) or []
        except Exception: pass
    if not results:
        t_first = (title or "").split()[0] if title else ""
        a_first = (artist or "").split()[0] if artist else ""
        if t_first or a_first:
            try: results = sp.search_track(t_first, a_first, limit=limit) or []
            except Exception: pass
    return results

def resolve_favorite_to_artist(
    sp: SpotifyClient,
    title: str,
    artist: str,
    limit: int = 10,
    accept_threshold: float = 72.0,
) -> Optional[Tuple[str, str, List[str]]]:
    title_clean = _clean(title)
    artist_clean = _clean(artist)
    candidates = _try_search_variants(sp, title, artist, limit=limit)
    best_item = None
    best_score = -1.0
    for tr in candidates:
        tr_title_clean = _clean(tr.get("name", ""))
        artists = tr.get("artists") or []
        lead_name_clean = _clean(artists[0].get("name", "")) if artists else ""
        score_title = _ratio(title_clean, tr_title_clean) if title_clean else 0.0
        score_artist = _ratio(artist_clean, lead_name_clean) if artist_clean else 0.0
        score = 0.6 * score_artist + 0.4 * score_title
        if score > best_score:
            best_score = score
            best_item = tr
    if best_item is None or best_score < accept_threshold:
        return None
    artists = best_item.get("artists") or []
    aid = artists[0].get("id") if artists else None
    adata = sp.get_artist(aid) if aid else {}
    return (
        aid or "",
        adata.get("name") or (artists[0].get("name") if artists else ""),
        adata.get("genres", []) or [],
    )

def resolve_artist_robust(sp: SpotifyClient, title: str, artist: str) -> Optional[Tuple[str, str, List[str]]]:
    try:
        r = resolve_favorite_to_artist(sp, title, artist, limit=10, accept_threshold=72.0)
        if r: return r
        if artist:
            items = sp.search_artist_by_name(artist, limit=3)
            if items:
                a = items[0]
                aid = a.get("id", "")
                adata = sp.get_artist(aid) if aid else {}
                return (aid, adata.get("name", a.get("name","")), adata.get("genres", []) or [])
        if title and not artist:
            items = sp.search_track(title, "", limit=3)
            if items:
                tid, tname, pa_id, pa_name, _ = SpotifyClient.extract_track_core(items[0])
                if pa_id:
                    adata = sp.get_artist(pa_id)
                    return (pa_id, adata.get("name", pa_name), adata.get("genres", []) or [])
    except Exception:
        return None
    return None

# =========================
#  Suggestions helper (artist dropdowns from typed title)
# =========================
def fetch_artist_suggestions_for_title(
    client_id: str,
    client_secret: str,
    market: str,
    title: str,
    limit: int = 25
) -> list[str]:
    title = (title or "").strip()
    if not title:
        return []
    sp = SpotifyClient(client_id, client_secret, market=market or "US")
    try:
        items = sp.search_track(title, "", limit=50)
    except Exception:
        return []
    names = []
    for tr in items or []:
        for ar in (tr.get("artists") or []):
            name = (ar.get("name") or "").strip()
            if name:
                names.append(name)
    seen, out = set(), []
    for n in names:
        k = n.lower()
        if k not in seen:
            seen.add(k)
            out.append(n)
        if len(out) >= limit:
            break
    return out

def artist_select_or_input(label: str, title_key: str, manual_key: str, pick_key: str, market: str) -> str:
    """
    Render the Artist field as a dropdown when a Title is present:
    - Options: ["— choose —"] + suggestions + ["Other (type manually)"]
    - If "Other..." chosen (or no suggestions), show a small text input below.
    Returns the final chosen/typed artist string.
    NOTE: This function does NOT write to st.session_state for the chosen value to avoid Widget state conflicts.
    """
    title_val = (st.session_state.get(title_key, "") or "").strip()
    current_manual = (st.session_state.get(manual_key, "") or "")

    if CLIENT_ID and CLIENT_SECRET and title_val:
        try:
            opts = fetch_artist_suggestions_for_title(CLIENT_ID, CLIENT_SECRET, market, title_val, limit=25)
        except Exception:
            opts = []

        if opts:
            options = ["— choose —"] + opts + ["Other (type manually)"]
            # Preselect current if present
            pre_index = 0
            if current_manual in opts:
                pre_index = 1 + opts.index(current_manual)
            choice = st.selectbox(
                label,
                options,
                index=pre_index,
                key=pick_key,
                help="Pick an artist for this title or choose 'Other' to type manually."
            )
            if choice and choice not in ("— choose —", "Other (type manually)"):
                return choice
            # Manual entry
            manual = st.text_input(f"{label} (type manually)", value=current_manual, key=manual_key)
            return manual
        else:
            # No suggestions → simple text input (manual only)
            manual = st.text_input(label, value=current_manual, key=manual_key)
            return manual
    else:
        # No title or no creds → simple manual text input
        manual = st.text_input(label, value=current_manual, key=manual_key)
        return manual

# =========================
#  Rendering helpers (SAFE + link buttons)
# =========================
def _sanitize_items(items: List) -> List[Tuple[str, str]]:
    """Ensure items are a list of (text, url) tuples; drop malformed entries."""
    out: List[Tuple[str, str]] = []
    for it in (items or []):
        if isinstance(it, (list, tuple)) and len(it) >= 2:
            text = str(it[0] or "").strip()
            url = str(it[1] or "").strip()
            if text:
                out.append((text, url))
        elif isinstance(it, str):
            txt = it.strip()
            if txt:
                out.append((txt, ""))  # no link
        elif isinstance(it, dict):
            text = str(it.get("text", "")).strip()
            url = str(it.get("url", "")).strip()
            if text:
                out.append((text, url))
    return out

def render_items_section(
    title: str,
    items: List,
    fallback_text: str = "Nothing here right now.",
    fallback_link_text: str = "Discover on Spotify",
    fallback_link_url: str = "https://open.spotify.com/explore",
):
    """Safely render a recommendation section; always robust even if items are empty."""
    st.markdown(f"#### {title}")
    safe_items = _sanitize_items(items)
    if not safe_items:
        st.info(fallback_text)
        if fallback_link_url:
            link_button(fallback_link_text, fallback_link_url)
        st.divider()
        return
    for text, url in safe_items:
        st.write(f"- **{text}**")
        if url:
            link_button("Open in Spotify", url)
    st.divider()

# =========================
#  Recommendation logic (with regenerate support)
# =========================
def _stable_shuffle(items: List[Tuple[str, str]], salt: str) -> List[Tuple[str, str]]:
    seed_int = int.from_bytes(hashlib.sha256(salt.encode("utf-8")).digest(), "big")
    rng = random.Random(seed_int)
    items_copy = items.copy()
    rng.shuffle(items_copy)
    return items_copy

def recommend_from_favorites(
    client_id: str,
    client_secret: str,
    market: str,
    favorites: List[Tuple[str, str]],
    max_recs: int = 3,
    regen_nonce: int = 0,
) -> List[Tuple[str, str]]:
    sp = SpotifyClient(client_id, client_secret, market=market or "US")
    favorites = [(t.strip(), a.strip()) for (t, a) in favorites if t and a]
    fav_keys = {(t.lower(), a.lower()) for (t, a) in favorites}
    artist_infos: List[Tuple[str, str, List[str]]] = []
    for (title, artist) in favorites:
        resolved = resolve_artist_robust(sp, title, artist)
        if resolved:
            aid, aname, a_genres = resolved
            if aid:
                artist_infos.append((aid, aname, a_genres))
    if not artist_infos:
        mixed = []
        for g in ["indie", "electronic", "hip hop", "latin", "pop"]:
            try:
                rows = sp.search_artists_by_genre(g, limit=10)
                for ar in rows[:3]:
                    name = ar.get("name"); url = (ar.get("external_urls") or {}).get("spotify","")
                    if not url:
                        aid = ar.get("id",""); url = f"https://open.spotify.com/artist/{aid}" if aid else ""
                    if name and url: mixed.append((f"{name} ({g})", url))
            except Exception:
                continue
        return mixed[:max_recs] if mixed else [("Discover on Spotify", "https://open.spotify.com/explore")]
    per_artist_fav: List[List[Tuple[str, str]]] = []
    for (aid, _aname, _g) in artist_infos:
        lst: List[Tuple[str, str]] = []
        try:
            top = sp.get_artist_top_tracks(aid, limit=10)
            if not top:
                sp_us = SpotifyClient(client_id, client_secret, market="US")
                top = sp_us.get_artist_top_tracks(aid, limit=10)
            for tr in top:
                _, tname, _, pa_name, turl = SpotifyClient.extract_track_core(tr)
                if not tname or not pa_name:
                    continue
                key = (tname.strip().lower(), pa_name.strip().lower())
                if key in fav_keys:
                    continue
                lst.append((f"{tname} — {pa_name}", turl or ""))
        except Exception:
            pass
        per_artist_fav.append(lst)
    rng = random.Random(regen_nonce or 0)
    per_artist_related: List[List[Tuple[str, str]]] = []
    for (aid, _aname, _g) in artist_infos:
        lst: List[Tuple[str, str]] = []
        try:
            related = sp.get_related_artists(aid) or []
            rng.shuffle(related)
            pick = related[:3] if related else []
            for ar in pick:
                rid = ar.get("id"); rname = ar.get("name")
                if not rid or not rname: continue
                url_artist = (ar.get("external_urls") or {}).get("spotify") or f"https://open.spotify.com/artist/{rid}"
                try:
                    rtop = sp.get_artist_top_tracks(rid, limit=5)
                    if not rtop:
                        sp_us = SpotifyClient(client_id, client_secret, market="US")
                        rtop = sp_us.get_artist_top_tracks(rid, limit=5)
                    if not rtop:
                        lst.append((rname, url_artist))
                    for tr in rtop:
                        _, tname, _, pa_name, turl = SpotifyClient.extract_track_core(tr)
                        if not tname or not pa_name: continue
                        lst.append((f"{tname} — {pa_name}", turl or ""))
                except Exception:
                    lst.append((rname, url_artist))
        except Exception:
            pass
        per_artist_related.append(lst)
    fav_combined = _interleave_lists(per_artist_fav)
    rel_combined = _interleave_lists(per_artist_related)
    mixed: List[Tuple[str, str]] = []
    i_f, i_r = 0, 0
    while i_f < len(fav_combined) or i_r < len(rel_combined):
        if i_f < len(fav_combined):
            mixed.append(fav_combined[i_f]); i_f += 1
        if i_r < len(rel_combined):
            mixed.append(rel_combined[i_r]); i_r += 1
    if not mixed:
        for g in ["indie", "electronic", "hip hop", "latin", "pop"]:
            try:
                rows = sp.search_artists_by_genre(g, limit=10)
                for ar in rows[:2]:
                    name = ar.get("name")
                    aid = ar.get("id","")
                    url = (ar.get("external_urls") or {}).get("spotify") or (f"https://open.spotify.com/artist/{aid}" if aid else "")
                    if name and url: mixed.append((f"{name} ({g})", url))
            except Exception:
                continue
    date_key = datetime.utcnow().strftime("%Y%m%d")
    salt = f"{market}|{date_key}|{'|'.join([t+'—'+a for (t,a) in favorites])}|{regen_nonce}"
    mixed_shuffled = _stable_shuffle(mixed, salt)
    seen, recs = set(), []
    for (text, url) in mixed_shuffled:
        if text not in seen:
            seen.add(text)
            recs.append((text, url))
        if len(recs) >= max_recs:
            break
    if not recs:
        recs = mixed_shuffled[:max_recs] if mixed_shuffled else [("Explore Spotify", "https://open.spotify.com/explore")]
    return recs

def _backfill_genres_from_related(sp: SpotifyClient, fav_artist_infos: List[Tuple[str,str,List[str]]]) -> set[str]:
    genres = set()
    for (aid, _aname, _g) in fav_artist_infos:
        try:
            related = sp.get_related_artists(aid)
            for ar in related:
                for g in (ar.get("genres") or []):
                    if g: genres.add(g)
        except Exception:
            continue
    return genres

def build_recommendation_buckets(
    client_id: str,
    client_secret: str,
    market: str,
    favorites: List[Tuple[str, str]],
    track_pop_max: int = 35,
    per_bucket: int = 5,
    min_artists: int = 2,
    regen_nonce: int = 0,
) -> Dict[str, List[Tuple[str, str]]]:
    sp = SpotifyClient(client_id, client_secret, market=market or "US")
    favorites = [(t.strip(), a.strip()) for (t, a) in favorites if t and a]
    rng = random.Random(regen_nonce or 0)
    fav_keys = {(t.lower(), a.lower()) for (t, a) in favorites}
    fav_artist_names_lower = {a.lower() for (_, a) in favorites}

    # Resolve favorites
    fav_artist_infos: List[Tuple[str, str, List[str]]] = []
    for (title, artist) in favorites:
        r = resolve_artist_robust(sp, title, artist)
        if r:
            aid, aname, a_genres = r
            if aid:
                fav_artist_infos.append((aid, aname, a_genres or []))
    fav_artist_ids = {aid for (aid, _, _) in fav_artist_infos}

    buckets: Dict[str, List[Tuple[str, str]]] = {
        "Hidden gems from your favorite artists": [],
        "Artists you may know": [],
        "Discover": [],
        "Songs from your genres (not your input artists)": [],
        "Rising stars in your genres": [],
    }

    # ---------- 1) Hidden gems (tracks) ----------
    per_artist_hidden: List[List[Tuple[str, str]]] = []
    for (aid, aname, _genres) in fav_artist_infos:
        lst: List[Tuple[str, str]] = []
        try:
            top = sp.get_artist_top_tracks(aid, limit=10)
            if not top:
                sp_us = SpotifyClient(client_id, client_secret, market="US")
                top = sp_us.get_artist_top_tracks(aid, limit=10)
            rng.shuffle(top)
            for tr in top:
                tname = tr.get("name")
                popularity = tr.get("popularity", 50)
                artists = tr.get("artists") or []
                pa_name = artists[0].get("name") if artists else aname
                turl = (tr.get("external_urls") or {}).get("spotify", "")
                if tname and turl and popularity <= track_pop_max:
                    lst.append((f"{tname} — {pa_name}", turl))
            if not lst:
                for tr in top[:10]:
                    tname = tr.get("name")
                    artists = tr.get("artists") or []
                    pa_name = artists[0].get("name") if artists else aname
                    turl = (tr.get("external_urls") or {}).get("spotify", "")
                    if tname and turl:
                        lst.append((f"{tname} — {pa_name}", turl))
        except Exception:
            pass
        per_artist_hidden.append(lst)
    hidden_combined = _interleave_lists(per_artist_hidden)
    if not hidden_combined:
        hidden_combined = [("Explore Spotify", "https://open.spotify.com/explore")]
    buckets["Hidden gems from your favorite artists"] = hidden_combined[:max(2, per_bucket)]

    # ---------- 2) Recommended artists (label only, with min-2 Discover) ----------
    def _artist_url(ar: Dict) -> str:
        return (ar.get("external_urls") or {}).get("spotify") or (f"https://open.spotify.com/artist/{ar.get('id','')}" if ar.get("id") else "")

    related_all: List[Tuple[str, str, int]] = []
    for (aid, _aname, _genres) in fav_artist_infos:
        try:
            rel = sp.get_related_artists(aid) or []
            rng.shuffle(rel)
            for ar in rel:
                name = ar.get("name","")
                pop = ar.get("popularity", 50)
                url = _artist_url(ar)
                if name and url:
                    related_all.append((name, url, pop))
        except Exception:
            continue

    # If thin, backfill from union genres (no pop filtering; just labeling later)
    if len(related_all) < min_artists:
        union_genres = {g for (_aid,_aname,gs) in fav_artist_infos for g in (gs or [])}
        if not union_genres:
            union_genres = {"indie","electronic","hip hop","pop","latin"}
        for g in list(union_genres)[:5]:
            try:
                items = sp.search_artists_by_genre(g, limit=30)
                rng.shuffle(items)
                for ar in items[:10]:
                    name = ar.get("name",""); pop = ar.get("popularity",50)
                    url = _artist_url(ar)
                    if name and url:
                        related_all.append((name, url, pop))
            except Exception:
                continue

    # Label into categories
    may_know, discover = [], []
    def _dedupe(items: List[Tuple[str,str]]) -> List[Tuple[str,str]]:
        out, seen = [], set()
        for n,u in items:
            k = (n or "").strip().lower()
            if k and k not in seen:
                seen.add(k)
                out.append((n,u))
        return out

    for name, url, pop in related_all:
        if pop >= 60: may_know.append((name, url))
        else:         discover.append((name, url))

    # De-duplicate initial sets
    may_know = _dedupe(may_know)
    discover = _dedupe(discover)

    # --- Guarantee at least two "Discover" items ---
    def _ensure_min_discover(min_count: int = 2) -> None:
        if len(discover) >= min_count:
            return
        exclude_names = {a.lower() for (_, a) in favorites} | {n.lower() for (n, _) in discover} | {n.lower() for (n, _) in may_know}
        union_genres = {g for (_aid,_aname,gs) in fav_artist_infos for g in (gs or [])}
        if not union_genres:
            union_genres = {"indie","electronic","hip hop","pop","latin"}
        for g in list(union_genres)[:5]:
            try:
                items = sp.search_artists_by_genre(g, limit=50)
                rng.shuffle(items)
                for ar in items:
                    name = (ar.get("name") or "").strip()
                    url = _artist_url(ar)
                    if not name or not url:
                        continue
                    if name.lower() in exclude_names:
                        continue
                    discover.append((name, url))
                    exclude_names.add(name.lower())
                    if len(discover) >= min_count:
                        return
            except Exception:
                continue

    _ensure_min_discover(min_count=2)

    # Final trim per bucket settings
    may_know = may_know[:max(2, per_bucket)]
    discover = discover[:max(2, per_bucket)]

    # If absolutely empty (extreme edge), add a single explore link to avoid blanks
    if not (may_know or discover):
        may_know = [("Explore artists", "https://open.spotify.com/genre")]

    buckets["Artists you may know"] = may_know
    buckets["Discover"] = discover

    # ---------- 3) Songs from your genres (not your input artists) ----------
    genre_pool = {g for (_aid, _aname, genres) in fav_artist_infos for g in (genres or [])}
    if not genre_pool:
        genre_pool |= _backfill_genres_from_related(sp, fav_artist_infos)
    if not genre_pool:
        genre_pool = {"indie", "alternative", "singer-songwriter", "electronic", "hip hop", "afrobeats", "latin"}

    per_genre_track_lists: List[List[Tuple[str, str]]] = []
    for genre in list(genre_pool)[:3]:
        lst: List[Tuple[str, str]] = []
        try:
            artists_by_genre = sp.search_artists_by_genre(genre, limit=30)
            rng.shuffle(artists_by_genre)
            for ar in artists_by_genre:
                aid = ar.get("id", "")
                aname = ar.get("name", "")
                if not aid or not aname:
                    continue
                if aid in fav_artist_ids or (aname.lower() in fav_artist_names_lower):
                    continue
                try:
                    top = sp.get_artist_top_tracks(aid, limit=5)
                    if not top:
                        sp_us = SpotifyClient(client_id, client_secret, market="US")
                        top = sp_us.get_artist_top_tracks(aid, limit=5)
                    rng.shuffle(top)
                    for tr in top:
                        _, tname, _, pa_name, turl = SpotifyClient.extract_track_core(tr)
                        if not tname or not pa_name or not turl:
                            continue
                        key = (tname.strip().lower(), pa_name.strip().lower())
                        if key in fav_keys:
                            continue
                        lst.append((f"{tname} — {pa_name}", turl))
                        if len(lst) >= 8:
                            break
                except Exception:
                    continue
                if len(lst) >= 12:
                    break
        except Exception:
            pass
        per_genre_track_lists.append(lst)
    genre_tracks_combined = _interleave_lists(per_genre_track_lists)
    if not genre_tracks_combined:
        genre_tracks_combined = [("Discover on Spotify", "https://open.spotify.com/explore")]
    buckets["Songs from your genres (not your input artists)"] = genre_tracks_combined[:max(2, per_bucket)]

    # ---------- 4) Rising stars in your genres ----------
    per_genre_lists = []
    for genre in list(genre_pool)[:3]:
        lst = []
        try:
            items = sp.search_artists_by_genre(genre, limit=30)
            rng.shuffle(items)
            for ar in items[:10]:
                name = ar.get("name"); aid = ar.get("id","")
                url = (ar.get("external_urls") or {}).get("spotify") or (f"https://open.spotify.com/artist/{aid}" if aid else "")
                if name and url:
                    lst.append((f"{name} ({genre})", url))
        except Exception:
            pass
        per_genre_lists.append(lst)
    rising_combined = _interleave_lists(per_genre_lists)
    if not rising_combined:
        rising_combined = [("Discover on Spotify", "https://open.spotify.com/explore")]
    buckets["Rising stars in your genres"] = rising_combined[:max(per_bucket, min_artists)]

    return buckets

def collect_genres_for_favorites(
    client_id: str, client_secret: str, market: str, favorites: List[Tuple[str,str]]
) -> List[str]:
    sp = SpotifyClient(client_id, client_secret, market=market or "US")
    fav_artist_infos: List[Tuple[str, str, List[str]]] = []
    for (title, artist) in [(t.strip(), a.strip()) for (t, a) in favorites if t and a]:
        r = resolve_artist_robust(sp, title, artist)
        if r:
            aid, aname, a_genres = r
            if aid:
                fav_artist_infos.append((aid, aname, a_genres or []))
    genre_pool = [g for (_aid, _name, genres) in fav_artist_infos for g in (genres or [])]
    if len(genre_pool) == 0:
        genre_pool = list(_backfill_genres_from_related(sp, fav_artist_infos)) or []
    return genre_pool

# =========================
#  Sidebar / Inputs (Artist boxes ARE the dropdowns)
# =========================
with st.sidebar:
    st.header("Settings")
    market = st.text_input("Market (country code)", value="US", help="e.g., US, GB, KR, JP")
    with st.expander("🎛️ Advanced controls", expanded=False):
        track_pop_max = st.slider("Max track popularity (hidden gems — tracks only)", 0, 100, 35, help="Lower = more niche for track picks")
        per_bucket = st.slider("Items per bucket", 1, 10, 5)
        min_artists = st.slider("Minimum artists per bucket (guaranteed)", 0, 5, 2)

# Titles & Artists (artist field switches to dropdown when title present)
col1, col2 = st.columns(2)
with col1:
    st.text_input("Favorite #1 — Title", key="s1_title", placeholder="e.g., Blinding Lights")
with col2:
    s1_artist_val = artist_select_or_input("Favorite #1 — Artist", "s1_title", "s1_artist_manual", "s1_artist_pick", market)

col1, col2 = st.columns(2)
with col1:
    st.text_input("Favorite #2 — Title", key="s2_title", placeholder="e.g., Yellow")
with col2:
    s2_artist_val = artist_select_or_input("Favorite #2 — Artist", "s2_title", "s2_artist_manual", "s2_artist_pick", market)

col1, col2 = st.columns(2)
with col1:
    st.text_input("Favorite #3 — Title", key="s3_title", placeholder="e.g., Bad Guy")
with col2:
    s3_artist_val = artist_select_or_input("Favorite #3 — Artist", "s3_title", "s3_artist_manual", "s3_artist_pick", market)

# Action buttons: Recommend + Regenerate
if "regen_nonce" not in st.session_state:
    st.session_state["regen_nonce"] = 0
colA, colB = st.columns([1,1])
with colA:
    run = st.button("Recommend", type="primary")
with colB:
    regenerate = st.button("🔁 Regenerate")
if regenerate:
    st.session_state["regen_nonce"] += 1

# =========================
#  Handlers
# =========================
def _ensure_creds() -> bool:
    if not CLIENT_ID or not CLIENT_SECRET:
        st.error(
            "No Spotify credentials found.\n\n"
            "Add them to **Manage app → Settings → Secrets** in Streamlit Cloud using TOML:\n\n"
            "```toml\nSPOTIFY_CLIENT_ID = \"your-client-id\"\nSPOTIFY_CLIENT_SECRET = \"your-client-secret\"\n```"
        )
        return False
    return True

def _collect_favorites_with_feedback(
    s1_artist_val: str, s2_artist_val: str, s3_artist_val: str
) -> List[Tuple[str, str]]:
    rows = [
        ("Favorite #1", (st.session_state.get("s1_title","") or "").strip(), (s1_artist_val or "").strip()),
        ("Favorite #2", (st.session_state.get("s2_title","") or "").strip(), (s2_artist_val or "").strip()),
        ("Favorite #3", (st.session_state.get("s3_title","") or "").strip(), (s3_artist_val or "").strip()),
    ]
    valid: List[Tuple[str, str]] = []
    for label, t, a in rows:
        if t and a:
            valid.append((t, a))
        elif t and not a:
            st.warning(f"{label}: Title entered but Artist is missing.")
        elif a and not t:
            st.warning(f"{label}: Artist entered but Title is missing.")
    return valid

if run or regenerate:
    if not _ensure_creds():
        st.stop()

    favorites = _collect_favorites_with_feedback(s1_artist_val, s2_artist_val, s3_artist_val)
    if not favorites:
        st.warning("Please enter at least one valid Title + Artist pair.")
        st.stop()

    # Auto genre-driven background
    genres = collect_genres_for_favorites(CLIENT_ID, CLIENT_SECRET, market, favorites)
    theme = pick_theme_by_genres(genres)
    st.markdown(theme["css"], unsafe_allow_html=True)
    st.markdown(f"### {theme['emoji']} Personalized Interface (auto)")

    # Context badges (artists + genres)
    icons = theme["icons"]
    st.markdown(f"**{icons['artist']} Inputs:** "
                f"`{s1_artist_val or '—'}` · `{s2_artist_val or '—'}` · `{s3_artist_val or '—'}`")
    unique_genres = sorted(set([g.lower() for g in genres]))[:6] if genres else []
    if unique_genres:
        st.markdown("**🏷️ Detected genres:** " + " ".join(
            [f"<span class='badge'>{g}</span>" for g in unique_genres]
        ), unsafe_allow_html=True)
    else:
        st.markdown("**🏷️ Detected genres:** <span class='badge'>mixed/unknown</span>", unsafe_allow_html=True)

    # Tabs
    tab_std, tab_niche = st.tabs([f"{theme['emoji']} Standard (varied)", "🌱 Niche"])

    # --- Standard ---
    with tab_std:
        with st.spinner("Fetching recommendations..."):
            recs = recommend_from_favorites(
                CLIENT_ID, CLIENT_SECRET, market, favorites, max_recs=3, regen_nonce=st.session_state["regen_nonce"]
            )
        st.subheader("Recommendations")
        render_items_section(
            title="Top picks",
            items=recs,
            fallback_text="No recommendations found.",
            fallback_link_text="Explore Spotify",
            fallback_link_url="https://open.spotify.com/explore",
        )

    # --- Niche ---
    with tab_niche:
        with st.spinner("Fetching niche recommendations..."):
            buckets = build_recommendation_buckets(
                CLIENT_ID,
                CLIENT_SECRET,
                market,
                favorites,
                track_pop_max=track_pop_max,
                per_bucket=per_bucket,
                min_artists=min_artists,
                regen_nonce=st.session_state["regen_nonce"],
            )
        st.subheader("Recommended artists & tracks")

        render_items_section(
            title="Artists you may know",
            items=buckets.get("Artists you may know", []),
            fallback_text="We couldn't find familiar artists.",
            fallback_link_text="Explore artists",
            fallback_link_url="https://open.spotify.com/genre",
        )
        render_items_section(
            title="Discover",
            items=buckets.get("Discover", []),
            fallback_text="We couldn't find new discoveries.",
            fallback_link_text="Explore artists",
            fallback_link_url="https://open.spotify.com/genre",
        )
        render_items_section(
            title="Hidden gems from your favorite artists",
            items=buckets.get("Hidden gems from your favorite artists", []),
            fallback_text="No hidden gems found.",
            fallback_link_text="Explore Spotify",
            fallback_link_url="https://open.spotify.com/explore",
        )
        render_items_section(
            title="Songs from your genres (not your input artists)",
            items=buckets.get("Songs from your genres (not your input artists)", []),
            fallback_text="No genre-matched songs right now.",
            fallback_link_text="Discover on Spotify",
            fallback_link_url="https://open.spotify.com/explore",
        )
        render_items_section(
            title="Rising stars in your genres",
            items=buckets.get("Rising stars in your genres", []),
            fallback_text="No rising stars found.",
            fallback_link_text="Discover on Spotify",
            fallback_link_url="https://open.spotify.com/explore",
        )


# =========================
# Genre/Subgenre Theme Patch (drop-in)
# =========================
try:
    import streamlit as st
except Exception:
    # If your app imports st earlier, this will be a no-op
    st = None

def _norm(s: str) -> str:
    """Normalize a genre string: lowercase, strip, replace common punctuation."""
    return (s or "").strip().lower().replace("_", " ").replace("-", " ").replace("/", " ").replace("&", " and ")

# ---- Wide alias map so subgenres resolve to a main bucket (or themselves if themed) ----
GENRE_ALIASES = {
    # hip hop family
    "hip hop": "hip hop",
    "hiphop": "hip hop",
    "hip-hop": "hip hop",
    "trap": "trap",
    "drill": "drill",
    "boom bap": "hip hop",
    "k hip hop": "hip hop",
    # pop family
    "pop": "pop",
    "synthpop": "synthpop",
    "hyperpop": "hyperpop",
    "indie pop": "indie pop",
    "electropop": "electropop",
    "dance pop": "dance pop",
    "j pop": "j-pop",
    "j-pop": "j-pop",
    "k pop": "k-pop",
    "k-pop": "k-pop",
    "c pop": "c-pop",
    "mandopop": "c-pop",
    "t pop": "t-pop",
    # rock / alt family
    "rock": "rock",
    "alternative": "alternative rock",
    "alternative rock": "alternative rock",
    "alt rock": "alternative rock",
    "indie rock": "indie rock",
    "garage rock": "garage rock",
    "psychedelic rock": "psychedelic rock",
    "shoegaze": "shoegaze",
    "math rock": "math rock",
    "post rock": "post rock",
    "punk": "punk",
    "pop punk": "pop punk",
    "post punk": "post punk",
    "emo": "emo",
    "metal": "metal",
    "heavy metal": "heavy metal",
    "black metal": "black metal",
    "death metal": "death metal",
    "progressive metal": "progressive metal",
    "nu metal": "nu metal",
    "djent": "djent",
    # electronic / dance family
    "electronic": "electronic",
    "edm": "edm",
    "house": "house",
    "deep house": "deep house",
    "progressive house": "progressive house",
    "tech house": "tech house",
    "electro house": "electro house",
    "future house": "future house",
    "trance": "trance",
    "psytrance": "psytrance",
    "techno": "techno",
    "minimal techno": "minimal techno",
    "drum and bass": "drum and bass",
    "dnb": "drum and bass",
    "dubstep": "dubstep",
    "future bass": "future bass",
    "bass music": "bass music",
    "ambient": "ambient",
    "downtempo": "downtempo",
    "idm": "idm",
    "lofi": "lo-fi",
    "lo-fi": "lo-fi",
    "synthwave": "synthwave",
    "retrowave": "synthwave",
    "vaporwave": "vaporwave",
    "chiptune": "chiptune",
    # r&b / soul / funk
    "r&b": "r&b",
    "r and b": "r&b",
    "contemporary r&b": "r&b",
    "neo soul": "neo soul",
    "soul": "soul",
    "funk": "funk",
    # jazz / blues
    "jazz": "jazz",
    "bebop": "bebop",
    "swing": "swing",
    "bossa nova": "bossa nova",
    "blues": "blues",
    # latin / regional
    "latin": "latin",
    "reggaeton": "reggaeton",
    "salsa": "salsa",
    "bachata": "bachata",
    "cumbia": "cumbia",
    "latin pop": "latin pop",
    # reggae / ska / dancehall
    "reggae": "reggae",
    "dancehall": "dancehall",
    "ska": "ska",
    "ska punk": "ska punk",
    # african / global
    "afrobeat": "afrobeat",
    "afrobeats": "afrobeat",
    "amapiano": "amapiano",
    "world": "world",
    # country / folk / singer-songwriter
    "country": "country",
    "americana": "americana",
    "bluegrass": "bluegrass",
    "folk": "folk",
    "singer songwriter": "singer-songwriter",
    "singer-songwriter": "singer-songwriter",
    # classical / soundtrack
    "classical": "classical",
    "baroque": "baroque",
    "romantic": "romantic era",
    "opera": "opera",
    "choral": "choral",
    "soundtrack": "soundtrack",
    "score": "soundtrack",
    # misc
    "gospel": "gospel",
    "christian": "christian",
    "worship": "worship",
    "holiday": "holiday",
    "videogame": "video game",
    "video game": "video game"
}

# ---- Rich theme definitions: accent color, gradient, emoji, font ----
GENRE_THEMES_PATCH = {
    # Pop & relatives
    "pop":                 {"accent": "#FF62B3", "gradient": "linear-gradient(135deg,#ff9ac6 0%,#ffd1e0 100%)", "emoji": "✨", "font": "system-ui"},
    "synthpop":            {"accent": "#C06CFF", "gradient": "linear-gradient(135deg,#c06cff 0%,#ffe0ff 100%)", "emoji": "🎛️", "font": "system-ui"},
    "electropop":          {"accent": "#9C7BFF", "gradient": "linear-gradient(135deg,#a68cff 0%,#e0e6ff 100%)", "emoji": "⚡", "font": "system-ui"},
    "dance pop":           {"accent": "#FF7F50", "gradient": "linear-gradient(135deg,#ffae86 0%,#ffe3cf 100%)", "emoji": "💃", "font": "system-ui"},
    "indie pop":           {"accent": "#66D9A3", "gradient": "linear-gradient(135deg,#94e3bf 0%,#e8fff4 100%)", "emoji": "🌿", "font": "system-ui"},
    "hyperpop":            {"accent": "#FF3ED1", "gradient": "linear-gradient(135deg,#ffd3f6 0%,#ffeefe 100%)", "emoji": "🫧", "font": "system-ui"},
    "j-pop":               {"accent": "#FF6FAE", "gradient": "linear-gradient(135deg,#ffc2da 0%,#fff0f6 100%)", "emoji": "🍡", "font": "system-ui"},
    "k-pop":               {"accent": "#7BD3FF", "gradient": "linear-gradient(135deg,#c9ecff 0%,#f3fbff 100%)", "emoji": "🎀", "font": "system-ui"},
    "c-pop":               {"accent": "#FF9A00", "gradient": "linear-gradient(135deg,#ffd29a 0%,#fff1dc 100%)", "emoji": "🎎", "font": "system-ui"},
    "t-pop":               {"accent": "#00C7B7", "gradient": "linear-gradient(135deg,#a6f2ea 0%,#e9fffc 100%)", "emoji": "🐘", "font": "system-ui"},

    # Hip hop & relatives
    "hip hop":             {"accent": "#FDBA3B", "gradient": "linear-gradient(135deg,#141414 0%,#262626 100%)", "emoji": "🎤", "font": "system-ui"},
    "trap":                {"accent": "#FF4D4D", "gradient": "linear-gradient(135deg,#1a1a1a 0%,#3a3a3a 100%)", "emoji": "🪤", "font": "system-ui"},
    "drill":               {"accent": "#6C8CFF", "gradient": "linear-gradient(135deg,#0e1733 0%,#1e2a4d 100%)", "emoji": "🧱", "font": "system-ui"},

    # Rock / alt / metal
    "rock":                {"accent": "#FF3B3B", "gradient": "linear-gradient(135deg,#3f3f3f 0%,#0f0f0f 100%)", "emoji": "🎸", "font": "system-ui"},
    "alternative rock":    {"accent": "#FF9955", "gradient": "linear-gradient(135deg,#4a3f3f 0%,#1d1515 100%)", "emoji": "🌀", "font": "system-ui"},
    "indie rock":          {"accent": "#7BC67B", "gradient": "linear-gradient(135deg,#203a25 0%,#152017 100%)", "emoji": "🌲", "font": "system-ui"},
    "garage rock":         {"accent": "#E84A5F", "gradient": "linear-gradient(135deg,#5a2830 0%,#2f151a 100%)", "emoji": "🛠️", "font": "system-ui"},
    "psychedelic rock":    {"accent": "#C81D77", "gradient": "linear-gradient(135deg,#3a0130 0%,#150012 100%)", "emoji": "🌈", "font": "system-ui"},
    "shoegaze":            {"accent": "#7E9CD8", "gradient": "linear-gradient(135deg,#192538 0%,#0d1421 100%)", "emoji": "🌀", "font": "system-ui"},
    "math rock":           {"accent": "#55C2FF", "gradient": "linear-gradient(135deg,#0b1d33 0%,#142a4d 100%)", "emoji": "📐", "font": "system-ui"},
    "post rock":           {"accent": "#8AA2A9", "gradient": "linear-gradient(135deg,#1f2628 0%,#121617 100%)", "emoji": "🌌", "font": "system-ui"},
    "punk":                {"accent": "#FF3564", "gradient": "linear-gradient(135deg,#33000b 0%,#0f0003 100%)", "emoji": "🧷", "font": "system-ui"},
    "pop punk":            {"accent": "#FF7FB0", "gradient": "linear-gradient(135deg,#380c1f 0%,#12060a 100%)", "emoji": "🛼", "font": "system-ui"},
    "post punk":           {"accent": "#8E8E8E", "gradient": "linear-gradient(135deg,#1f1f1f 0%,#0e0e0e 100%)", "emoji": "🖤", "font": "system-ui"},
    "emo":                 {"accent": "#B084EF", "gradient": "linear-gradient(135deg,#2f2341 0%,#1a1326 100%)", "emoji": "🖤", "font": "system-ui"},
    "metal":               {"accent": "#9FA7B3", "gradient": "linear-gradient(135deg,#2a2d33 0%,#17181b 100%)", "emoji": "🪙", "font": "system-ui"},
    "heavy metal":         {"accent": "#A0A0A0", "gradient": "linear-gradient(135deg,#3a3a3a 0%,#181818 100%)", "emoji": "⚒️", "font": "system-ui"},
    "black metal":         {"accent": "#AAAAAA", "gradient": "linear-gradient(135deg,#0a0a0a 0%,#000000 100%)", "emoji": "🕯️", "font": "system-ui"},
    "death metal":         {"accent": "#A63A3A", "gradient": "linear-gradient(135deg,#2a0c0c 0%,#160707 100%)", "emoji": "💀", "font": "system-ui"},
    "progressive metal":   {"accent": "#4E86D6", "gradient": "linear-gradient(135deg,#152a4a 0%,#0b1729 100%)", "emoji": "🧭", "font": "system-ui"},
    "nu metal":            {"accent": "#CE6C6C", "gradient": "linear-gradient(135deg,#342020 0%,#1b1111 100%)", "emoji": "🔩", "font": "system-ui"},
    "djent":               {"accent": "#7E7E7E", "gradient": "linear-gradient(135deg,#2d2d2d 0%,#171717 100%)", "emoji": "🧱", "font": "system-ui"},

    # Electronic & dance
    "electronic":          {"accent": "#55C2FF", "gradient": "linear-gradient(135deg,#0b1d33 0%,#142a4d 100%)", "emoji": "⚡", "font": "system-ui"},
    "edm":                 {"accent": "#50E3C2", "gradient": "linear-gradient(135deg,#1b2a2f 0%,#0e1619 100%)", "emoji": "🎧", "font": "system-ui"},
    "house":               {"accent": "#FF9E2C", "gradient": "linear-gradient(135deg,#2b1f0f 0%,#1a1208 100%)", "emoji": "🏠", "font": "system-ui"},
    "deep house":          {"accent": "#F39C12", "gradient": "linear-gradient(135deg,#131d1d 0%,#0a1111 100%)", "emoji": "🌊", "font": "system-ui"},
    "progressive house":   {"accent": "#76D7C4", "gradient": "linear-gradient(135deg,#0f1f1b 0%,#091411 100%)", "emoji": "➡️", "font": "system-ui"},
    "tech house":          {"accent": "#E67E22", "gradient": "linear-gradient(135deg,#1a1a1a 0%,#0f0f0f 100%)", "emoji": "🛠️", "font": "system-ui"},
    "electro house":       {"accent": "#FF6F00", "gradient": "linear-gradient(135deg,#251a0a 0%,#120d06 100%)", "emoji": "⚡", "font": "system-ui"},
    "future house":        {"accent": "#7FDBFF", "gradient": "linear-gradient(135deg,#0a2030 0%,#071520 100%)", "emoji": "🔮", "font": "system-ui"},
    "techno":              {"accent": "#A3A3A3", "gradient": "linear-gradient(135deg,#0c0c0c 0%,#000000 100%)", "emoji": "🧪", "font": "system-ui"},
    "minimal techno":      {"accent": "#BEBEBE", "gradient": "linear-gradient(135deg,#161616 0%,#080808 100%)", "emoji": "➖", "font": "system-ui"},
    "trance":              {"accent": "#A66BFF", "gradient": "linear-gradient(135deg,#1d0f2d 0%,#0f0716 100%)", "emoji": "🌀", "font": "system-ui"},
    "psytrance":           {"accent": "#C54CFD", "gradient": "linear-gradient(135deg,#280f33 0%,#14071a 100%)", "emoji": "🧠", "font": "system-ui"},
    "drum and bass":       {"accent": "#00C9A7", "gradient": "linear-gradient(135deg,#0c1f1f 0%,#071414 100%)", "emoji": "🥁", "font": "system-ui"},
    "dubstep":             {"accent": "#7D5FFF", "gradient": "linear-gradient(135deg,#16172b 0%,#0b0c16 100%)", "emoji": "🧨", "font": "system-ui"},
    "future bass":         {"accent": "#00E5FF", "gradient": "linear-gradient(135deg,#0a1f2a 0%,#07151d 100%)", "emoji": "🫧", "font": "system-ui"},
    "ambient":             {"accent": "#9E7AFF", "gradient": "linear-gradient(135deg,#2e1a47 0%,#241a3a 100%)", "emoji": "🌌", "font": "Georgia, serif"},
    "downtempo":           {"accent": "#84A9AC", "gradient": "linear-gradient(135deg,#1b2e30 0%,#101b1d 100%)", "emoji": "🫖", "font": "system-ui"},
    "idm":                 {"accent": "#B39DDB", "gradient": "linear-gradient(135deg,#1f2433 0%,#131824 100%)", "emoji": "🧩", "font": "system-ui"},
    "lo-fi":               {"accent": "#B8C1EC", "gradient": "linear-gradient(135deg,#2a2f45 0%,#161a24 100%)", "emoji": "📻", "font": "system-ui"},
    "synthwave":           {"accent": "#FF6C9A", "gradient": "linear-gradient(135deg,#27023f 0%,#10001e 100%)", "emoji": "🌇", "font": "system-ui"},
    "vaporwave":           {"accent": "#9DF0FF", "gradient": "linear-gradient(135deg,#103548 0%,#081c25 100%)", "emoji": "🗿", "font": "system-ui"},
    "chiptune":            {"accent": "#00FF7F", "gradient": "linear-gradient(135deg,#1a3321 0%,#0d1a12 100%)", "emoji": "🎮", "font": "system-ui"},

    # R&B / soul / funk
    "r&b":                 {"accent": "#A977D8", "gradient": "linear-gradient(135deg,#2a1c3d 0%,#171025 100%)", "emoji": "💜", "font": "system-ui"},
    "neo soul":            {"accent": "#9C6ADE", "gradient": "linear-gradient(135deg,#261a3b 0%,#140c21 100%)", "emoji": "🪩", "font": "system-ui"},
    "soul":                {"accent": "#D19275", "gradient": "linear-gradient(135deg,#3a221b 0%,#1c100c 100%)", "emoji": "🧡", "font": "system-ui"},
    "funk":                {"accent": "#F7B32B", "gradient": "linear-gradient(135deg,#3a2a0b 0%,#1c1506 100%)", "emoji": "🕺", "font": "system-ui"},

    # Jazz / Blues
    "jazz":                {"accent": "#9E7AFF", "gradient": "linear-gradient(135deg,#2e1a47 0%,#241a3a 100%)", "emoji": "🎷", "font": "Georgia, serif"},
    "bebop":               {"accent": "#8F7EE7", "gradient": "linear-gradient(135deg,#231a3c 0%,#120d21 100%)", "emoji": "🎺", "font": "Georgia, serif"},
    "swing":               {"accent": "#FFD966", "gradient": "linear-gradient(135deg,#3a2f0c 0%,#1c1606 100%)", "emoji": "🕴️", "font": "Georgia, serif"},
    "bossa nova":          {"accent": "#6CD4FF", "gradient": "linear-gradient(135deg,#153241 0%,#0c1e27 100%)", "emoji": "🌴", "font": "Georgia, serif"},
    "blues":               {"accent": "#5AA9E6", "gradient": "linear-gradient(135deg,#0e2030 0%,#07151d 100%)", "emoji": "🎸", "font": "Georgia, serif"},

    # Latin
    "latin":               {"accent": "#FF6B6B", "gradient": "linear-gradient(135deg,#3a0f0f 0%,#1d0808 100%)", "emoji": "🌶️", "font": "system-ui"},
    "reggaeton":           {"accent": "#FFC300", "gradient": "linear-gradient(135deg,#2a2307 0%,#151103 100%)", "emoji": "💃", "font": "system-ui"},
    "salsa":               {"accent": "#F94144", "gradient": "linear-gradient(135deg,#3a0e0f 0%,#1d0708 100%)", "emoji": "🫑", "font": "system-ui"},
    "bachata":             {"accent": "#F3722C", "gradient": "linear-gradient(135deg,#36180c 0%,#1b0c06 100%)", "emoji": "💃", "font": "system-ui"},
    "cumbia":              {"accent": "#90BE6D", "gradient": "linear-gradient(135deg,#24331e 0%,#141c10 100%)", "emoji": "🪘", "font": "system-ui"},
    "latin pop":           {"accent": "#FF8FAB", "gradient": "linear-gradient(135deg,#3a2430 0%,#1d1218 100%)", "emoji": "🌺", "font": "system-ui"},

    # Reggae / ska / dancehall
    "reggae":              {"accent": "#2ECC71", "gradient": "linear-gradient(135deg,#0b2a17 0%,#07160c 100%)", "emoji": "🟩🟨🟥", "font": "system-ui"},
    "dancehall":           {"accent": "#FFD31A", "gradient": "linear-gradient(135deg,#2a2507 0%,#151203 100%)", "emoji": "🏝️", "font": "system-ui"},
    "ska":                 {"accent": "#000000", "gradient": "linear-gradient(135deg,#ffffff 0%,#e7e7e7 100%)", "emoji": "🏁", "font": "system-ui"},
    "ska punk":            {"accent": "#FF4D6D", "gradient": "linear-gradient(135deg,#3a0f16 0%,#1d080b 100%)", "emoji": "🏁🧷", "font": "system-ui"},

    # African / global
    "afrobeat":            {"accent": "#FF8C00", "gradient": "linear-gradient(135deg,#2b1f0f 0%,#1a1208 100%)", "emoji": "🪘", "font": "system-ui"},
    "amapiano":            {"accent": "#00B894", "gradient": "linear-gradient(135deg,#0e2a22 0%,#081815 100%)", "emoji": "🎹", "font": "system-ui"},
    "world":               {"accent": "#6C5CE7", "gradient": "linear-gradient(135deg,#231f3c 0%,#13112a 100%)", "emoji": "🌍", "font": "system-ui"},

    # Country / folk / singer-songwriter
    "country":             {"accent": "#E39C5A", "gradient": "linear-gradient(135deg,#f2dcc1 0%,#e3c199 100%)", "emoji": "🤠", "font": "system-ui"},
    "americana":           {"accent": "#C49A6C", "gradient": "linear-gradient(135deg,#352a1f 0%,#1c1611 100%)", "emoji": "🪕", "font": "system-ui"},
    "bluegrass":           {"accent": "#8ECae6", "gradient": "linear-gradient(135deg,#1b2e45 0%,#0f1a27 100%)", "emoji": "🎻", "font": "system-ui"},
    "folk":                {"accent": "#9CCC65", "gradient": "linear-gradient(135deg,#20301a 0%,#131b10 100%)", "emoji": "🍂", "font": "system-ui"},
    "singer-songwriter":   {"accent": "#A1887F", "gradient": "linear-gradient(135deg,#2e2623 0%,#181412 100%)", "emoji": "✍️", "font": "system-ui"},

    # Classical / soundtrack
    "classical":           {"accent": "#D3C4A4", "gradient": "linear-gradient(135deg,#f7f3e9 0%,#e6dcc7 100%)", "emoji": "🎼", "font": "Georgia, serif"},
    "baroque":             {"accent": "#C1A16B", "gradient": "linear-gradient(135deg,#3a2f1e 0%,#1d180f 100%)", "emoji": "🎻", "font": "Georgia, serif"},
    "romantic era":        {"accent": "#B28B84", "gradient": "linear-gradient(135deg,#32201d 0%,#1a110f 100%)", "emoji": "❤️", "font": "Georgia, serif"},
    "opera":               {"accent": "#AA6C39", "gradient": "linear-gradient(135deg,#301f14 0%,#180f0a 100%)", "emoji": "🎭", "font": "Georgia, serif"},
    "choral":              {"accent": "#C0B283", "gradient": "linear-gradient(135deg,#2f2b1d 0%,#17150f 100%)", "emoji": "👥", "font": "Georgia, serif"},
    "soundtrack":          {"accent": "#8FBC8F", "gradient": "linear-gradient(135deg,#1f2f1f 0%,#111b11 100%)", "emoji": "🎬", "font": "system-ui"},

    # Misc
    "gospel":              {"accent": "#FFD166", "gradient": "linear-gradient(135deg,#3a2f0c 0%,#1c1606 100%)", "emoji": "🙏", "font": "system-ui"},
    "christian":           {"accent": "#B2DFDB", "gradient": "linear-gradient(135deg,#1f2e2d 0%,#11201f 100%)", "emoji": "✝️", "font": "system-ui"},
    "worship":             {"accent": "#E0F7FA", "gradient": "linear-gradient(135deg,#2a3a3d 0%,#152022 100%)", "emoji": "🕊️", "font": "system-ui"},
    "holiday":             {"accent": "#2ECC71", "gradient": "linear-gradient(135deg,#153116 0%,#0d1d0e 100%)", "emoji": "🎄", "font": "system-ui"},
    "video game":          {"accent": "#00FF7F", "gradient": "linear-gradient(135deg,#0f1f12 0%,#08120b 100%)", "emoji": "🕹️", "font": "system-ui"},
}

def patch_genre_themes():
    """Merge GENRE_THEMES_PATCH into global GENRE_THEMES, creating it if absent."""
    global GENRE_THEMES
    if "GENRE_THEMES" not in globals() or not isinstance(globals().get("GENRE_THEMES"), dict):
        GENRE_THEMES = {}
    # Do not clobber existing keys; only add missing ones
    for k, v in GENRE_THEMES_PATCH.items():
        if k not in GENRE_THEMES:
            GENRE_THEMES[k] = dict(v)  # shallow copy
    return GENRE_THEMES

def resolve_genre_key(g: str) -> str:
    """Return the primary theme key for a raw genre/subgenre string."""
    g0 = _norm(g)
    # direct hit
    if g0 in GENRE_THEMES:
        return g0
    # alias resolution
    if g0 in GENRE_ALIASES:
        alias = GENRE_ALIASES[g0]
        if alias in GENRE_THEMES:
            return alias
    # try loosening (remove spaces)
    g1 = g0.replace(" ", "")
    if g1 in GENRE_ALIASES:
        alias = GENRE_ALIASES[g1]
        if alias in GENRE_THEMES:
            return alias
    # fallback: map subgenre to a plausible parent by keywords
    parents = [
        ("metal", "metal"), ("rock", "rock"), ("pop", "pop"), ("hip", "hip hop"), ("hop", "hip hop"),
        ("house", "house"), ("techno", "techno"), ("trance", "trance"), ("bass", "future bass"),
        ("ambient", "ambient"), ("lofi", "lo-fi"), ("jazz", "jazz"), ("blues", "blues"),
        ("latin", "latin"), ("reggae", "reggae"), ("country", "country"), ("folk", "folk"),
        ("classical", "classical"), ("soundtrack", "soundtrack"), ("opera", "opera"),
    ]
    for kw, parent in parents:
        if kw in g0 and parent in GENRE_THEMES:
            return parent
    # last resort
    return "pop" if "pop" in GENRE_THEMES else next(iter(GENRE_THEMES.keys()))

def apply_theme(theme_key: str):
    """Apply the theme to the page (background gradient + accent CSS)."""
    if st is None:
        return  # streamlit not available
    th = GENRE_THEMES.get(theme_key, {})
    gradient = th.get("gradient", "linear-gradient(135deg,#1f1f1f 0%,#0f0f0f 100%)")
    accent = th.get("accent", "#7bd3ff")
    font = th.get("font", "system-ui")
    emoji = th.get("emoji", "🎵")

    css = f"""
    <style>
      :root {{
        --accent: {accent};
      }}
      html, body, [data-testid="stAppViewContainer"] {{
        background: {gradient} !important;
        color: #f6f6f6;
        font-family: {font}, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, "Helvetica Neue", sans-serif;
      }}
      h1, h2, h3, h4, h5, h6 {{
        color: #ffffff;
      }}
      .stButton button {{
        background: var(--accent) !important;
        color: #0f0f0f !important;
        border: none !important;
      }}
      .stSelectbox div[role="combobox"], .stTextInput input {{
        border: 1px solid var(--accent) !important;
      }}
      a, .stMarkdown a {{
        color: var(--accent) !important;
        text-decoration-color: var(--accent) !important;
      }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
    st.caption(f"{emoji} Theme: **{theme_key.title()}**")

def apply_theme_for_genres(genres):
    """Pick the first matching theme from a list of genre strings and apply it."""
    if not genres:
        return
    for g in genres:
        key = resolve_genre_key(g)
        if key:
            apply_theme(key)
            return

def _try_auto_apply():
    """Try to auto-apply based on common variable names your app might already define."""
    patch_genre_themes()
    candidates = []
    for name in ("DOMINANT_GENRES", "dominant_genres", "user_genres", "genres", "detected_genres"):
        if name in globals():
            val = globals()[name]
            if isinstance(val, (list, tuple, set)):
                candidates.extend(list(val))
            elif isinstance(val, dict):
                candidates.extend(list(val.keys()))
    # de-duplicate while preserving order
    seen = set()
    ordered = []
    for g in candidates:
        gn = _norm(g)
        if gn and gn not in seen:
            ordered.append(gn)
            seen.add(gn)
    if ordered:
        apply_theme_for_genres(ordered)

# ---- Run the auto-apply when this patch is imported/executed at the end of app.py ----
_try_auto_apply()

# Optional: expose a quick callable you can use anywhere:
# apply_theme_for_genres(["indie pop", "alt rock", "trap"])


# =========================
# Comfort Palette Patch (low-contrast, eye-friendly)
# =========================
try:
    import streamlit as st
except Exception:
    st = None

def _norm(s: str) -> str:
    return (s or "").strip().lower().replace("_", " ").replace("-", " ").replace("/", " ").replace("&", " and ")

GENRE_ALIASES = {
    "hip hop": "hip hop", "hiphop": "hip hop", "hip-hop": "hip hop",
    "lofi": "lo-fi", "j-pop": "j-pop", "k-pop": "k-pop",
    "alt rock": "alternative rock", "indie pop": "indie pop",
    "dnb": "drum and bass"
}

# ---- Muted, comfortable themes (accents ~mid-saturation; gentle gradients) ----
GENRE_THEMES_PATCH = {
    # Pop family
    "pop":                {"accent": "#c4739a", "gradient": "linear-gradient(135deg,#2a2a2a 0%,#242424 100%)", "emoji": "✨", "font": "system-ui"},
    "indie pop":          {"accent": "#7fa88a", "gradient": "linear-gradient(135deg,#27302a 0%,#232a25 100%)", "emoji": "🌿", "font": "system-ui"},
    "synthpop":           {"accent": "#9c86c9", "gradient": "linear-gradient(135deg,#2b2a33 0%,#252432 100%)", "emoji": "🎛️", "font": "system-ui"},
    "electropop":         {"accent": "#8c89b8", "gradient": "linear-gradient(135deg,#2b2c33 0%,#252530 100%)", "emoji": "⚡", "font": "system-ui"},
    "dance pop":          {"accent": "#c08b72", "gradient": "linear-gradient(135deg,#2b2b2b 0%,#252525 100%)", "emoji": "💃", "font": "system-ui"},
    "hyperpop":           {"accent": "#b67aa5", "gradient": "linear-gradient(135deg,#2b2630 0%,#241f29 100%)", "emoji": "🫧", "font": "system-ui"},
    "j-pop":              {"accent": "#c38ba0", "gradient": "linear-gradient(135deg,#2a2a31 0%,#24242c 100%)", "emoji": "🍡", "font": "system-ui"},
    "k-pop":              {"accent": "#87a8bf", "gradient": "linear-gradient(135deg,#283035 0%,#22292e 100%)", "emoji": "🎀", "font": "system-ui"},

    # Hip hop family
    "hip hop":            {"accent": "#c59a56", "gradient": "linear-gradient(135deg,#232323 0%,#1d1d1d 100%)", "emoji": "🎤", "font": "system-ui"},
    "trap":               {"accent": "#b7776d", "gradient": "linear-gradient(135deg,#242222 0%,#1e1c1c 100%)", "emoji": "🪤", "font": "system-ui"},
    "drill":              {"accent": "#7b8fb2", "gradient": "linear-gradient(135deg,#20232a 0%,#1a1d23 100%)", "emoji": "🧱", "font": "system-ui"},

    # Rock / alt / metal
    "rock":               {"accent": "#b96565", "gradient": "linear-gradient(135deg,#2c2c2c 0%,#242424 100%)", "emoji": "🎸", "font": "system-ui"},
    "alternative rock":   {"accent": "#b68c6e", "gradient": "linear-gradient(135deg,#2c2926 0%,#25231f 100%)", "emoji": "🌀", "font": "system-ui"},
    "indie rock":         {"accent": "#7ba083", "gradient": "linear-gradient(135deg,#273129 0%,#222a24 100%)", "emoji": "🌲", "font": "system-ui"},
    "shoegaze":           {"accent": "#8897b3", "gradient": "linear-gradient(135deg,#262a33 0%,#20242b 100%)", "emoji": "🌀", "font": "system-ui"},
    "emo":                {"accent": "#9a87bd", "gradient": "linear-gradient(135deg,#292633 0%,#221f2c 100%)", "emoji": "🖤", "font": "system-ui"},
    "metal":              {"accent": "#939aa3", "gradient": "linear-gradient(135deg,#2b2d31 0%,#24262a 100%)", "emoji": "🪙", "font": "system-ui"},
    "heavy metal":        {"accent": "#9b9b9b", "gradient": "linear-gradient(135deg,#2f2f2f 0%,#262626 100%)", "emoji": "⚒️", "font": "system-ui"},

    # Electronic & dance
    "electronic":         {"accent": "#7ba7c6", "gradient": "linear-gradient(135deg,#23303a 0%,#1e2a34 100%)", "emoji": "⚡", "font": "system-ui"},
    "edm":                {"accent": "#77b6a8", "gradient": "linear-gradient(135deg,#223033 0%,#1d292b 100%)", "emoji": "🎧", "font": "system-ui"},
    "house":              {"accent": "#c4925f", "gradient": "linear-gradient(135deg,#2a2622 0%,#24211e 100%)", "emoji": "🏠", "font": "system-ui"},
    "deep house":         {"accent": "#b78951", "gradient": "linear-gradient(135deg,#222422 0%,#1c1e1c 100%)", "emoji": "🌊", "font": "system-ui"},
    "techno":             {"accent": "#9a9a9a", "gradient": "linear-gradient(135deg,#1f1f1f 0%,#181818 100%)", "emoji": "🧪", "font": "system-ui"},
    "trance":             {"accent": "#9a87c6", "gradient": "linear-gradient(135deg,#241f2f 0%,#1e1928 100%)", "emoji": "🌀", "font": "system-ui"},
    "drum and bass":      {"accent": "#74a79b", "gradient": "linear-gradient(135deg,#20302e 0%,#1b2523 100%)", "emoji": "🥁", "font": "system-ui"},
    "dubstep":            {"accent": "#8c7fb8", "gradient": "linear-gradient(135deg,#232535 0%,#1d1f2c 100%)", "emoji": "🧨", "font": "system-ui"},
    "ambient":            {"accent": "#8a7cc0", "gradient": "linear-gradient(135deg,#262039 0%,#201a31 100%)", "emoji": "🌌", "font": "Georgia, serif"},
    "lo-fi":              {"accent": "#a6aec6", "gradient": "linear-gradient(135deg,#2b2f3f 0%,#242838 100%)", "emoji": "📻", "font": "system-ui"},

    # R&B / soul / funk
    "r&b":                {"accent": "#a489c3", "gradient": "linear-gradient(135deg,#2a2335 0%,#241f2f 100%)", "emoji": "💜", "font": "system-ui"},
    "neo soul":           {"accent": "#9a82bf", "gradient": "linear-gradient(135deg,#292233 0%,#221d2b 100%)", "emoji": "🪩", "font": "system-ui"},
    "soul":               {"accent": "#b8846b", "gradient": "linear-gradient(135deg,#2f241f 0%,#272019 100%)", "emoji": "🧡", "font": "system-ui"},
    "funk":               {"accent": "#c39a4a", "gradient": "linear-gradient(135deg,#2f2a1a 0%,#262313 100%)", "emoji": "🕺", "font": "system-ui"},

    # Jazz / Blues
    "jazz":               {"accent": "#8b79be", "gradient": "linear-gradient(135deg,#241d36 0%,#1e182e 100%)", "emoji": "🎷", "font": "Georgia, serif"},
    "blues":              {"accent": "#7397c2", "gradient": "linear-gradient(135deg,#1d2a38 0%,#17212d 100%)", "emoji": "🎸", "font": "Georgia, serif"},

    # Latin / reggae
    "latin":              {"accent": "#b36d6d", "gradient": "linear-gradient(135deg,#2d2222 0%,#251b1b 100%)", "emoji": "🌶️", "font": "system-ui"},
    "reggaeton":          {"accent": "#b89d4f", "gradient": "linear-gradient(135deg,#2c2618 0%,#252114 100%)", "emoji": "💃", "font": "system-ui"},
    "reggae":             {"accent": "#73a77e", "gradient": "linear-gradient(135deg,#1f2a22 0%,#19221c 100%)", "emoji": "🟩🟨🟥", "font": "system-ui"},

    # Global / folk / country
    "afrobeat":           {"accent": "#bd8649", "gradient": "linear-gradient(135deg,#2a251c 0%,#241f18 100%)", "emoji": "🪘", "font": "system-ui"},
    "country":            {"accent": "#c29369", "gradient": "linear-gradient(135deg,#2f2a25 0%,#27231f 100%)", "emoji": "🤠", "font": "system-ui"},
    "folk":               {"accent": "#8aa578", "gradient": "linear-gradient(135deg,#21281f 0%,#1b2219 100%)", "emoji": "🍂", "font": "system-ui"},

    # Classical / soundtrack
    "classical":          {"accent": "#b8ac8a", "gradient": "linear-gradient(135deg,#2f2c26 0%,#27241f 100%)", "emoji": "🎼", "font": "Georgia, serif"},
    "soundtrack":         {"accent": "#8ba696", "gradient": "linear-gradient(135deg,#212b26 0%,#1b2320 100%)", "emoji": "🎬", "font": "system-ui"},
}

def patch_genre_themes():
    global GENRE_THEMES
    if "GENRE_THEMES" not in globals() or not isinstance(globals().get("GENRE_THEMES"), dict):
        GENRE_THEMES = {}
    for k, v in GENRE_THEMES_PATCH.items():
        GENRE_THEMES.setdefault(k, dict(v))
    return GENRE_THEMES

def resolve_genre_key(g: str) -> str:
    g0 = _norm(g)
    if g0 in GENRE_THEMES: return g0
    if g0 in GENRE_ALIASES and GENRE_ALIASES[g0] in GENRE_THEMES:
        return GENRE_ALIASES[g0]
    # simple parent inference (non-neon, muted defaults)
    parents = [("metal","metal"),("rock","rock"),("pop","pop"),("hip","hip hop"),
               ("house","house"),("techno","techno"),("trance","trance"),
               ("ambient","ambient"),("lo fi","lo-fi"),("jazz","jazz"),
               ("blues","blues"),("latin","latin"),("reggae","reggae"),
               ("country","country"),("folk","folk"),("classical","classical"),
               ("soundtrack","soundtrack")]
    for kw, parent in parents:
        if kw in g0 and parent in GENRE_THEMES:
            return parent
    return "pop" if "pop" in GENRE_THEMES else next(iter(GENRE_THEMES.keys()))

def apply_theme(theme_key: str):
    if st is None:
        return
    th = GENRE_THEMES.get(theme_key, {})
    gradient = th.get("gradient", "linear-gradient(135deg,#262626 0%,#1f1f1f 100%)")
    accent = th.get("accent", "#8fa3b8")
    font = th.get("font", "system-ui")
    emoji = th.get("emoji", "🎵")

    # Softer text colors
    base_text = "#eaeaea"
    link_text = accent
    code = f"""
    <style>
      :root {{ --accent: {accent}; --text: {base_text}; }}
      html, body, [data-testid="stAppViewContainer"] {{
        background: {gradient} !important;
        color: var(--text);
        font-family: {font}, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, "Helvetica Neue", sans-serif;
      }}
      h1, h2, h3, h4, h5, h6 {{ color: var(--text); }}
      .stButton button {{
        background: var(--accent) !important;
        color: #1a1a1a !important; border: none !important;
      }}
      .stSelectbox div[role="combobox"], .stTextInput input {{
        border: 1px solid rgba(255,255,255,0.12) !important;
        background-color: rgba(255,255,255,0.02) !important;
        color: var(--text) !important;
      }}
      a, .stMarkdown a {{ color: {link_text} !important; text-decoration-color: {link_text} !important; }}
    </style>
    """
    st.markdown(code, unsafe_allow_html=True)
    st.caption(f"{emoji} Theme: **{theme_key.title()}**")

def apply_theme_for_genres(genres):
    if not genres: return
    for g in genres:
        apply_theme(resolve_genre_key(g))
        return

def _try_auto_apply():
    patch_genre_themes()
    # Look for lists your app might already define
    names = ("DOMINANT_GENRES", "dominant_genres", "user_genres", "genres", "detected_genres")
    found = []
    for n in names:
        if n in globals():
            val = globals()[n]
            if isinstance(val, (list, tuple, set)):
                found += list(val)
            elif isinstance(val, dict):
                found += list(val.keys())
    # de-dup
    seen, ordered = set(), []
    for g in found:
        gn = _norm(g)
        if gn and gn not in seen:
            ordered.append(gn); seen.add(gn)
    if ordered:
        apply_theme_for_genres(ordered)

_try_auto_apply()



