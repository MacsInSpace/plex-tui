# Plex Music Player - Terminal User Interface (TUI)

A lightweight, terminal-based music player for Plex Media Server with a modern TUI interface inspired by `spotify-tui`.

## Features

- 🎵 **Browse Playlists** - Navigate and play from your Plex music playlists
- 🔍 **Search Tracks** - Quick search across your music library
- ⚡ **Fast Loading** - Optimized for large playlists (64k+ tracks)
- 🎨 **Modern TUI** - Clean, interactive terminal interface using Textual
- 🎮 **Keyboard Controls** - Full keyboard navigation and playback control
- 💾 **Smart Caching** - Instant reload of previously loaded playlists
- 🎲 **Shuffle Support** - Randomize and play tracks

## Requirements

- Python 3.9+
- `plexapi` library
- `textual` library (TUI framework)
- `ffplay` (part of ffmpeg) for audio playback

## Installation

1. **Install dependencies:**
   ```bash
   pip install plexapi textual
   ```

   Or using requirements.txt:
   ```bash
   pip install -r requirements.txt
   ```

2. **Install ffmpeg (includes ffplay):**
   - **macOS:** `brew install ffmpeg`
   - **Linux:** `apt install ffmpeg` or `yum install ffmpeg`

3. **Configure your Plex server:**
   Edit the configuration at the top of `plex-tui.py`:
   ```python
   PLEX_BASE_URL = "https://your-plex-server.com/"
   PLEX_TOKEN = "your-plex-token-here"
   ```

   To get your Plex token, see: https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/

## Usage

### Running the Player

```bash
python3 plex-tui.py
```

Or if executable:
```bash
./plex-tui.py
```

### Interface Overview

The TUI is divided into three main areas:

1. **Left Sidebar** - Playlists list and search
2. **Right Panel** - Track listing and now playing info
3. **Bottom Bar** - Keybindings reference

### Keybindings

| Key | Action |
|-----|--------|
| `↑` `↓` | Navigate playlists/tracks |
| `Enter` | Load selected playlist or play selected track |
| `Space` | Play/Pause current track or start playing highlighted playlist |
| `n` | Next track |
| `p` | Previous track |
| `r` | Shuffle current playlist |
| `s` | Focus search input |
| `q` | Quit |

### Playlist Navigation

1. **Browse Playlists:**
   - Use arrow keys to navigate the playlist list
   - Press `Enter` to load a playlist and see its tracks
   - Press `Space` to start playing a highlighted playlist

2. **Load Tracks:**
   - After loading a playlist, tracks are displayed in the main panel
   - Navigate tracks with arrow keys
   - Press `Enter` on a track to play it

3. **Large Playlists:**
   - Playlists with 1000+ tracks automatically use optimized loading
   - Only the first 50 tracks are loaded initially (configurable)
   - Full metadata (including artist names) is included

### Search

1. Press `s` to focus the search input
2. Type your search query
3. Press `Enter` to search
4. Results appear in the search results list
5. Navigate and press `Enter` to play a track

### Playback Controls

- **Play/Pause:** Press `Space` while a track is playing
- **Next Track:** Press `n`
- **Previous Track:** Press `p`
- **Shuffle:** Press `r` to randomize the current playlist

## Configuration

### Playlist Loading Settings

You can adjust these settings at the top of `plex-tui.py`:

```python
LARGE_PLAYLIST_THRESHOLD = 1000  # Use library method for playlists with more tracks than this
LARGE_PLAYLIST_LIMIT = 50  # Number of tracks to load for large playlists (reduced for speed)
REGULAR_PLAYLIST_LIMIT = 100  # Number of tracks to load for regular playlists
MAX_API_RESULTS = 1000  # Maximum results to request from API
```

### Player Settings

```python
PLAYER_CMD = "ffplay"  # Audio player command
PLAYER_ARGS = ["-nodisp", "-autoexit", "-loglevel", "quiet"]  # Player arguments
```

### Debug Mode

To see timing information and debug messages, set `debug_mode = True` in the `__init__` method (line ~108).

## Performance

The player is optimized for large music libraries:

- **Smart Loading:** Large playlists (>1000 tracks) use library methods instead of playlist iteration
- **Caching:** Loaded playlists are cached for instant reload
- **Limited Initial Load:** Only loads a subset of tracks initially to keep UI responsive
- **API Optimization:** Uses server-side limits to avoid fetching unnecessary data

For playlists with 64,000+ tracks, loading typically takes <1 second.

## Troubleshooting

### "ffplay not found"

Install ffmpeg:
- **macOS:** `brew install ffmpeg`
- **Linux:** `apt install ffmpeg`

The player will also check common Homebrew paths on macOS (`/opt/homebrew/bin`, `/usr/local/bin`).

### "Cannot connect to Plex"

1. Verify `PLEX_BASE_URL` is correct (include `https://` and trailing `/`)
2. Verify `PLEX_TOKEN` is valid
3. Check network connectivity to your Plex server

### Artists showing as "Unknown"

This typically happens with very large playlists. The player automatically uses optimized loading methods for playlists with 1000+ tracks, which includes full metadata. If you still see "Unknown", try:

1. Reload the playlist (it will use the optimized method)
2. Check that your Plex server has proper metadata for tracks

### Playlist loading is slow

- Large playlists automatically use optimized loading
- First load may be slower; subsequent loads use cache
- Check your network connection to the Plex server

## Technical Details

### Architecture

- **Framework:** Textual (Python TUI framework)
- **Plex API:** plexapi library
- **Audio Player:** ffplay (part of ffmpeg)
- **Threading:** Playback runs in background, controls are non-blocking

### Playlist Loading Strategy

1. **Small Playlists (<1000 tracks):** Uses `playlist.items()` method
2. **Large Playlists (>1000 tracks):** Uses `library.search()` with limit for faster loading
3. **Recently Added:** Uses `library.recentlyAdded()` method for optimal performance
4. **Caching:** All loaded tracks are cached by playlist ratingKey

### Artist Name Resolution

The player tries multiple methods to get artist names without making extra API calls:

1. Direct attribute access (`grandparentTitle`)
2. XML data parsing
3. Fallback to API call if needed

## License

This is a standalone script for personal use with your Plex Media Server.

## Credits

- Inspired by [spotify-tui](https://github.com/Rigellute/spotify-tui)
- Built with [Textual](https://github.com/Textualize/textual)
- Uses [plexapi](https://github.com/pkkid/python-plexapi)

