#!/bin/sh
# Install Prism Monitor for the current user (no root needed).
# Run from a built folder (dist/PrismMonitor) or from the source checkout.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
share="${XDG_DATA_HOME:-$HOME/.local/share}"
bin="$HOME/.local/bin"
mkdir -p "$share/prism-monitor" "$bin" "$share/applications"
if [ -x "$here/PrismMonitor" ]; then            # portable build
    rm -rf "$share/prism-monitor/app"
    cp -a "$here" "$share/prism-monitor/app"
    ln -sf "$share/prism-monitor/app/PrismMonitor" "$bin/prism-monitor"
    cp "$here/prism-monitor-run" "$bin/prism-monitor-run"
else                                             # source checkout
    root=$(dirname "$here")
    [ -x "$root/.venv/bin/python" ] || { python3 -m venv "$root/.venv" && "$root/.venv/bin/pip" install -q -r "$root/requirements.txt"; }
    printf '#!/bin/sh\nexec "%s/.venv/bin/python" "%s/main.py" "$@"\n' "$root" "$root" > "$bin/prism-monitor"
    chmod +x "$bin/prism-monitor"
    cp "$here/prism-monitor-run" "$bin/prism-monitor-run"
fi
chmod +x "$bin/prism-monitor-run"
cat > "$share/applications/prism-monitor.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Prism Monitor
Comment=Fan speed, game FPS and Bluetooth battery
Exec=$bin/prism-monitor
Icon=utilities-system-monitor
Categories=System;Monitor;
DESKTOP
echo "Installed. Start it from the app menu or run: prism-monitor"
command -v mangohud >/dev/null 2>&1 || echo "For game FPS also install MangoHud: sudo pacman -S mangohud lib32-mangohud"
