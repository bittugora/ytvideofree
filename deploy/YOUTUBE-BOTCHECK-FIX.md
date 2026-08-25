# Fixing "Sign in to confirm you're not a bot" on a VPS

YouTube shows this error when a request comes from an IP address it flags as a
datacenter/VPS. It is not a bug in the link or in this app. No end-user action
is needed — these are one-time server-side fixes, done once by the operator.
Afterwards users still just paste a link.

## Step 0 — update yt-dlp (required)

YouTube rotates which player clients work every few months. An older yt-dlp
tries clients that no longer work, which produces exactly this error. Update it
inside the app's virtualenv first, because **nothing else works on an old build**:

```bash
cd /var/www/ytvideofree
.venv/bin/pip install -U yt-dlp yt-dlp-ejs curl_cffi
.venv/bin/python -c "import yt_dlp; print(yt_dlp.version.__version__)"
```

(You already installed `ffmpeg` and `nodejs`; those are fine and needed, but on
their own they do not clear this check.)

Then do **one** of the two options below.

---

## Option A — cookies file (quickest, most reliable)

A signed-in session makes YouTube trust the server. Use a **throwaway** Google
account, never your main one.

1. On your own computer, sign in to YouTube with a throwaway account in a
   dedicated browser profile.
2. Install the browser extension **"Get cookies.txt LOCALLY"** and export
   cookies for `youtube.com` (Netscape format).
3. Copy the file to the server, e.g. `scp cookies.txt root@VPS:/var/lib/ytvideofree/cookies.txt`,
   and make it readable by the app user.
4. Set the env var in `/etc/ytvideofree/ytvideofree.env`:

   ```bash
   YTVIDEOFREE_COOKIES_FILE=/var/lib/ytvideofree/cookies.txt
   ```

5. Restart (see bottom) and test.

Note: sessions used by downloaders can get flagged, so expect to refresh this
file occasionally — that's why a throwaway account is recommended.

---

## Option B — PO token provider (robust, no account)

This is the yt-dlp-recommended fix for flagged IPs and the exact error message
above. It needs Node.js ≥ 20 (you installed Node 22) and git.

```bash
# 1. Install the plugin that feeds PO tokens to yt-dlp
cd /var/www/ytvideofree
.venv/bin/pip install -U bgutil-ytdlp-pot-provider

# 2. Clone and build the token-generation server (script mode, no Docker)
git clone --single-branch --branch 1.3.2 \
  https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
  ~/bgutil-ytdlp-pot-provider
cd ~/bgutil-ytdlp-pot-provider/server
npm ci
npx tsc
```

Because the server is at `~/bgutil-ytdlp-pot-provider`, yt-dlp finds it
automatically. If you put it elsewhere, set `server_home` via
`YTVIDEOFREE_PLAYER_CLIENTS` is not needed — the plugin is auto-detected.

(If the app user differs from the user who ran `npm ci`, make sure
`~/bgutil-ytdlp-pot-provider/server/build` is readable by the app user.)

---

## Restart and verify

```bash
sudo systemctl restart ytvideofree
```

Then open `https://your-domain/admin/status/` and click **Run live bot-check
test**. "Extraction succeeded" means the IP is no longer blocked. The same page
shows the yt-dlp version and whether the PO token provider and curl_cffi are
installed.

If it still fails, check the logs for which step is failing:

```bash
sudo journalctl -u ytvideofree -n 200 --no-pager
```
