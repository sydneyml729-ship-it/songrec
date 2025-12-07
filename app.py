
# app.py (single-file version)
import os
import sys
import time
import json
import base64
import urllib.parse
import urllib.request
import urllib.error
import pathlib
import re
import unicodedata
from typing import List, Tuple, Dict, Optional

import streamlit as st

# ---------- Page / Branding ----------
st.set_page_config(page_title="Song Recommendation (Spotify)", page_icon="🎵")
st.markdown("### 🎵 Song Recommendations")
st.caption("Each item includes an 'Open in Spotify' button for attribution.")
st.caption("Tip: typos are okay — we’ll fuzzy‑match your Title and Artist.")

# ---------- Secrets ----------
def _get_secret(name: str) -> str:
    # Prefer Streamlit secrets; fall back to environment variables
    val = st.secrets.get(name, "") or os.getenv(name, "")
    return val.strip()

CLIENT_ID = _get_secret("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = _get_secret("SPOTIFY_CLIENT_SECRET")

# ---------- Portable link button ----------
def link_button(label: str, url: str):
    """Use st.link_button if available; otherwise render a Markdown link."""
    try:
        st.link_button(label, url)
    except Exception:
        if url:
            st.markdown(f"{label}")

# ---------- Spotify client (Client Credentials; allowed endpoints only) ----------
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

    # --- Auth: Client Credentials ---
    def _fetch_access_token(self) -> None:
        """Obtain a ~1-hour bearer token via Client Credentials."""
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
            # Refresh slightly early (95% of expires_in)
            self._expires_at = time.time() + float(payload.get("expires_in", 3600)) * 0.95

    def _ensure_token(self) -> str:
        if not self._access_token or time.time() >= self._expires_at:
            self._fetch_access_token()
        return self._access_token

    # --- Core GET helper ---
    def _api_get(self, path: str, params: Dict[str, str] = None) -> Dict:
        """
        Build a GET request to `SPOTIFY_API_BASE + path` with params and auth header.

        Resilience:
          - If 429 Too Many Requests: sleep Retry-After, then retry once.
          - If 401 Unauthorized: refresh token and retry once.
        """
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
                req = urllib.request.Request(
                    url, headers={"Authorization": f"Bearer {self._access_token}"}, method="GET"
                )
                with urllib.request.urlopen(req, timeout=20) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            raise

    # --- Search helpers ---
    def search_track(self, title: str, artist: str, limit: int = 3) -> List[Dict]:
        """Field-filtered search for a specific track & artist using quoted filters."""
        t = (title or "").strip()
        a = (artist or "").strip()
        if not t and not a:
            return []
        q = " ".join([f'track:"{t}"' if t else "", f'artist:"{a}"' if a else ""]).strip()
        params = {"q": q, "type": "track", "limit": str(limit), "market": self.market}
        data = self._api_get("/search", params)
        return (data.get("tracks", {}) or {}).get("items", []) or []

    def search_tracks_filtered(self, title: str = "", artist: str = "", limit: int = 10) -> List[Dict]:
        """Typo-tolerant field-filtered search (quoted first, then unquoted)."""
        results: List[Dict] = []
        q = " ".join([f'track:"{title.strip()}"' if title else "", f'artist:"{artist.strip()}"' if artist else ""]).strip()
        if q:
            data = self._api_get("/search", {"q": q, "type": "track", "limit": str(limit), "market": self.market})
            results = (data.get("tracks") or {}).get("items", []) or []
        if not results:
            q = " ".join([f"track:{title.strip()}" if title else "", f"artist:{artist.strip()}" if artist else ""]).strip()
            if q:
                data = self._api_get("/search", {"q": q, "type": "track", "limit": str(limit), "market": self.market})
                results = (data.get("tracks") or {}).get("items", []) or []
        return results

    def search_tracks_free(self, query: str, limit: int = 10) -> List[Dict]:
        """Free-text fallback when filters miss."""
        q = (query or "").strip()
        if not q:
            return []
        data = self._api_get("/search", {"q": q, "type": "track", "limit": str(limit), "market": self.market})
        return (data.get("tracks") or {}).get("items", []) or []

    # --- Artist data ---
    def get_artist(self, artist_id: str) -> Dict:
        """Get Artist (name, genres, popularity, images...)."""
        return self._api_get(f"/artists/{artist_id}", {})

    def get_artist_top_tracks(self, artist_id: str, limit: int = 10) -> List[Dict]:
        """Top Tracks (requires `market`)."""
        data = self._api_get(f"/artists/{artist_id}/top-tracks", {"market": self.market})
        items = data.get("tracks", []) or []
        return items[:limit]

    def get_related_artists(self, artist_id: str) -> List[Dict]:
        """Related Artists."""
        data = self._api_get(f"/artists/{artist_id}/related-artists", {})
        return data.get("artists", []) or []

    def search_artists_by_genre(self, genre: str, limit: int = 10, offset: int = 0) -> List[Dict]:
        """Search with genre:"..." (for Niche mode)."""
        g = (genre or "").strip()
        if not g:
            return []
        q = f'genre:"{g}"'
        data = self._api_get("/search", {"q": q, "type": "artist", "limit": str(limit), "offset": str(offset), "market": self.market})
        return (data.get("artists") or {}).get("items", []) or []

    # --- Track core extractor ---
    @staticmethod
    def extract_track_core(track: Dict) -> Tuple[str, str, str, str, str]:
        """Return (track_id, track_name, primary_artist_id, primary_artist_name, spotify_url)."""
        tid = track.get("id") or ""
        tname = track.get("name") or ""
        artists = track.get("artists") or []
        a_id = artists[0].get("id") if artists else ""
        a_name = artists[0].get("name") if artists else ""
        turl = (track.get("external_urls") or {}).get("spotify") or (f"https://open.spotify.com/track/{tid}" if tid else "")
        return tid, tname, a_id, a_name, turl

# ---------- Fuzzy helpers ----------
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
    # Optional helpers
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
    # Fallbacks
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

# ---------- Standard recommendations ----------
def recommend_from_favorites(
    client_id: str,
    client_secret: str,
    market: str,
    favorites: List[Tuple[str, str]],
    max_recs: int = 3,
) -> List[Tuple[str, str]]:
    sp = SpotifyClient(client_id, client_secret, market=market or "US")
    favorites = [(t.strip(), a.strip()) for (t, a) in favorites if t and a]
    fav_keys = {(t.lower(), a.lower()) for (t, a) in favorites}
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
    candidates: List[Tuple[str, str]] = []
    for (aid, _aname, _g) in artist_infos:
        try:
            top = sp.get_artist_top_tracks(aid, limit=10)
            for tr in top:
                _, tname, _, pa_name, turl = SpotifyClient.extract_track_core(tr)
                if not tname or not pa_name:
                    continue
                key = (tname.strip().lower(), pa_name.strip().lower())
                if key in fav_keys:
                    continue
                candidates.append((f"{tname} — {pa_name}", turl or ""))
        except Exception:
            continue
    seen, recs = set(), []
    for (text, url) in candidates:
        if text not in seen:
            seen.add(text)
            recs.append((text, url))
        if len(recs) >= max_recs:
            break
    return recs

# ---------- Niche buckets ----------
def build_recommendation_buckets(
    client_id: str,
    client_secret: str,
    market: str,
    favorites: List[Tuple[str, str]],
    track_pop_max: int = 35,
    artist_pop_max: int = 45,
    per_bucket: int = 5
) -> Dict[str, List[Tuple[str, str]]]:
    sp = SpotifyClient(client_id, client_secret, market=market or "US")
    favorites = [(t.strip(), a.strip()) for (t, a) in favorites if t and a]
    fav_artist_infos: List[Tuple[str, str, List[str]]] = []
    for (title, artist) in favorites:
        try:
