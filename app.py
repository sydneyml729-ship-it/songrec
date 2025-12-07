
# app.py — single-file Streamlit app (Spotify-compliant)
# Adds:
# - "Songs from your genres (not your input artists)" tracks category.
# - 🔁 Regenerate button.
# - Artist categories without popularity filtering: "Artists you may know" (pop >= 60) & "Discover" (pop < 60).
# Keeps:
# - Fair interleaving across ALL inputs.
# - Auto genre-driven background (no manual personalization).
# - Standard mode mixes favorites’ top tracks + related artists’ top tracks (varied).
# Endpoints: Search, Artist, Artist Top Tracks (requires market), Related Artists (Client Credentials).

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
    """Use st.link_button if available; otherwise render a Markdown link."""
    try:
        st.link_button(label, url)
    except Exception:
        if url:
            st.markdown(f"{label}")

# =========================
#  Genre Themes (gradient & optional image)
# =========================
GENRE_THEMES = {
    "pop":        {"accent": "#FF62B3", "gradient": "linear-gradient(135deg,#ff9ac6 0%,#ffd1e0 100%)",
                   "image": "assets/bg_pop.jpg",        "emoji": "✨", "font": "system-ui"},
    "rock":       {"accent": "#FF3B3B", "gradient": "linear-gradient(135deg,#3f3f3f 0%,#0f0f0f 100%)",
                   "image": "assets/bg_rock.jpg",       "emoji": "🎸", "font": "system-ui"},
    "hip hop":    {"accent": "#FDBA3B", "gradient": "linear-gradient(135deg,#0e0e0e 0%,#1a1a1a 100%)",
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
    """Round-robin interleave: [a1,a2], [b1,b2,b3] -> a1,b1,a2,b2,b3."""
    out: List[Tuple[str, str]] = []
    max_len = max((len(lst) for lst in lists), default=0)
    for i in range(max_len):
        for lst in lists:
            if i < len(lst):
                out.append(lst[i])
    return out

def build_css_theme(primary: dict, secondary: dict | None = None) -> dict:
    """Build CSS string for Streamlit app based on genre theme(s)."""
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

def pick_theme_by_genres(genres: List[str]) -> dict:
    """Choose a primary theme by frequency; blend with second-most if present."""
    counts: Dict[str, int] = {}
    for g in genres:
        g_norm = (g or "").lower()
        if "hip hop" in g_norm or "hip-hop" in g_norm or "rap" in g_norm:
            g_norm = "hip hop"
        elif "k-pop" in g_norm or "kpop" in g_norm:
            g_norm = "k-pop"
        if g_norm in GENRE_THEMES:
            counts[g_norm] = counts.get(g_norm, 0) + 1
    top = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    if not top:
        base = GENRE_THEMES["__default__"]
        return build_css_theme(base)
    primary = GENRE_THEMES.get(top[0][0], GENRE_THEMES["__default__"])
    if len(top) >= 2:
        secondary = GENRE_THEMES.get(top[1][0], GENRE_THEMES["__default__"])
        return build_css_theme(primary, secondary)
    return build_css_theme(primary)

# =========================
#  Spotify Client (Client Credentials; allowed endpoints only)
# =========================
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"

class SpotifyClient:
    """
    Spotify Web API client (Client Credentials flow; non-user endpoints only).
    Endpoints used:
      - GET /v1/search
      - GET /v1/artists/{id}
      - GET /v1/artists/{id}/top-tracks (requires `market`)
      - GET /v1/artists/{id}/related-artists
    """
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
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", "2"))
                time.sleep(retry_after)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            if e.code == 401:
                self._fetch_access_token()
                req2 = urllib.request.Request(
                    url, headers={"Authorization": f"Bearer {self._access_token}"}, method="GET"
                )
                with urllib.request.urlopen(req2, timeout=20) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            raise

    # Search helpers
    def search_track(self, title: str, artist: str, limit: int = 3) -> List[Dict]:
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
#  Fuzzy helpers
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
    """Robust resolution: (Title+Artist) → direct artist search → track-only fallback."""
    try:
        r = resolve_favorite_to_artist(sp, title, artist, limit=10, accept_threshold=72.0)
        if r: return r
        # Direct artist search by name
        if artist:
            items = sp.search_artist_by_name(artist, limit=3)
            if items:
                a = items[0]
                aid = a.get("id", "")
                adata = sp.get_artist(aid) if aid else {}
                return (aid, adata.get("name", a.get("name","")), adata.get("genres", []) or [])
        # Track-only fallback to get primary artist
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
#  Recommendation logic (with regenerate support)
# =========================
def _stable_shuffle(items: List[Tuple[str, str]], salt: str) -> List[Tuple[str, str]]:
    """Deterministic shuffle by SHA-256 of salt (varies per day & inputs, stable within a day)."""
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
    regen_nonce: int = 0,  # vary suggestions when user clicks "Regenerate"
) -> List[Tuple[str, str]]:
    """
    STANDARD (varied) across ALL inputs:
    - Favorite artists' top tracks + up to 3 related artists' top tracks.
    - Interleave across ALL inputs, then stable-shuffle with a nonce.
    - Deduplicate; up to max_recs.
    """
    sp = SpotifyClient(client_id, client_secret, market=market or "US")
    favorites = [(t.strip(), a.strip()) for (t, a) in favorites if t and a]
    fav_keys = {(t.lower(), a.lower()) for (t, a) in favorites}

    # Resolve all favorites robustly
    artist_infos: List[Tuple[str, str, List[str]]] = []
    for (title, artist) in favorites:
        resolved = resolve_artist_robust(sp, title, artist)
        if resolved:
            aid, aname, a_genres = resolved
            if aid:
                artist_infos.append((aid, aname, a_genres))

    # If nothing resolved, genre backfill
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

    # Per-artist favorite top tracks
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

    # Per-artist related artists' top tracks (shuffled by nonce for variety)
    rng = random.Random(regen_nonce or 0)
    per_artist_related: List[List[Tuple[str, str]]] = []
    for (aid, _aname, _g) in artist_infos:
        lst: List[Tuple[str, str]] = []
        try:
            related = sp.get_related_artists(aid) or []
            rng.shuffle(related)  # vary which related artists we pick
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

    # Interleave across ALL inputs
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

    # Stable shuffle by date + market + inputs + nonce
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
    regen_nonce: int = 0,  # allow variety on regenerate
) -> Dict[str, List[Tuple[str, str]]]:
    """
    Returns buckets:
      - "Hidden gems from your favorite artists" (tracks; uses track_pop_max)
      - "Artists you may know" (pop >= 60) — no filtering, just labeling
      - "Discover" (pop < 60) — no filtering, just labeling
      - "Songs from your genres (not your input artists)" — tracks by genre-matched artists excluding inputs
      - "Rising stars in your genres" — informational
    """
    sp = SpotifyClient(client_id, client_secret, market=market or "US")
    favorites = [(t.strip(), a.strip()) for (t, a) in favorites if t and a]
    rng = random.Random(regen_nonce or 0)

    fav_keys = {(t.lower(), a.lower()) for (t, a) in favorites}
    fav_artist_names_lower = {a.lower() for (_, a) in favorites}

    # Resolve all favorites robustly
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
                # Track bucket still uses track_pop_max for "hidden gems"
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
    buckets["Hidden gems from your favorite artists"] = hidden_combined[:max(2, per_bucket)]

    # ---------- 2) Recommended artists: all popularity levels, labeled ----------
    def _artist_url(ar: Dict) -> str:
        return (ar.get("external_urls") or {}).get("spotify") or (f"https://open.spotify.com/artist/{ar.get('id','')}" if ar.get("id") else "")

    # Gather related artists across all favorites
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

    # If still thin, backfill from genre-similar (no pop filtering; just labeling later)
    if len(related_all) < min_artists:
        union_genres = {g for (_aid,_aname,gs) in fav_artist_infos for g in (gs or [])}
        if not union_genres:
            union_genres = {"indie","electronic","hip hop","pop","latin"}
        for g in list(union_genres)[:5]:
            try:
                items = sp.search_artists_by_genre(g, limit=20)
                rng.shuffle(items)
                for ar in items[:8]:
                    name = ar.get("name",""); pop = ar.get("popularity",50)
                    url = _artist_url(ar)
                    if name and url:
                        related_all.append((name, url, pop))
            except Exception:
                continue

    # Label into two categories (no filtering)
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
        if pop >= 60:
            may_know.append((name, url))
        else:
            discover.append((name, url))
    may_know = _dedupe(may_know)[:max(2, per_bucket)]
    discover = _dedupe(discover)[:max(2, per_bucket)]
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
            # Find artists by genre
            artists_by_genre = sp.search_artists_by_genre(genre, limit=30)
            rng.shuffle(artists_by_genre)
            for ar in artists_by_genre:
                aid = ar.get("id", "")
                aname = ar.get("name", "")
                if not aid or not aname:
                    continue
                # Exclude submitted favorites
                if aid in fav_artist_ids or (aname.lower() in fav_artist_names_lower):
                    continue
                # Fetch a few top tracks for this genre-matched artist
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
                        # Exclude exact favorites (title+artist)
                        key = (tname.strip().lower(), pa_name.strip().lower())
                        if key in fav_keys:
                            continue
                        lst.append((f"{tname} — {pa_name}", turl))
                        if len(lst) >= 8:  # keep each genre list modest
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

    # ---------- 4) Rising stars in your genres (informational) ----------
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
#  Sidebar / Inputs
# =========================
with st.sidebar:
    st.header("Settings")
    market = st.text_input("Market (country code)", value="US", help="e.g., US, GB, KR, JP")

    with st.expander("🎛️ Advanced controls", expanded=False):
        track_pop_max = st.slider("Max track popularity (hidden gems — tracks only)", 0, 100, 35, help="Lower = more niche for track picks")
        per_bucket = st.slider("Items per bucket", 1, 10, 5)
        min_artists = st.slider("Minimum artists per bucket (guaranteed)", 0, 5, 2)

