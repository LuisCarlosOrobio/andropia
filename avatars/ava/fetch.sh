#!/usr/bin/env bash
# Fetch the Ava avatar model.
#
# Not committed: at 21 MB it would dominate a repository whose entire source
# is a fraction of that, and every clone would pay for it. The manifest and
# licence live in git; the body is fetched on demand.
set -euo pipefail

cd "$(dirname "$0")"
URL="https://raw.githubusercontent.com/pixiv/ChatVRM/main/public/AvatarSample_B.vrm"
OUT="AvatarSample_B.vrm"

if [ -f "$OUT" ]; then
  echo "$OUT already present"
  exit 0
fi

echo "Fetching $OUT (~21 MB)…"
curl -fL --progress-bar -o "$OUT" "$URL"

# The terms are a website ToS pixiv may change without notice, so archive a
# dated copy alongside the asset. This evidences what they said when you
# shipped, which is the whole reason to keep it.
printf 'Retrieved %s from %s\nTerms at time of retrieval: %s\n' \
  "$(date -u +%Y-%m-%d)" "$URL" \
  "https://vroid.pixiv.help/hc/en-us/articles/4402394424089" \
  > RETRIEVED.txt

echo "Done. See ../../ASSET-LICENSES.md for terms."
