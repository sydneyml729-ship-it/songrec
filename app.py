
# app.py — single-file Streamlit app (Spotify-compliant)
# Features: Standard & Niche recs; fair interleaving across ALL inputs; min-2 artists guarantee; genre-driven UI.

import os
import time
import json
import base64
import urllib.parse
import urllib.request
import urllib.error
import re
import unicodedata
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
    "pop": {"accent": "#FF62B3", "gradient": "linear-gradient(135deg,#ff9ac6 0%,#ffd1e0 100%)",
            "image": "assets/bg_pop.jpg", "emoji": "✨", "font": "system-ui"},
    "rock": {"accent": "#FF3B3B", "gradient": "linear-gradient(135deg,#3f3f3f 0%,#0f0f0f 100%)",
             "image": "assets/bg_rock.jpg", "emoji": "🎸", "font": "system-ui"},
    "hip hop": {"accent": "#FDBA3B", "gradient": "linear-gradient(135deg,#0e0e0e 0%,#1a1a1a 100%)",
                "image": "assets/bg_hiphop.jpg", "emoji": "🧢", "font": "system-ui"},
    "indie": {"accent": "#66D9A3", "gradient": "linear-gradient(135deg,#94e3bf 0%,#e8fff4 100%)",
              "image": "assets/bg_indie.jpg", "emoji": "🍃", "font": "system-ui"},
    "electronic": {"accent": "#55C2FF", "gradient": "linear-gradient(135deg,#0b1d33 0%,#142a4d 100%)",
                   "image": "assets/bg_electronic.jpg", "emoji": "⚡", "font": "system-ui"},
    "jazz": {"accent": "#9E7AFF", "gradient": "linear-gradient(135deg,#2e1a47 0%,#241a3a 100%)",
             "image": "assets/bg_jazz.jpg", "emoji": "🎷", "font": "Georgia, serif"},
    "classical": {"accent": "#D3C4A4", "gradient": "linear-gradient(135deg,#f7f3e9 0%,#e6dcc7 100%)",
                  "image": "assets/bg_classical.jpg", "emoji": "🎼", "font": "Georgia, serif"},
    "country": {"accent": "#E39C5A", "gradient": "linear-gradient(135deg,#f2dcc1 0%,#e3c199 100%)",
                "image": "assets/bg_country.jpg", "emoji": "🤠", "font": "system-ui"},
    "latin": {"accent": "#FF6F61", "gradient": "linear-gradient(135deg,#ffd4c6 0%,#ffc1b1 100%)",
              "image": "assets/bg_latin.jpg", "emoji": "💃", "font": "system-ui"},
    "k-pop": {"accent": "#7AE0FF", "gradient": "linear-gradient(135deg,#7ae0ff 0%,#c2f2ff 100%)",
              "image": "assets/bg_kpop.jpg", "emoji": "🌈", "font": "system-ui"},
    "metal": {"accent": "#A0A0A0", "gradient": "linear-gradient(135deg,#1a1a1a 0%,#2a2a2a 100%)",
              "image": "assets/bg_metal.jpg", "emoji": "🤘", "font": "system-ui"},
    "__default__": {"accent": "#1DB954", "gradient": "linear-gradient(135deg,#0b0b0b 0%,#141414 100%)",
                    "image": "assets/bg_default.jpg", "emoji": "🎵", "font": "system-ui"},
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
    image_url = primary.get("image", "")
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
    </style>
    """
    return {"css": css, "emoji": primary.get("emoji", "🎵"), "accent": accent}

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

# =========================
#  Recommendation logic
# =========================
def recommend_from_favorites(
    client_id: str,
    client_secret: str,
    market: str,
    favorites: List[Tuple[str, str]],
    max_recs: int = 3,
) -> List[Tuple[str, str]]:
    """
    Fair, interleaved Standard recommendations across ALL favorites:
    - Build a candidate list per resolved favorite artist (Top Tracks excluding exact favorites).
    - Interleave per-artist lists round-robin.
    - Deduplicate & pick up to max_recs (ensuring representation).
    """
    sp = SpotifyClient(client_id, client_secret, market=market or "US")
    favorites = [(t.strip(), a.strip()) for (t, a) in favorites if t and a]
    fav_keys = {(t.lower(), a.lower()) for (t, a) in favorites}

    # Resolve all favorites to artists
    artist_infos: List[Tuple[str, str, List[str]]] = []
    for (title, artist) in favorites:
        try:
            resolved = resolve_favorite_to_artist(sp, title, artist, limit=10, accept_threshold=72.0)
            if resolved:
                aid, aname, a_genres = resolved
                if aid:
                    artist_infos.append((aid, aname, a_genres))
        except Exception:
            continue

    # Build per-artist candidate lists
    per_artist_lists: List[List[Tuple[str, str]]] = []
    for (aid, _aname, _g) in artist_infos:
        lst: List[Tuple[str, str]] = []
        try:
            top = sp.get_artist_top_tracks(aid, limit=10)
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
        per_artist_lists.append(lst)

    # Interleave across favorites (ensures representation)
    combined = _interleave_lists(per_artist_lists)

    # Deduplicate while selecting up to max_recs with fair share
    seen, recs = set(), []
    for (text, url) in combined:
        if text not in seen:
            seen.add(text)
            recs.append((text, url))
        if len(recs) >= max_recs:
            break
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
    artist_pop_max: int = 45,
    per_bucket: int = 5,
    min_artists: int = 2,           # guarantee at least 2 artists in artist-based buckets
    extra_genre: str = "",          # optional manual genre from user
) -> Dict[str, List[Tuple[str, str]]]:
    sp = SpotifyClient(client_id, client_secret, market=market or "US")
    favorites = [(t.strip(), a.strip()) for (t, a) in favorites if t and a]

    # Resolve all favorites to artists
    fav_artist_infos: List[Tuple[str, str, List[str]]] = []
    for (title, artist) in favorites:
        try:
            resolved = resolve_favorite_to_artist(sp, title, artist, limit=10, accept_threshold=72.0)
            if resolved:
                aid, aname, a_genres = resolved
                if aid:
                    fav_artist_infos.append((aid, aname, a_genres or []))
        except Exception:
            continue

    buckets: Dict[str, List[Tuple[str, str]]] = {
        "Hidden gems from your favorite artists": [],
        "Artists you should listen to": [],
        "Rising stars in your genres": [],
    }

    # 1) Hidden gems (low-pop top tracks) — interleave per favorite
    per_artist_hidden: List[List[Tuple[str, str]]] = []
    for (aid, aname, _genres) in fav_artist_infos:
        lst: List[Tuple[str, str]] = []
        try:
            top = sp.get_artist_top_tracks(aid, limit=10)
            for tr in top:
                tname = tr.get("name")
                popularity = tr.get("popularity", 50)
                artists = tr.get("artists") or []
                pa_name = artists[0].get("name") if artists else aname
                turl = (tr.get("external_urls") or {}).get("spotify", "")
                if tname and turl and popularity <= track_pop_max:
                    lst.append((f"{tname} — {pa_name}", turl))
        except Exception:
            pass
        per_artist_hidden.append(lst)
    hidden_combined = _interleave_lists(per_artist_hidden)
    buckets["Hidden gems from your favorite artists"] = hidden_combined[:per_bucket]

    # 2) Artists you should listen to (Related Artists) — interleave & guarantee min_artists
    def related_interleaved(pop_cap: int) -> List[Tuple[str, str]]:
        per_aid_lists = []
        for (aid, _aname, _genres) in fav_artist_infos:
            lst = []
            try:
                related = sp.get_related_artists(aid)
                for ar in related:
                    name = ar.get("name")
                    pop = ar.get("popularity", 50)
                    url = (ar.get("external_urls") or {}).get("spotify", "")
                    if name and url and pop <= pop_cap:
                        lst.append((name, url))
            except Exception:
                pass
            per_aid_lists.append(lst)
        combined = _interleave_lists(per_aid_lists)
        # Deduplicate by name (case-insensitive)
        dedup, seen = [], set()
        for name, url in combined:
            key = (name or "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                dedup.append((name, url))
        return dedup

    rel_caps = [artist_pop_max, min(artist_pop_max + 10, 75), min(artist_pop_max + 20, 85), 100]
    related_items: List[Tuple[str, str]] = []
    for cap in rel_caps:
        related_items = related_interleaved(cap)
        if len(related_items) >= min_artists:
            break
    if len(related_items) < min_artists:
        related_items = related_interleaved(100)
    buckets["Artists you should listen to"] = related_items[:max(per_bucket, min_artists)]

    # 3) Rising stars in your genres (Search by genre) — interleave & guarantee min_artists
    genre_pool = {g for (_aid, _aname, genres) in fav_artist_infos for g in (genres or [])}
    if extra_genre.strip():
        genre_pool.add(extra_genre.strip())
    if not genre_pool:
        genre_pool |= _backfill_genres_from_related(sp, fav_artist_infos)
    if not genre_pool:
        genre_pool = {"indie", "alternative", "singer-songwriter", "electronic", "hip hop", "afrobeats", "latin"}

    def rising_interleaved(pop_cap: int, limit: int = 30) -> List[Tuple[str, str]]:
        per_genre_lists = []
        genres_to_use = list(genre_pool)[:3] if len(genre_pool) > 3 else list(genre_pool)
        for genre in genres_to_use:
            lst = []
            try:
                items = sp.search_artists_by_genre(genre, limit=limit)
                items = sorted(items, key=lambda x: x.get("popularity", 50))
                for ar in items:
                    pop = ar.get("popularity", 50)
                    if pop > pop_cap:
                        continue
                    name = ar.get("name")
                    url = (ar.get("external_urls") or {}).get("spotify", "")
                    if name and url:
                        lst.append((f"{name} ({genre})", url))
            except Exception:
                pass
            per_genre_lists.append(lst)
        combined = _interleave_lists(per_genre_lists)
        # Deduplicate by display text
        dedup, seen = [], set()
        for text, url in combined:
            key = (text or "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                dedup.append((text, url))
        return dedup

    rise_caps = [artist_pop_max, min(artist_pop_max + 10, 70), min(artist_pop_max + 20, 85), 100]
    rising_items: List[Tuple[str, str]] = []
    for cap in rise_caps:
        rising_items = rising_interleaved(pop_cap=cap, limit=40 if cap >= artist_pop_max + 10 else 30)
        if len(rising_items) >= min_artists:
            break
    if len(rising_items) < min_artists:
        rising_items = rising_interleaved(pop_cap=100, limit=50)
    buckets["Rising stars in your genres"] = rising_items[:max(per_bucket, min_artists)]

    return buckets

def collect_genres_for_favorites(
    client_id: str, client_secret: str, market: str, favorites: List[Tuple[str,str]]
) -> List[str]:
    sp = SpotifyClient(client_id, client_secret, market=market or "US")
    fav_artist_infos: List[Tuple[str, str, List[str]]] = []
    for (title, artist) in [(t.strip(), a.strip()) for (t, a) in favorites if t and a]:
        try:
            resolved = resolve_favorite_to_artist(sp, title, artist, limit=10, accept_threshold=72.0)
            if resolved:
                aid, aname, a_genres = resolved
                if aid:
                    fav_artist_infos.append((aid, aname, a_genres or []))
        except Exception:
            continue
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

    with st.expander("🎛️ Advanced & Niche controls", expanded=False):
        track_pop_max = st.slider("Max track popularity (hidden gems)", 0, 100, 35, help="Lower = more niche")
        artist_pop_max = st.slider("Max artist popularity (artists/rising stars)", 0, 100, 45, help="Lower = more niche")
        per_bucket = st.slider("Items per bucket", 1, 10, 5)
        min_artists = st.slider("Minimum artists per bucket (guaranteed)", 0, 5, 2)
        extra_genre = st.text_input("Optional: add a genre (e.g., 'indie', 'afrobeats')", value="")

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

run = st.button("Recommend", type="primary")

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

if run:
    if not _ensure_creds():
        st.stop()

    favorites = _collect_favorites_with_feedback()
    if not favorites:
        st.warning("Please enter at least one valid Title + Artist pair.")
        st.stop()

    # Apply genre-driven theme (dominant or blended across ALL inputs)
    genres = collect_genres_for_favorites(CLIENT_ID, CLIENT_SECRET, market, favorites)
    theme = pick_theme_by_genres(genres)
    st.markdown(theme["css"], unsafe_allow_html=True)
    st.markdown(f"### {theme['emoji']} Personalized Interface")

    # Tabs for modes
    tab_std, tab_niche = st.tabs([f"{theme['emoji']} Standard", "🌱 Niche"])

    # --- Standard ---
    with tab_std:
        with st.spinner("Fetching recommendations..."):
            recs = recommend_from_favorites(CLIENT_ID, CLIENT_SECRET, market, favorites, max_recs=3)
        st.subheader("Recommendations")
        if not recs:
            st.info("No compliant recommendations found—try different titles/artists.")
        else:
            for i, (text, url) in enumerate(recs, start=1):
                st.write(f"**{i}. {text}**")
                if url:
                    link_button("Open in Spotify", url)

    # --- Niche ---
    with tab_niche:
        with st.spinner("Fetching niche recommendations..."):
            buckets = build_recommendation_buckets(
                CLIENT_ID,
                CLIENT_SECRET,
                market,
                favorites,
                track_pop_max=track_pop_max,
                artist_pop_max=artist_pop_max,
                per_bucket=per_bucket,
                min_artists=min_artists,
                extra_genre=extra_genre,
            )
        st.subheader("Recommendations")
        for title, items in buckets.items():
            st.markdown(f"#### {title}")
            if not items:
                st.info("No items found—try raising the popularity thresholds or change favorites/market.")
            else:
                for text, url in items:
                    st.write(f"- **{text}**")
                    if url:
                        link_button("Open in Spotify", url)
            st.divider()
