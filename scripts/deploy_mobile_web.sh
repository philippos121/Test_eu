#!/usr/bin/env bash
# ============================================================
# deploy_mobile_web.sh — Build Flutter web and wire it to FastAPI
#
# Run this ON a machine with Flutter SDK installed, then
# copy mobile_dist/ to the server.  OR run directly on the
# server if Flutter is installed there.
#
# Usage:
#   ./scripts/deploy_mobile_web.sh
#   ./scripts/deploy_mobile_web.sh --server user@1.2.3.4:/opt/eu_portal
# ============================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MOBILE_DIR="$REPO_ROOT/mobile"
OUT_DIR="$REPO_ROOT/mobile_dist"
REMOTE="${1:-}"   # optional: user@host:/path

echo "═══════════════════════════════════════════════════"
echo "  EU-Portal — Flutter Web Build"
echo "═══════════════════════════════════════════════════"

# ── Check Flutter ────────────────────────────────────────────
if ! command -v flutter &>/dev/null; then
  echo "ERROR: Flutter not found. Install from https://flutter.dev/docs/get-started/install"
  exit 1
fi
flutter --version

cd "$MOBILE_DIR"

# ── Generate missing scaffold files if needed ────────────────
echo ""
echo "▶ Generating platform scaffold (web)..."
flutter create . \
  --project-name eu_claims_portal \
  --org eu.portal \
  --platforms=web \
  --no-overwrite 2>/dev/null || true

# ── Install Dart packages ────────────────────────────────────
echo ""
echo "▶ Installing packages..."
flutter pub get

# ── Build ────────────────────────────────────────────────────
echo ""
echo "▶ Building Flutter Web (release, canvaskit)..."
flutter build web \
  --release \
  --web-renderer canvaskit \
  --base-href / \
  --dart-define=API_BASE_URL=

echo ""
echo "▶ Build complete. Size: $(du -sh build/web | cut -f1)"

# ── Copy to mobile_dist ──────────────────────────────────────
echo ""
echo "▶ Copying to $OUT_DIR ..."
rm -rf "$OUT_DIR"
cp -r "$MOBILE_DIR/build/web" "$OUT_DIR"
echo "  Done: $OUT_DIR"

# ── Optional remote deploy ───────────────────────────────────
if [[ -n "$REMOTE" ]]; then
  echo ""
  echo "▶ Deploying to $REMOTE ..."
  rsync -avz --delete "$OUT_DIR/" "$REMOTE/"
  echo "  Deployed."
fi

echo ""
echo "═══════════════════════════════════════════════════"
echo "  DONE."
echo ""
echo "  The Flutter web app is now at: $OUT_DIR/"
echo ""
echo "  FastAPI will serve it automatically on next restart."
echo "  Open on iPhone: http://<server-ip>:8000"
echo "  → Safari → Share → Add to Home Screen → native-like PWA"
echo "═══════════════════════════════════════════════════"
