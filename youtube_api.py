"""YouTube resmi API yardimcisi: kanal basina OAuth, istatistik raporu, yukleme/zamanlama.

Kurulum (bir kerelik):
  1. Google Cloud'da proje ac, "YouTube Data API v3" + "YouTube Analytics API" etkinlestir.
  2. OAuth consent screen (External) + Desktop app client olustur, JSON'u
     secrets/client_secret.json olarak kaydet.
  3. Her kanal icin:  python youtube_api.py auth kanal1   /   python youtube_api.py auth kanal2
     (tarayicida dogru Google hesabini ve kanali sec)

Kullanim:
  python youtube_api.py stats kanal1 [--days 28]
  python youtube_api.py upload kanal1 video.mp4 --title "..." --desc-file d.txt --tags a,b \
      --publish-at "2026-10-05 15:00" [--ai]

Not: Denetlenmemis API projelerinden yuklenen videolar YouTube tarafindan "private"a
kilitlenir; upload/zamanlama icin projenin YouTube API audit'ten gecmesi gerekir.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).parent
SECRETS = ROOT / "secrets"
CLIENT_SECRET = SECRETS / "client_secret.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
TR = dt.timezone(dt.timedelta(hours=3))


def _token_path(channel: str) -> Path:
    return SECRETS / f"yt_token_{channel}.json"


def get_creds(channel: str, interactive: bool = False) -> Credentials:
    path = _token_path(channel)
    creds = Credentials.from_authorized_user_file(str(path), SCOPES) if path.exists() else None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None
    if not creds or not creds.valid:
        if not interactive:
            sys.exit(f"'{channel}' icin token yok/gecersiz. Once: python youtube_api.py auth {channel}")
        if not CLIENT_SECRET.exists():
            sys.exit(f"{CLIENT_SECRET} bulunamadi (Google Cloud > Credentials > Desktop app JSON).")
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
        creds = flow.run_local_server(port=0, prompt="consent")
    SECRETS.mkdir(exist_ok=True)
    path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def clients(channel: str, interactive: bool = False):
    creds = get_creds(channel, interactive)
    return (build("youtube", "v3", credentials=creds),
            build("youtubeAnalytics", "v2", credentials=creds))


def my_channel(yt) -> dict:
    return yt.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()["items"][0]


def recent_uploads(yt, ch: dict, limit: int = 50) -> list[dict]:
    pl = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids = [it["contentDetails"]["videoId"] for it in yt.playlistItems().list(
        part="contentDetails", playlistId=pl, maxResults=min(limit, 50)).execute().get("items", [])]
    if not ids:
        return []
    return yt.videos().list(part="snippet,statistics,status,contentDetails",
                            id=",".join(ids)).execute()["items"]


def video_analytics(ya, days: int) -> dict[str, dict]:
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    res = ya.reports().query(
        ids="channel==MINE", startDate=str(start), endDate=str(end), dimensions="video",
        metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
                "likes,subscribersGained",
        sort="-views", maxResults=200).execute()
    cols = [h["name"] for h in res.get("columnHeaders", [])]
    return {row[0]: dict(zip(cols, row)) for row in res.get("rows", [])}


def retention_curve(ya, video_id: str, since: str = "2026-01-01") -> list[dict]:
    """Izleyici tutma egrisi: videonun %x'inde izleyicilerin ne kadari hala izliyor (audienceWatchRatio)
    ve benzer uzunluktaki videolara gore durum (relativeRetentionPerformance, 0.5 = ortalama)."""
    res = ya.reports().query(
        ids="channel==MINE", startDate=since, endDate=str(dt.date.today()), dimensions="elapsedVideoTimeRatio",
        metrics="audienceWatchRatio,relativeRetentionPerformance", filters=f"video=={video_id}").execute()
    return [{"at": r[0], "watch": r[1], "relative": r[2]} for r in res.get("rows", [])]


def cmd_retention(a):
    yt, ya = clients(a.channel)
    v = yt.videos().list(part="snippet,contentDetails", id=a.video_id).execute()["items"][0]
    m = re.match(r"PT(?:(\d+)M)?(?:(\d+)S)?", v["contentDetails"]["duration"])
    dur = int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
    curve = retention_curve(ya, a.video_id)
    print(f"# {v['snippet']['title']}  ({dur} sn)")
    if not curve:
        print("(retention verisi henuz yok; YouTube 1-2 gun gecikmeli)")
        return
    prev = None
    for p in curve:
        drop = "" if prev is None else f"{(p['watch'] - prev) * 100:+.0f}"
        bar = "#" * int(min(p["watch"], 1.5) * 30)
        print(f"{p['at'] * dur:5.1f} sn  {p['watch'] * 100:5.0f}%  {drop:>4}  {bar}")
        prev = p["watch"]
    if a.json:
        Path(a.json).write_text(json.dumps({"duration": dur, "curve": curve}, indent=1), encoding="utf-8")


def cmd_auth(a):
    yt, _ = clients(a.channel, interactive=True)
    ch = my_channel(yt)
    print(f"OK: '{a.channel}' -> {ch['snippet']['title']} ({ch['id']})")


def cmd_stats(a):
    yt, ya = clients(a.channel)
    ch = my_channel(yt)
    s = ch["statistics"]
    print(f"# {ch['snippet']['title']}  abone={s.get('subscriberCount')}  "
          f"toplam izlenme={s.get('viewCount')}  video={s.get('videoCount')}")
    try:
        an = video_analytics(ya, a.days)
    except Exception as e:  # analytics 24-48 saat gecikmeli olabilir / yetki yoksa
        print(f"(analytics alinamadi: {e})")
        an = {}
    print("(analytics ~1-2 gun gecikmeli; izlenme sutunu anlik)")
    print(f"{'yayin (TR)':16} {'durum':10} {'izl':>6} {'like':>5} {'ort.sn':>6} {'ort.%':>6}  baslik")
    for v in recent_uploads(yt, ch):
        st, sn = v["status"], v["snippet"]
        when = st.get("publishAt") or sn["publishedAt"]
        t = dt.datetime.fromisoformat(when.replace("Z", "+00:00")).astimezone(TR)
        state = "zamanli" if st.get("publishAt") and st["privacyStatus"] == "private" else st["privacyStatus"]
        r = an.get(v["id"], {})
        avd = f"{r['averageViewDuration']:.0f}" if r else "-"
        avp = f"{r['averageViewPercentage']:.0f}" if r else "-"
        print(f"{t:%m-%d %H:%M}      {state:10} {v['statistics'].get('viewCount', '0'):>6} "
              f"{v['statistics'].get('likeCount', '0'):>5} {avd:>6} {avp:>6}  {sn['title'][:60]}")
    if a.json:
        Path(a.json).write_text(json.dumps({"channel": ch, "analytics": an}, indent=2), encoding="utf-8")


def upload(channel: str, file: str, title: str, desc: str, tags: list[str],
           publish_at: str | None = None, ai: bool = False, kids: bool = False) -> str:
    yt, _ = clients(channel)
    status = {"privacyStatus": "public", "selfDeclaredMadeForKids": kids,
              "containsSyntheticMedia": ai}
    if publish_at:  # "YYYY-MM-DD HH:MM" Turkiye saati
        t = dt.datetime.strptime(publish_at, "%Y-%m-%d %H:%M").replace(tzinfo=TR)
        status.update(privacyStatus="private",
                      publishAt=t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    body = {"snippet": {"title": title[:100], "description": desc, "tags": tags, "categoryId": "24"},
            "status": status}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(file, chunksize=8 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        prog, resp = req.next_chunk()
        if prog:
            print(f"  yukleniyor %{prog.progress() * 100:.0f}")
    vid = resp["id"]
    print(f"OK: https://youtube.com/shorts/{vid}  durum={resp['status']['privacyStatus']}"
          + (f"  yayin={publish_at} TR" if publish_at else ""))
    return vid


def cmd_upload(a):
    desc = Path(a.desc_file).read_text(encoding="utf-8") if a.desc_file else (a.desc or "")
    tags = [t.strip() for t in (a.tags or "").split(",") if t.strip()]
    upload(a.channel, a.file, a.title, desc, tags, a.publish_at, a.ai)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("auth"); s.add_argument("channel"); s.set_defaults(f=cmd_auth)
    s = sp.add_parser("stats"); s.add_argument("channel"); s.add_argument("--days", type=int, default=28)
    s.add_argument("--json"); s.set_defaults(f=cmd_stats)
    s = sp.add_parser("retention"); s.add_argument("channel"); s.add_argument("video_id")
    s.add_argument("--json"); s.set_defaults(f=cmd_retention)
    s = sp.add_parser("upload"); s.add_argument("channel"); s.add_argument("file")
    s.add_argument("--title", required=True); s.add_argument("--desc"); s.add_argument("--desc-file")
    s.add_argument("--tags"); s.add_argument("--publish-at"); s.add_argument("--ai", action="store_true")
    s.set_defaults(f=cmd_upload)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
