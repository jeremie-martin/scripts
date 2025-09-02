## Scripts — utility CLIs (modern Python package)

### Install
```bash
# base tools
uv pip install -e .

# with Jama tools
uv pip install -e .[jama]

# with media tools (yt-dlp, transcripts)
uv pip install -e .[media]

# everything
uv pip install -e .[full]
```

### Run
Discrete commands (installed via entry points):

```bash
concat …
transcript …          # requires [media] (default: 2 workers)
ffcut …               # requires ffmpeg + yt-dlp on PATH
gdiffpath …
import-photos …
jamaclean …           # requires [jama]
jamaconcat …          # requires [jama]
jamaconcatfull …      # requires [jama]
jamafilltests …       # requires [jama]
jamalinking …         # requires [jama]
jamalinkingfull …     # requires [jama]
jamanotest …          # requires [jama]
jamatmp …             # requires [jama]
2twi / img-twi …      # ImageMagick (writes to twi/, dir must pre-exist)
2work / img-work …    # ImageMagick (writes to ../working/, dir must pre-exist)
```

Umbrella wrapper (optional):

```bash
scripts list          # show available commands
scripts run concat -- <args>
scripts jama clean -- ABSD-SWVER-123
```

### Environment
Create `.env` in project root for Jama:
```bash
JAMA_URL=https://your-instance.jamacloud.com
CLIENT_ID=…
CLIENT_SECRET=…
```

> Note: No `setup_scripts.sh` needed — entry points handle global shims.
