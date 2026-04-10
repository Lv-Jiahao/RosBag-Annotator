#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# RosBag Annotator — one-click install
# Usage:  bash install.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_DIR/.venv"

echo "==> Checking Python >= 3.10"
python3 -c "import sys; assert sys.version_info >= (3,10), 'Python 3.10+ required'"

echo "==> Creating virtual environment at $VENV_DIR"
python3 -m venv "$VENV_DIR"

echo "==> Upgrading pip"
"$VENV_DIR/bin/pip" install --upgrade pip

echo "==> Installing Python dependencies"
"$VENV_DIR/bin/pip" install PyQt6 pyyaml numpy opencv-python

# ── ROS 2 optional deps ──────────────────────────────────────────────────────
# rosbag2_py and rclpy must come from the ROS 2 environment.
# Source your ROS setup before running the tool if you need them:
#   source /opt/ros/<distro>/setup.bash

echo "==> Installing rosbag_annotator package (editable)"
"$VENV_DIR/bin/pip" install -e "$REPO_DIR"

# ── create launcher script ───────────────────────────────────────────────────
LAUNCHER="$REPO_DIR/run.sh"
cat > "$LAUNCHER" <<'EOF'
#!/usr/bin/env bash
# Launch RosBag Annotator
# Optionally source ROS 2 before this script for rosbag2_py support:
#   source /opt/ros/<distro>/setup.bash && bash run.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/main.py" "$@"
EOF
chmod +x "$LAUNCHER"

echo ""
echo "✅  Installation complete!"
echo ""
echo "   Run the tool:"
echo "     bash run.sh"
echo ""
echo "   (Optional) With ROS 2 support:"
echo "     source /opt/ros/<distro>/setup.bash && bash run.sh"
echo ""
