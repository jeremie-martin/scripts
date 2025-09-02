#!/bin/bash
# Setup script for making scripts available globally

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "🚀 Setting up scripts for global usage..."
echo "📁 Script directory: $SCRIPT_DIR"
echo "🐍 Virtual environment: $VENV_DIR"

# Create a wrapper script that activates venv and runs commands
cat > "$HOME/.local/bin/scripts-runner" << EOF
#!/bin/bash
# Scripts runner - activates virtual environment and runs commands

SCRIPT_DIR="$SCRIPT_DIR"
VENV_DIR="$VENV_DIR"

# Load environment variables from .env if it exists
if [ -f "\$SCRIPT_DIR/.env" ]; then
    export \$(grep -v '^#' "\$SCRIPT_DIR/.env" | xargs 2>/dev/null)
fi

# Activate virtual environment
source "\$VENV_DIR/bin/activate"

# Run the requested command
exec "\$@"
EOF

chmod +x "$HOME/.local/bin/scripts-runner"

# Create individual command wrappers
COMMANDS=("concat" "transcript" "jamaclean" "jamaconcat" "jamaconcatfull" "jamafilltests" "jamalinking" "jamalinkingfull" "jamanotest" "jamatmp")

for cmd in "${COMMANDS[@]}"; do
    cat > "$HOME/.local/bin/$cmd" << EOF
#!/bin/bash
# $cmd wrapper

exec "$HOME/.local/bin/scripts-runner" "$cmd" "\$@"
EOF
    chmod +x "$HOME/.local/bin/$cmd"
done

echo "✅ Setup complete!"
echo ""
echo "📋 Available commands:"
for cmd in "${COMMANDS[@]}"; do
    echo "   $cmd"
done
echo ""
echo "💡 Usage examples:"
echo "   concat --help"
echo "   transcript https://youtu.be/VIDEO_ID"
echo "   jamaclean ABSD-SWVER-123"
echo ""
echo "🔧 Environment variables are automatically loaded from:"
echo "   $SCRIPT_DIR/.env"
echo ""
echo "📝 To update your environment variables, edit:"
echo "   $SCRIPT_DIR/.env"
