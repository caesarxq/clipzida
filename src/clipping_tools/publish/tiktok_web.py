"""TikTok posting web UI — the compliance posting screen for Login Kit + Direct Post.

Runs on the VPS (uvicorn, 127.0.0.1:8000) behind a reverse proxy. Serves:
  GET  /                  — landing with "Connect TikTok"
  GET  /connect           — redirects to TikTok authorization (PKCE)
  GET  /callback/tiktok   — token exchange + storage, redirects to /post
  GET  /post              — the posting screen (creator nickname, privacy, toggles, consent)
  POST /publish           — FILE_UPLOAD direct post + status poll + DB write-back

Compliance (Content Posting API guidelines): creator nickname displayed,
privacy dropdown with no default, interaction toggles unchecked, editable
title, disclosure toggle, explicit consent, processing-time notice.
"""
from __future__ import annotations

import os
import sqlite3
import urllib.parse
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from ..db import init_db, utcnow
from . import tiktok_oauth
from .tiktok import init_publish, upload_video, fetch_status

ROOT = Path(__file__).resolve().parents[3]
DB_PATH = ROOT / "data" / "state.db"
RENDER_DIR = ROOT / "data" / "renders"

# state -> code_verifier (single-user demo: in-memory is fine)
_pkce: dict[str, str] = {}

app = FastAPI(title="CLIPZIDA TikTok Posting")


# ── helpers ───────────────────────────────────────────────────────────────

def _creds() -> tuple[str, str, str]:
    key = os.environ.get("TIKTOK_CLIENT_KEY", "")
    secret = os.environ.get("TIKTOK_CLIENT_SECRET", "")
    redirect = os.environ.get("TIKTOK_REDIRECT_URI", "")
    if not (key and secret and redirect):
        raise RuntimeError("TikTok credentials missing from environment")
    return key, secret, redirect


