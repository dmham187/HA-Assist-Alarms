#!/bin/bash
# deploy.sh — Copy ha_alarms integration files to the HA Samba share.
# Run from any directory; paths are resolved relative to this script.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAMBA="/Volumes/config"
SRC_INTEGRATION="$SCRIPT_DIR/custom_components/ha_alarms"
DST_INTEGRATION="$SAMBA/custom_components/ha_alarms"
SRC_SENTENCES_DIR="$SCRIPT_DIR/config/custom_sentences"
DST_SENTENCES_DIR="$SAMBA/custom_sentences"

# ---------------------------------------------------------------------------
# Pre-flight: confirm Samba share is mounted
# ---------------------------------------------------------------------------
if [ ! -d "$SAMBA" ]; then
  echo "ERROR: Samba share not mounted at $SAMBA"
  echo ""
  echo "Mount it first:"
  echo "  Finder → Go → Connect to Server → smb://homeassistant.local/config"
  echo "  or: open smb://homeassistant.local/config"
  exit 1
fi

if [ ! -d "$DST_INTEGRATION" ]; then
  echo "ERROR: Destination directory not found: $DST_INTEGRATION"
  echo "Make sure the ha_alarms integration is already installed in HA."
  exit 1
fi

# ---------------------------------------------------------------------------
# Copy integration Python files and support files
# ---------------------------------------------------------------------------
echo "Deploying ha_alarms to Home Assistant..."
echo ""
echo "Integration files:"

for f in "$SRC_INTEGRATION"/*; do
  [ -d "$f" ] && continue          # skip __pycache__ and any other directories
  fname=$(basename "$f")
  cp "$f" "$DST_INTEGRATION/$fname"
  echo "  ✓  custom_components/ha_alarms/$fname"
done

# ---------------------------------------------------------------------------
# Copy sentence YAML (one file per language)
# ---------------------------------------------------------------------------
echo ""
echo "Sentence files:"
for src in "$SRC_SENTENCES_DIR"/*/ha_alarms.yaml; do
  lang=$(basename "$(dirname "$src")")
  mkdir -p "$DST_SENTENCES_DIR/$lang"
  cp "$src" "$DST_SENTENCES_DIR/$lang/ha_alarms.yaml"
  echo "  ✓  custom_sentences/$lang/ha_alarms.yaml"
done

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "Deploy complete."
echo ""
echo "Next step: restart Home Assistant to apply changes."
echo "  Settings → System → Restart Home Assistant"
echo ""
