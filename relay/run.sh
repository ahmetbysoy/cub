#!/usr/bin/env bash
# Temporary relay helper: downloads the target file on a GitHub runner,
# splits it into <=45MB parts and pushes them to the `relay/cubecraft` branch.
set -uo pipefail

OUT="relay/out"
URL_FILE="relay/url.txt"
mkdir -p "$OUT"
LOG="$OUT/status.txt"
URL="$(tr -d '\r\n' < "$URL_FILE")"

{
  echo "run_id: ${GITHUB_RUN_ID:-local}"
  echo "started: $(date -u +%FT%TZ)"
  echo "target_host: $(printf '%s' "$URL" | sed -E 's#^(https?://[^/]+)/.*#\1#')"
} > "$LOG"

curl -fL --retry 3 --retry-delay 5 --max-time 2400 \
  -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36" \
  -e "https://apkpure.com/" \
  -o /tmp/payload.xapk "$URL" 2>/tmp/curl.log
rc=$?

if [ "$rc" -ne 0 ]; then
  {
    echo "result: DOWNLOAD_FAILED"
    echo "curl_rc: $rc"
    echo "--- curl log (tail) ---"
    tail -40 /tmp/curl.log
  } >> "$LOG"
else
  SIZE=$(stat -c%s /tmp/payload.xapk)
  SHA=$(sha256sum /tmp/payload.xapk | cut -d' ' -f1)
  {
    echo "result: OK"
    echo "bytes: $SIZE"
    echo "sha256: $SHA"
  } >> "$LOG"
  rm -f "$OUT"/part-*
  split -b 45M -d -a 3 /tmp/payload.xapk "$OUT/part-"
fi

ls -l "$OUT" >> "$LOG" 2>&1 || true
echo "finished: $(date -u +%FT%TZ)" >> "$LOG"

git config user.name "relay-bot"
git config user.email "relay-bot@users.noreply.github.com"

# Publish payload on a throwaway orphan branch (no history, easy to delete later)
git checkout --orphan relay-payload-tmp >/dev/null 2>&1 || true
git rm -rf . >/dev/null 2>&1 || true
git add -A "$OUT"
git commit -m "relay payload" >/dev/null 2>&1 || echo "nothing to commit"
git push -f origin "HEAD:refs/heads/relay/cubecraft"
