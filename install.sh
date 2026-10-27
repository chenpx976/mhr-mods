#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
target="${DECK_TARGET:-deck@192.168.1.28}"
npm run typecheck
npm run build
npm test
python3 - <<'PY'
import hashlib
from pathlib import Path
from environment import ASSET_HASHES
for name, expected in ASSET_HASHES.items():
    with (Path('assets') / name).open('rb') as f:
        assert hashlib.file_digest(f, 'sha256').hexdigest() == expected, name
print('Offline repair assets verified')
PY
archive="$(mktemp -t mhrmods).tar.gz"
trap 'rm -f "$archive"' EXIT
COPYFILE_DISABLE=1 tar --no-xattrs -czf "$archive" main.py manager.py environment.py plugin.json package.json dist assets
ssh "$target" 'du -sh /home/deck/homebrew/plugins/MHRMods 2>/dev/null || true; if [ -d /home/deck/homebrew/plugins/MHRMods ]; then sudo tar -czf "/home/deck/Downloads/02-GameMods/04-MH-Rise/Backups/MHRMods-plugin-$(date +%Y%m%d-%H%M%S).tar.gz" -C /home/deck/homebrew/plugins MHRMods; fi'
scp "$archive" "$target:/tmp/mhrmods-install.tar.gz"
ssh "$target" 'set -e; sudo mkdir -p /home/deck/homebrew/plugins/MHRMods /home/deck/.local/share/mhr-mods/repair-assets; sudo tar -xzf /tmp/mhrmods-install.tar.gz -C /home/deck/homebrew/plugins/MHRMods; sudo chown -R root:root /home/deck/homebrew/plugins/MHRMods; sudo cp /home/deck/homebrew/plugins/MHRMods/assets/* /home/deck/.local/share/mhr-mods/repair-assets/; sudo chown -R root:root /home/deck/.local/share/mhr-mods; sudo chmod 755 /home/deck/.local/share/mhr-mods /home/deck/.local/share/mhr-mods/repair-assets; sudo chmod 644 /home/deck/.local/share/mhr-mods/repair-assets/*; sudo systemctl restart plugin_loader; systemctl is-active plugin_loader'