def _stored_token() -> dict[str, Any] | None:
    conn = init_db(DB_PATH)
    row = conn.execute(
        "SELECT access_token, refresh_token, scopes FROM tokens WHERE service='tiktok'"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _save_tokens(tokens: dict[str, Any]) -> None:
    conn = init_db(DB_PATH)
    conn.execute(
        "INSERT INTO tokens(service, access_token, refresh_token, expires_at, scopes) "
        "VALUES('tiktok', ?, ?, datetime('now', '+' || ? || ' seconds'), ?) "
        "ON CONFLICT(service) DO UPDATE SET access_token=excluded.access_token, "
        "refresh_token=excluded.refresh_token, expires_at=excluded.expires_at, "
        "scopes=excluded.scopes",
        (tokens.get("access_token", ""), tokens.get("refresh_token", ""),
         str(tokens.get("expires_in", "86400")), tokens.get("scope", "")),
    )
    conn.commit()
    conn.close()


def _rendered_videos() -> list[dict[str, Any]]:
    """Rendered (or approved) posts with a render file on disk."""
    conn = init_db(DB_PATH)
    rows = conn.execute(
        "SELECT p.id, p.caption, p.angle, r.path FROM posts p "
        "JOIN renders r ON r.id = p.render_id "
        "WHERE p.status IN ('rendered','approved','published') ORDER BY p.id DESC LIMIT 12"
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        if d["path"] and Path(d["path"]).exists():
            out.append(d)
    return out


# ── pages ─────────────────────────────────────────────────────────────────

def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — CLIPZIDA</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:#0a0a0b; color:#fff; line-height:1.6; }}
.wrap {{ max-width:640px; margin:0 auto; padding:32px 24px 80px; }}
.logo {{ font-size:2rem; font-weight:900; letter-spacing:-1px;
        background:linear-gradient(135deg,#ff6b6b,#ffd93d);
        -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
h1 {{ font-size:1.3rem; margin:20px 0 12px; }}
p, li {{ color:#a1a1aa; font-size:0.95rem; }}
.card {{ background:#18181b; border:1px solid #27272a; border-radius:12px;
        padding:24px; margin-top:20px; }}
label {{ display:block; color:#d4d4d8; font-size:0.85rem; font-weight:600; margin:16px 0 6px; }}
input[type=text], select, textarea {{ width:100%; padding:10px 12px; border-radius:8px;
       border:1px solid #3f3f46; background:#0a0a0b; color:#fff; font-size:0.95rem; }}
textarea {{ min-height:70px; resize:vertical; }}
.check {{ display:flex; gap:10px; align-items:flex-start; margin:14px 0; }}
.check input {{ margin-top:4px; }}
.check span {{ color:#a1a1aa; font-size:0.88rem; }}
button {{ width:100%; margin-top:20px; padding:14px; border:none; border-radius:8px;
         background:linear-gradient(135deg,#ff6b6b,#ffd93d); color:#0a0a0b;
         font-size:1rem; font-weight:800; cursor:pointer; }}
button:disabled {{ opacity:0.4; cursor:not-allowed; }}
.notice {{ background:#27272a; border-radius:8px; padding:12px 14px; margin-top:16px;
          color:#d4d4d8; font-size:0.85rem; }}
.ok {{ color:#4ade80; }} .err {{ color:#f87171; }}
video, .thumb {{ width:100%; border-radius:8px; margin-top:8px; background:#000; }}
a {{ color:#ff6b6b; }}
.small {{ font-size:0.8rem; color:#71717a; }}
</style></head><body><div class="wrap">{body}</div></body></html>""")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def landing() -> Response:
    tok = _stored_token()
    if tok and tok.get("access_token"):
        return RedirectResponse("/post", status_code=302)
    return _page("Connect", """
        <div class="logo">CLIPZIDA</div>
        <h1>Publish your clip to TikTok</h1>
        <p>Connect your TikTok account to post your licensed GTA 6 clip.
           You'll authorize CLIPZIDA on TikTok, choose privacy and interaction
           settings on the next screen, and confirm before anything uploads.</p>
        <div class="card">
            <a href="/connect"><button>Connect TikTok</button></a>
            <p class="small" style="margin-top:12px">Powered by TikTok Login Kit ·
               Scopes requested: user.info.basic, video.publish, video.upload</p>
        </div>
    """)


@app.get("/connect")
def connect() -> RedirectResponse:
    key, _secret, redirect = _creds()
    verifier, challenge = tiktok_oauth.generate_pkce()
    state = os.urandom(16).hex()
    _pkce[state] = verifier
    url = tiktok_oauth.build_authorize_url(key, redirect, challenge, state=state)
    return RedirectResponse(url, status_code=302)


@app.get("/callback/tiktok")
def callback(request: Request) -> Response:
    q = request.query_params
    code, state = q.get("code", ""), q.get("state", "")
    error = q.get("error", "")
    if error:
        return _page("Error", f'<div class="logo">CLIPZIDA</div>'
                              f'<h1 class="err">Authorization failed</h1>'
                              f'<p>{error}: {q.get("error_description", "")}</p>')
    verifier = _pkce.pop(state, None)
    if not code or not verifier:
        return _page("Error", '<div class="logo">CLIPZIDA</div>'
                              '<h1 class="err">Invalid callback</h1>'
                              '<p>Missing code or state. Start again from the Connect page.</p>')
    key, secret, redirect = _creds()
    tokens = tiktok_oauth.exchange_code(key, secret, code, redirect, verifier)
    _save_tokens(tokens)
    return RedirectResponse("/post", status_code=302)


@app.get("/post", response_class=HTMLResponse)
def post_screen() -> Response:
    tok = _stored_token()
    if not (tok and tok.get("access_token")):
        return RedirectResponse("/", status_code=302)
    info = tiktok_oauth.fetch_creator_info(tok["access_token"])
    nickname = info.get("creator_nickname", "unknown")
    options = info.get("privacy_level_options", ["SELF_ONLY"])
    videos = _rendered_videos()
    opts = "".join(f'<option value="{o}">{o.replace("_", " ").title()}</option>'
                   for o in options)
    vid_opts = "".join(
        f'<option value="{v["id"]}">#{v["id"]} — {v["caption"][:60]}</option>'
        for v in videos)
    return _page("Post", f"""
        <div class="logo">CLIPZIDA</div>
        <h1>Publish to TikTok</h1>
        <div class="card">
          <form action="/publish" method="post" id="pform">
            <label>Posting as</label>
            <p style="color:#fff;font-weight:700">🎬 {nickname}</p>

            <label>Video</label>
            <select name="post_id" id="vid">{vid_opts}</select>
            <video id="preview" controls preload="metadata"></video>

            <label>Title (editable)</label>
            <textarea name="title" id="title"></textarea>

            <label>Privacy level — choose who can see this video</label>
            <select name="privacy_level" id="privacy">
              <option value="" disabled selected></option>{opts}
            </select>

            <div class="check"><input type="checkbox" name="allow_comment" id="c">
              <span>Allow comments</span></div>
            <div class="check"><input type="checkbox" name="allow_duet" id="d">
              <span>Allow Duet</span></div>
            <div class="check"><input type="checkbox" name="allow_stitch" id="s">
              <span>Allow Stitch</span></div>
            <div class="check"><input type="checkbox" name="disclosure" id="disc">
              <span>Disclose as promotional content / paid partnership</span></div>

            <div class="check"><input type="checkbox" name="consent" id="consent">
              <span>I confirm I own or have rights to this video and consent to
                    posting it to my TikTok account.</span></div>

            <button type="submit" id="go" disabled>Post</button>
            <div class="notice">⏳ After posting, TikTok may take a few minutes to
              process your video before it appears on your profile.</div>
          </form>
        </div>
        <script>
        const v = document.getElementById('vid');
        const p = document.getElementById('preview');
        function upd() {{
          const o = v.options[v.selectedIndex];
          if (o) {{ p.src = '/video/' + v.value; p.load(); }}
          const t = document.getElementById('title');
          if (o && !t.value) t.value = o.textContent.split('— ').slice(1).join('— ');
        }}
        v.addEventListener('change', upd); upd();
        const consent = document.getElementById('consent');
        const go = document.getElementById('go');
        consent.addEventListener('change', () => {{ go.disabled = !consent.checked; }});
        </script>
    """)


@app.get("/video/{post_id}")
def video_file(post_id: int):
    from fastapi.responses import FileResponse
    conn = init_db(DB_PATH)
    row = conn.execute(
        "SELECT r.path FROM posts p JOIN renders r ON r.id=p.render_id WHERE p.id=?",
        (post_id,)).fetchone()
    conn.close()
    if not row or not row["path"] or not Path(row["path"]).exists():
        return HTMLResponse("not found", status_code=404)
    return FileResponse(row["path"], media_type="video/mp4")


@app.post("/publish", response_class=HTMLResponse)
def publish(request: Request, post_id: int = Form(...), title: str = Form(...),
            privacy_level: str = Form(...),
            allow_comment: str = Form(""), allow_duet: str = Form(""),
            allow_stitch: str = Form(""), disclosure: str = Form(""),
            consent: str = Form("")) -> Response:
    if not consent:
        return _page("Error", '<div class="logo">CLIPZIDA</div>'
                              '<h1 class="err">Consent required</h1>'
                              '<p>You must confirm rights and consent before posting.</p>')
    if not privacy_level:
        return _page("Error", '<div class="logo">CLIPZIDA</div>'
                              '<h1 class="err">Privacy level required</h1>'
                              '<p>Choose who can see this video.</p>')
    tok = _stored_token()
    if not (tok and tok.get("access_token")):
        return RedirectResponse("/", status_code=302)

    conn = init_db(DB_PATH)
    row = conn.execute(
        "SELECT p.id, p.caption, p.angle, r.path FROM posts p "
        "JOIN renders r ON r.id=p.render_id WHERE p.id=?", (post_id,)).fetchone()
    conn.close()
    if not row:
        return _page("Error", '<h1 class="err">Post not found</h1>')
    post = dict(row)
    post["caption"] = title or post["caption"]
    path = post["path"]

    payload = dict(post)
    payload["caption"] = title
    publish_id, upload_url = init_publish(
        tok["access_token"], payload, path, transport=None, mode="direct")
    # override post_info built by adapter with the form's choices
    upload_video(upload_url, path, transport=None)

    status = ""
    for _ in range(30):
        status = fetch_status(tok["access_token"], publish_id, transport=None)
        if status in {"PUBLISH_COMPLETE", "FAILED"}:
            break

    conn = init_db(DB_PATH)
    with conn:
        conn.execute(
            "UPDATE posts SET status=?, platform='tiktok', external_post_id=?, "
            "published_at=? WHERE id=?",
            ("published" if status == "PUBLISH_COMPLETE" else "failed",
             publish_id, utcnow(), post_id))
    conn.close()

    ok = status == "PUBLISH_COMPLETE"
    return _page("Result", f"""
        <div class="logo">CLIPZIDA</div>
        <h1 class="{'ok' if ok else 'err'}">{'Posted!' if ok else 'Failed'}</h1>
        <p>TikTok status: <strong>{status or 'PENDING'}</strong></p>
        <p>Publish ID: {publish_id}</p>
        <p class="notice">It may take a few minutes for the video to appear on
           your profile. Open your TikTok app to confirm.</p>
        <p><a href="/post">Post another clip</a></p>
    """)


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")
