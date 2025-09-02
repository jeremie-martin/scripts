# Scripts Collection - Modern Python Package

This is a modern Python package containing a collection of utility scripts for development and automation. The package uses `uv` for dependency management and provides global command-line access to all scripts.

## 🏗️ Project Structure

The project has been modernized with:
- **Standard Python package structure** (`src/scripts/`)
- **uv-based dependency management**
- **Global command-line access** via entry points
- **Environment variable configuration**
- **Professional development setup**

## 📦 Installation & Setup

### Prerequisites
- Python 3.8+
- [uv](https://github.com/astral-sh/uv) package manager

### One-Time Setup
```bash
# Navigate to the scripts directory
cd /path/to/scripts

# Install dependencies and package
uv pip install -e .

# Set up global command access
./setup_scripts.sh
```

## 🚀 Usage

### Available Commands

Once set up, these commands are available globally:

**File Processing:**
- `concat` - Concatenate files matching patterns
- `transcript` - Download YouTube video transcripts

**Jama API Tools:**
- `jamaclean` - Clean HTML descriptions in Jama
- `jamaconcat` - Concatenate Jama item descriptions
- `jamaconcatfull` - Full Jama structure inspection
- `jamafilltests` - Fill empty test fields in Jama
- `jamalinking` - Create Jama requirement links
- `jamalinkingfull` - Create comprehensive Jama links
- `jamanotest` - Test coverage analysis
- `jamatmp` - Temporary Jama linking operations

### Usage Examples

```bash
# File concatenation
concat "*.py" -o combined.py
concat "*.md" -o docs.md --exclude "node_modules"

# YouTube transcripts
transcript https://youtu.be/VIDEO_ID
transcript -t https://youtu.be/VIDEO_ID  # Print to terminal

# Jama operations (requires environment variables)
jamaclean ABSD-SWVER-123
jamaconcat ABSD-SWVER-124 --version
```

## 🔐 Environment Configuration

### Jama API Credentials

Create or edit the `.env` file in the project root:

```bash
# Jama API Configuration
JAMA_URL=https://your-instance.jamacloud.com
CLIENT_ID=your_client_id_here
CLIENT_SECRET=your_client_secret_here
```

### Automatic Environment Loading

The setup script automatically loads environment variables from `.env` when running commands. No manual activation required!

## 🛠️ Development

### Adding New Scripts

1. Create your script in `src/scripts/your_script.py`
2. Add a `main()` function
3. Update `pyproject.toml` to include the entry point:
   ```toml
   [project.scripts]
   your_script = "scripts.your_script:main"
   ```
4. Reinstall: `uv pip install -e .`
5. Run setup: `./setup_scripts.sh`

### Dependencies

Add new dependencies:
```bash
uv add package_name
```

## 📁 File Organization

```
/home/holo/.local/bin/scripts/
├── .env                    # Environment variables (private)
├── .gitignore             # Git ignore rules
├── pyproject.toml         # Package configuration
├── setup_scripts.sh       # Global setup script
├── API_SETUP_README.md    # This documentation
├── src/
│   └── scripts/
│       ├── __init__.py
│       ├── concat.py      # File concatenation
│       ├── transcript.py  # YouTube transcripts
│       ├── jamaclean.py   # Jama HTML cleaner
│       └── ...            # Other scripts
└── .venv/                 # Virtual environment (managed by uv)
```

## 🔒 Security

- **Never commit `.env`** - It contains sensitive credentials
- **Environment variables** are loaded automatically
- **Virtual environment** isolates dependencies
- **Entry points** provide secure command access

## 🎯 Benefits of This Setup

✅ **Future-proof** - No hardcoded paths or user-specific references
✅ **Standard** - Follows modern Python packaging practices
✅ **Secure** - Credentials stored in environment variables
✅ **Global access** - Commands work from anywhere
✅ **Dependency managed** - uv handles all package management
✅ **Maintainable** - Clean separation of concerns
✅ **GitHub ready** - Professional project structure

## 🔄 Migration from Old Setup

The old executable scripts (with `#!/home/holo/.local/bin/.venv/bin/python`) have been replaced with:

1. **Proper Python modules** in `src/scripts/`
2. **Standard shebang** (`#!/usr/bin/env python3`)
3. **Entry points** for global command access
4. **Environment variables** for configuration

## 📚 Command Reference

### concat
```bash
concat [OPTIONS] PATTERN

Options:
  -o OUTPUT        Output file path (required)
  -p PATH         Search path (default: current directory)
  --exclude TEXT  Exclude pattern
  --separator TEXT Separator between files
  --list-only     Only list files, don't concatenate
```

### transcript
```bash
transcript [OPTIONS] [URLS ...]

Options:
  -t, --terminal  Print to terminal instead of clipboard
  -w, --workers   Number of worker threads (default: 2)
```

### Jama Commands
All Jama commands require environment variables to be set:
```bash
jamaclean [OPTIONS] JAMA_KEY [JAMA_KEY ...]
jamaconcat [OPTIONS] JAMA_KEY [JAMA_KEY ...]
# ... etc
```

## 🆘 Troubleshooting

**Commands not found:**
```bash
./setup_scripts.sh  # Re-run setup
```

**Environment variables not loaded:**
- Check `.env` file exists and has correct format
- Verify variables are exported: `echo $JAMA_URL`

**Permission denied:**
```bash
chmod +x ~/.local/bin/jamaclean
```

**Python path issues:**
```bash
uv pip install -e .  # Reinstall package
```