# Collect favorites
col1, col2 = st.columns(2)
with col1:
    s1_title = st.text_input("Favorite #1 — Title", placeholder="e.g., Blinding Lights")
with col2:
    s1_artist = st.text_input("Favorite #1 — Artist", placeholder="e.g., The Weeknd")

col1, col2 = st.columns(2)
with col1:
    s2_title = st.text_input("Favorite #2 — Title", placeholder="e.g., Yellow")
with col2:
    s2_artist = st.text_input("Favorite #2 — Artist", placeholder="e.g., Coldplay")

col1, col2 = st.columns(2)
with col1:
    s3_title = st.text_input("Favorite #3 — Title", placeholder="e.g., Bad Guy")
with col2:
    s3_artist = st.text_input("Favorite #3 — Artist", placeholder="e.g., Billie Eilish")

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

def _collect_favorites_with_feedback() -> List[Tuple[str, str]]:
    rows = [
        ("Favorite #1", s1_title.strip(), s1_artist.strip()),
        ("Favorite #2", s2_title.strip(), s2_artist.strip()),
        ("Favorite #3", s3_title.strip(), s3_artist.strip()),
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

    favorites = _collect_favorites_with_feedback()
    if not favorites:
        st.warning("Please enter at least one valid Title + Artist pair.")
        st.stop()

    # Auto genre-driven background — based solely on inputs
    genres = collect_genres_for_favorites(CLIENT_ID, CLIENT_SECRET, market, favorites)
    theme = pick_theme_by_genres(genres)
    st.markdown(theme["css"], unsafe_allow_html=True)
    st.markdown(f"### {theme['emoji']} Personalized Interface (auto)")

    # Context badges (artists + genres)
    icons = theme["icons"]
    st.markdown(f"**{icons['artist']} Inputs:** "
                f"`{s1_artist or '—'}` · `{s2_artist or '—'}` · `{s3_artist or '—'}`")
    unique_genres = sorted(set([g.lower() for g in genres]))[:6] if genres else []
    if unique_genres:
        st.markdown("**🏷️ Detected genres:** " + " ".join(
            [f"<span class='badge'>{g}</span>" for g in unique_genres]
        ), unsafe_allow_html=True)
    else:
        st.markdown("**🏷️ Detected genres:** <span class='badge'>mixed/unknown</span>", unsafe_allow_html=True)

    # Tabs for modes
    tab_std, tab_niche = st.tabs([f"{theme['emoji']} Standard (varied)", "🌱 Niche"])

    # --- Standard (varied) ---
    with tab_std:
        with st.spinner("Fetching recommendations..."):
            recs = recommend_from_favorites(
                CLIENT_ID, CLIENT_SECRET, market, favorites, max_recs=3, regen_nonce=st.session_state["regen_nonce"]
            )
        st.subheader("Recommendations")
        if not recs:
            recs = [("Explore Spotify", "https://open.spotify.com/explore")]
        for i, (text, url) in enumerate(recs, start=1):
            st.write(f"**{i}. {text}**")
            if url:
                link_button("Open in Spotify", url)

    # --- Niche with artist + track categories ---
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
        st.subheader("Recommended artists")

        # Artists you may know
        st.markdown("#### Artists you may know")
        items = buckets.get("Artists you may know", [])
        if not items:
            items = [("Explore artists", "https://open.spotify.com/genre")]
        for text, url in items:
            st.write(f"- **{text}**")
            if url:
                link_button("Open in Spotify", url)

        # Discover
        st.markdown("#### Discover")
        items = buckets.get("Discover", [])
        if not items:
            items = [("Explore artists", "https://open.spotify.com/genre")]
        for text, url in items:
            st.write(f"- **{text}**")
            if url:
                link_button("Open in Spotify", url)

        st.divider()

        # Hidden gems from your favorite artists (tracks)
        st.markdown("#### Hidden gems from your favorite artists")
        items = buckets.get("Hidden gems from your favorite artists", [])
        if not items:
            items = [("Explore Spotify", "https://open.spotify.com/explore")]
        for text, url in items:
            st.write(f"- **{text}**")
            if url:
                link_button("Open in Spotify", url)

        st.divider()

        # NEW: Songs from your genres (not your input artists)
        st.markdown("#### Songs from your genres (not your input artists)")
        items = buckets.get("Songs from your genres (not your input artists)", [])
        if not items:
            items = [("Discover on Spotify", "https://open.spotify.com/explore")]
        for text, url in items:
            st.write(f"- **{text}**")
            if url:
                link_button("Open in Spotify", url)

        st.divider()

        # Rising stars (informational)
        st.markdown("#### Rising stars in your genres")
        items = buckets.get("Rising stars in your genres", [])
        if not items:
            items = [("Discover on Spotify", "https://open.spotify.com/explore")]
        for text, url in items:
            st.write(f"- **{text}**")
            if url:
                link_button("Open in Spotify", url)
        st.divider()
