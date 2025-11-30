#!/usr/bin/env python3
"""
Plex Music Player - Terminal User Interface (TUI)

A spotify-tui inspired interface for Plex music playback.
Uses Textual framework for a modern, interactive terminal interface.

Usage:
    python3 plex-tui.py
"""

import sys
import os
import subprocess
import shutil
import platform
import random
import signal
import time
from typing import List, Optional, Dict
from plexapi.server import PlexServer
from plexapi.exceptions import NotFound

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header, Footer, Button, Input, Label, ListView, ListItem, 
    Static, ProgressBar, Log
)
from textual.binding import Binding

# Configuration
PLEX_BASE_URL = "https://plexserver.local/"
PLEX_TOKEN = "1234567890qwertyuiop"
PLAYER_CMD = "ffplay"
PLAYER_ARGS = ["-nodisp", "-autoexit", "-loglevel", "quiet"]

# Playlist loading settings
LARGE_PLAYLIST_THRESHOLD = 1000  # Use library method for playlists with more tracks than this
LARGE_PLAYLIST_LIMIT = 50  # Number of tracks to load for large playlists (reduced for speed)
REGULAR_PLAYLIST_LIMIT = 100  # Number of tracks to load for regular playlists
MAX_API_RESULTS = 1000  # Maximum results to request from API


class PlexTUI(App):
    """Main TUI application for Plex music player."""
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    #sidebar {
        width: 30%;
        background: $panel;
        border-right: wide $primary;
    }
    
    #main {
        width: 70%;
    }
    
    .track-item {
        padding: 1;
        border-bottom: solid $primary;
    }
    
    .track-item:hover {
        background: $primary 20%;
    }
    
    .now-playing {
        background: $accent;
        padding: 1;
        text-align: center;
    }
    
    #playlist-list {
        height: 1fr;
    }
    
    #track-list {
        height: 1fr;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("s", "search", "Search"),
        Binding("space", "play_pause", "Play/Pause"),
        Binding("enter", "load_playlist", "Load"),
        Binding("n", "next", "Next"),
        Binding("p", "previous", "Previous"),
        Binding("r", "random", "Random"),
    ]
    
    def __init__(self):
        super().__init__()
        self.plex = None
        self.music_library = None
        self.current_track = None
        self.current_playlist = []
        self.current_index = 0
        self.is_playing = False
        self.current_process = None
        self.playlists = []
        self.playlist_cache = {}  # Cache playlist titles/keys to avoid property access
        self.tracks_cache: Dict[str, List] = {}  # Cache loaded tracks by playlist ratingKey
        self.search_results = []
        self.current_view = "playlists"  # playlists, search, library
        self._highlighted_playlist = None
        self._highlighted_playlist_key = None
        self.debug_mode = True  # Set to False to disable debug output
    
    def on_mount(self) -> None:
        """Initialize the app."""
        self.title = "Plex Music Player"
        self.sub_title = "Loading..."
        self._connect_to_plex()
        self._load_playlists()
    
    def _connect_to_plex(self):
        """Connect to Plex server."""
        try:
            self.plex = PlexServer(PLEX_BASE_URL, PLEX_TOKEN)
            self.sub_title = f"Connected to {self.plex.friendlyName}"
            
            # Find music library
            for section in self.plex.library.sections():
                if section.type == 'artist':
                    self.music_library = section
                    break
        except Exception as e:
            self.sub_title = f"Error: {e}"
    
    def _load_playlists(self):
        """Load playlists from Plex."""
        try:
            # Get playlists iterator
            playlists_iter = self.plex.playlists()
            # Cache playlist data immediately to avoid property access during scrolling
            self.playlists = []
            self.playlist_cache = {}
            for playlist in playlists_iter:
                try:
                    # Cache title and key immediately - if this fails, skip the playlist
                    title = playlist.title if hasattr(playlist, 'title') else "Playlist"
                    rating_key = playlist.ratingKey if hasattr(playlist, 'ratingKey') else None
                    if rating_key:
                        self.playlists.append(playlist)
                        self.playlist_cache[str(rating_key)] = {
                            'title': title,
                            'playlist': playlist
                        }
                except Exception:
                    # Skip playlists that cause errors when accessing properties
                    continue
            self._update_playlist_list()
            self.sub_title = f"Loaded {len(self.playlists)} playlists"
        except Exception as e:
            self.sub_title = f"Error loading playlists: {e}"
    
    def _update_playlist_list(self):
        """Update the playlist list widget."""
        playlist_list = self.query_one("#playlist-list", ListView)
        playlist_list.clear()
        # Use cached data instead of accessing playlist properties
        for rating_key, cache_data in self.playlist_cache.items():
            try:
                title = cache_data['title']
                playlist_list.append(ListItem(Label(title), id=f"playlist-{rating_key}"))
            except Exception:
                continue
    
    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label("📋 Playlists")
                yield ListView(id="playlist-list")
                
                yield Label("🔍 Search")
                yield Input(placeholder="Search tracks...", id="search-input")
                yield ListView(id="search-results")
            
            with Vertical(id="main"):
                yield Static("Select a playlist or search for tracks", id="main-content")
                yield Static("", id="now-playing", classes="now-playing")
        
        yield Footer()
    
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle playlist selection."""
        if event.item.id and event.item.id.startswith("playlist-"):
            playlist_key = event.item.id.replace("playlist-", "")
            # Use cache to get playlist without accessing properties
            self._highlighted_playlist_key = playlist_key
            if playlist_key in self.playlist_cache:
                playlist = self.playlist_cache[playlist_key]['playlist']
                self._highlighted_playlist = playlist
                # Stop current playback if playing
                if self.current_process:
                    try:
                        self.current_process.terminate()
                        self.current_process = None
                        self.is_playing = False
                    except:
                        pass
                # Load the new playlist
                self._load_playlist_tracks(playlist)
            else:
                # Show clear message with actual keys if playlist not found
                try:
                    main_content = self.query_one("#main-content", Static)
                    main_content.update("Press [Spacebar] to play or [Enter] to load tracks")
                except:
                    pass
        elif event.item.id and event.item.id.startswith("track-"):
            track_key = event.item.id.replace("track-", "")
            self._play_track_by_key(track_key)
    
    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle when a playlist is highlighted (for spacebar to play)."""
        if event.item.id and event.item.id.startswith("playlist-"):
            playlist_key = event.item.id.replace("playlist-", "")
            # Store the key - use cache to get playlist object without accessing properties
            # This avoids any network calls during scrolling
            self._highlighted_playlist_key = playlist_key
            if playlist_key in self.playlist_cache:
                self._highlighted_playlist = self.playlist_cache[playlist_key]['playlist']
            else:
                # If not in cache, clear highlighted playlist to avoid errors
                self._highlighted_playlist = None
            # Show clear message with actual keys
            try:
                main_content = self.query_one("#main-content", Static)
                main_content.update("Press [Spacebar] to play or [Enter] to load tracks")
            except:
                pass
    
    def _load_playlist_tracks(self, playlist, limit=None):
        """Load tracks from a playlist (with limit for large playlists)."""
        try:
            start_time = time.time()
            playlist_key = str(playlist.ratingKey) if hasattr(playlist, 'ratingKey') else None
            playlist_title = getattr(playlist, 'title', '')
            
            # Check cache first
            if playlist_key and playlist_key in self.tracks_cache:
                if self.debug_mode:
                    self.sub_title = f"Using cached tracks (instant)"
                tracks = self.tracks_cache[playlist_key]
                self.current_playlist = tracks
                self.current_index = 0
                self._update_playlist_display(playlist, tracks, None)
                return
            
            # Try to get playlist count if available (for very large playlists)
            playlist_count = None
            try:
                # Check various attributes that might contain the count
                if hasattr(playlist, 'leafCount'):
                    playlist_count = playlist.leafCount
                elif hasattr(playlist, 'childCount'):
                    playlist_count = playlist.childCount
                elif hasattr(playlist, '_data') and playlist._data:
                    count_elem = playlist._data.find('leafCount')
                    if count_elem is not None and count_elem.text:
                        playlist_count = int(count_elem.text)
            except:
                pass
            
            # Determine limit based on playlist size
            is_large_playlist = playlist_count and playlist_count > LARGE_PLAYLIST_THRESHOLD
            if limit is None:
                limit = LARGE_PLAYLIST_LIMIT if is_large_playlist else REGULAR_PLAYLIST_LIMIT
            
            # Use API limit (cap at MAX_API_RESULTS)
            api_limit = min(limit, MAX_API_RESULTS)
            
            if is_large_playlist:
                if self.debug_mode:
                    self.sub_title = f"Large playlist detected ({playlist_count} tracks), loading {limit}..."
                else:
                    self.sub_title = f"Loading {limit} tracks (of {playlist_count})..."
            else:
                self.sub_title = "Loading tracks..."
            
            fetch_start = time.time()
            
            tracks = []
            collect_time = 0
            
            # Use library method for large playlists (faster and includes full metadata)
            # Threshold: use library method if playlist has more than LARGE_PLAYLIST_THRESHOLD tracks
            use_library_method = playlist_count and playlist_count > LARGE_PLAYLIST_THRESHOLD and self.music_library
            
            # Special case: "Recently Added" uses recentlyAdded() method if available
            if playlist_title and "Recently Added" in playlist_title and self.music_library:
                try:
                    collect_start = time.time()
                    try:
                        all_tracks = self.music_library.recentlyAdded(libtype='track', maxresults=api_limit)
                    except AttributeError:
                        # Fallback: use search with sort by addedAt
                        all_tracks = self.music_library.search(libtype='track', sort='addedAt:desc', maxresults=api_limit)
                    
                    for i, track in enumerate(all_tracks):
                        if i < limit:
                            tracks.append(track)
                        else:
                            break
                    collect_time = time.time() - collect_start
                except Exception as e:
                    if self.debug_mode:
                        self.sub_title = f"Library method failed: {e}, trying playlist..."
                    # Fall back to playlist method
                    items = playlist.items()
                    collect_start = time.time()
                    for i, track in enumerate(items):
                        if i < limit:
                            tracks.append(track)
                        else:
                            break
                    collect_time = time.time() - collect_start
            elif use_library_method:
                # For large playlists, use library search with no query to get limited results with full metadata
                # This is much faster than library.all() which iterates everything
                try:
                    collect_start = time.time()
                    # Use search with limit parameter - this limits at the API level, not client-side
                    # An empty query or '*' should return all tracks but with the limit applied
                    all_tracks = self.music_library.search(libtype='track', maxresults=api_limit)
                    tracks = list(all_tracks)
                    # Limit to the requested number if API returned more
                    if len(tracks) > limit:
                        tracks = tracks[:limit]
                    collect_time = time.time() - collect_start
                except Exception as e:
                    if self.debug_mode:
                        self.sub_title = f"Library search method failed: {e}, trying library.all()..."
                    # Fallback: try library.all() but break early
                    try:
                        collect_start = time.time()
                        all_tracks = self.music_library.all(libtype='track')
                        for i, track in enumerate(all_tracks):
                            if i < limit:
                                tracks.append(track)
                            else:
                                break
                        collect_time = time.time() - collect_start
                    except Exception as e2:
                        if self.debug_mode:
                            self.sub_title = f"Library.all() failed: {e2}, trying playlist..."
                        # Final fallback: use playlist method
                        items = playlist.items()
                        collect_start = time.time()
                        for i, track in enumerate(items):
                            if i < limit:
                                tracks.append(track)
                            else:
                                break
                        collect_time = time.time() - collect_start
            else:
                # Regular playlist - use items() method
                try:
                    items = playlist.items()
                    collect_start = time.time()
                    for i, track in enumerate(items):
                        if i < limit:
                            tracks.append(track)
                        else:
                            break
                    collect_time = time.time() - collect_start
                except Exception as e:
                    if self.debug_mode:
                        self.sub_title = f"Error fetching: {e}"
                    raise
            
            fetch_time = time.time() - fetch_start
            
            # Cache the tracks
            if playlist_key:
                self.tracks_cache[playlist_key] = tracks
            
            total_time = time.time() - start_time
            if self.debug_mode:
                count_info = f" (of {playlist_count})" if playlist_count else ""
                self.sub_title = f"Loaded {len(tracks)} tracks{count_info} ({total_time:.2f}s: fetch={fetch_time:.2f}s, collect={collect_time:.2f}s)"
            else:
                count_info = f" (of {playlist_count})" if playlist_count and is_large_playlist else ""
                self.sub_title = f"Loaded {len(tracks)} tracks{count_info}"
            
            self.current_playlist = tracks
            self.current_index = 0
            
            self._update_playlist_display(playlist, tracks, playlist_count)
        except Exception as e:
            self.sub_title = f"Error: {e}"
            main_content = self.query_one("#main-content", Static)
            main_content.update(f"Error loading playlist: {e}")
    
    def _get_artist_name(self, track):
        """Get artist name from track using multiple methods."""
        artist = None
        
        # Method 1: Try grandparentTitle attribute first (most reliable for music)
        if not artist:
            try:
                if hasattr(track, 'grandparentTitle') and track.grandparentTitle:
                    artist = str(track.grandparentTitle).strip()
            except:
                pass
        
        # Method 2: Check XML data directly (fastest, no API call)
        if not artist and hasattr(track, '_data') and track._data:
            try:
                # Try multiple XML paths
                for elem_name in ['grandparentTitle', 'originalTitle', 'parentTitle']:
                    artist_elem = track._data.find(elem_name)
                    if artist_elem is not None and artist_elem.text:
                        artist = artist_elem.text.strip()
                        break
            except:
                pass
        
        # Method 3: Try originalTitle
        if not artist:
            try:
                if hasattr(track, 'originalTitle') and track.originalTitle:
                    artist = str(track.originalTitle).strip()
            except:
                pass
        
        # Method 4: Try parentTitle (album name, but better than nothing)
        if not artist:
            try:
                if hasattr(track, 'parentTitle') and track.parentTitle:
                    artist = str(track.parentTitle).strip()
            except:
                pass
        
        # Method 5: Try reloading track if it's a cached object (for "All Music" playlist)
        # Only do this if we have a ratingKey and haven't found artist yet
        if not artist and hasattr(track, 'ratingKey'):
            try:
                # Reload the track to get full metadata - use includeChildren to get artist
                reloaded = self.plex.fetchItem(track.ratingKey, includeChildren=True)
                if hasattr(reloaded, 'grandparentTitle') and reloaded.grandparentTitle:
                    artist = str(reloaded.grandparentTitle).strip()
                elif hasattr(reloaded, '_data') and reloaded._data:
                    artist_elem = reloaded._data.find('grandparentTitle')
                    if artist_elem is not None and artist_elem.text:
                        artist = artist_elem.text.strip()
            except:
                pass
        
        # Method 6: Last resort - call artist() method (makes API call)
        if not artist:
            try:
                artist_obj = track.artist()
                if artist_obj:
                    artist = artist_obj.title if hasattr(artist_obj, 'title') else str(artist_obj)
                    artist = artist.strip() if artist else None
            except:
                pass
        
        return artist or 'Unknown'
    
    def _update_playlist_display(self, playlist, tracks, total_count=None):
        """Update the main content display with playlist tracks."""
        try:
            main_content = self.query_one("#main-content", Static)
            playlist_title = playlist.title if hasattr(playlist, 'title') else "Playlist"
            content = f"📋 {playlist_title}\n\n"
            
            # Show count info
            if total_count:
                content += f"Tracks: {len(tracks)} loaded (of {total_count:,} total)\n\n"
            else:
                content += f"Tracks: {len(tracks)} loaded\n\n"
            
            # Build display - get artist info efficiently
            display_start = time.time()
            track_lines = []
            for i, track in enumerate(tracks[:20], 1):
                try:
                    title = getattr(track, 'title', 'Unknown')
                    artist = self._get_artist_name(track)
                    track_lines.append(f"{i:2d}. {artist} - {title}")
                except Exception as e:
                    # If anything fails, just show title
                    title = getattr(track, 'title', 'Unknown')
                    track_lines.append(f"{i:2d}. Unknown - {title}")
            
            content += "\n".join(track_lines)
            display_time = time.time() - display_start
            if self.debug_mode and display_time > 0.1:
                content += f"\n\n[Debug: Display took {display_time:.2f}s]"
            
            if len(tracks) > 20:
                content += f"\n... and {len(tracks) - 20} more loaded tracks"
            if len(tracks) >= REGULAR_PLAYLIST_LIMIT:
                content += f"\n\n⚠️  Large playlist: Only first {len(tracks)} tracks loaded"
                content += f"\n   Press [r] to shuffle and play random tracks"
            
            main_content.update(content)
        except Exception as e:
            if self.debug_mode:
                self.sub_title = f"Display error: {e}"
    
    def _play_track_by_key(self, track_key):
        """Play a track by its key."""
        # Find track in current playlist or search results
        all_tracks = self.current_playlist + self.search_results
        track = next((t for t in all_tracks if str(t.ratingKey) == track_key), None)
        if track:
            self._play_track(track)
    
    def _play_track(self, track):
        """Play a single track."""
        try:
            stream_url = track.getStreamUrl() if hasattr(track, 'getStreamUrl') else None
            if not stream_url:
                # Fallback: construct URL manually
                if hasattr(track, 'media') and track.media:
                    media = track.media[0]
                    if media.parts:
                        part = media.parts[0]
                        key = part.key
                        token = self.plex._token
                        base_url = self.plex._baseurl.rstrip('/')
                        stream_url = f"{base_url}{key}?X-Plex-Token={token}"
            
            if not stream_url:
                self.sub_title = "Could not get stream URL"
                return
            
            # Get track info using helper function
            title = getattr(track, 'title', 'Unknown')
            artist = self._get_artist_name(track)
            
            # Update now playing
            now_playing = self.query_one("#now-playing", Static)
            now_playing.update(f"▶ {artist} - {title}")
            
            # Find player
            player_path = self._find_player(PLAYER_CMD)
            if not player_path:
                self.sub_title = "ffplay not found"
                return
            
            # Stop current playback
            if self.current_process:
                try:
                    self.current_process.terminate()
                except:
                    pass
            
            # Play track
            cmd = [player_path] + PLAYER_ARGS + [stream_url]
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            self.current_track = track
            self.is_playing = True
            self.sub_title = "Playing..."
            
        except Exception as e:
            self.sub_title = f"Error: {e}"
    
    def _find_player(self, player_cmd: str) -> Optional[str]:
        """Find the full path to a player command."""
        full_path = shutil.which(player_cmd)
        if full_path:
            return full_path
        
        if platform.system() == "Darwin":
            homebrew_paths = [
                "/opt/homebrew/bin",
                "/usr/local/bin",
            ]
            for brew_path in homebrew_paths:
                test_path = os.path.join(brew_path, player_cmd)
                if os.path.isfile(test_path) and os.access(test_path, os.X_OK):
                    return test_path
        
        return None
    
    def action_search(self) -> None:
        """Focus search input."""
        search_input = self.query_one("#search-input", Input)
        search_input.focus()
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search input."""
        if event.input.id == "search-input":
            query = event.value
            if query:
                self._search_tracks(query)
    
    def _search_tracks(self, query: str):
        """Search for tracks."""
        try:
            if self.music_library:
                results = self.music_library.search(title=query, libtype='track', limit=20)
            else:
                results = self.plex.library.search(title=query, libtype='track', limit=20)
            
            self.search_results = list(results)
            
            # Update search results list
            search_list = self.query_one("#search-results", ListView)
            search_list.clear()
            for track in self.search_results:
                # Use helper function to get artist
                title = getattr(track, 'title', 'Unknown')
                artist = self._get_artist_name(track)
                search_list.append(
                    ListItem(Label(f"{artist} - {title}"), id=f"track-{track.ratingKey}")
                )
            
            self.sub_title = f"Found {len(results)} tracks"
        except Exception as e:
            self.sub_title = f"Search error: {e}"
    
    def action_play_pause(self) -> None:
        """Toggle play/pause or start playing if nothing is playing."""
        # If something is already playing, toggle pause
        if self.current_process:
            try:
                # ffplay uses SIGUSR1 to toggle pause
                if platform.system() != "Windows":
                    self.current_process.send_signal(signal.SIGUSR1)
                    self.is_playing = not self.is_playing
                    status = "⏸ Paused" if not self.is_playing else "▶ Playing"
                    self.sub_title = status
            except:
                pass
        # If nothing is playing, start playing current playlist or highlighted playlist
        elif self.current_playlist:
            # Start playing from the beginning
            if self.current_playlist:
                self.current_index = 0
                self._play_track(self.current_playlist[0])
        elif self._highlighted_playlist:
            # Load and play highlighted playlist (with limit for large playlists)
            self._load_playlist_tracks(self._highlighted_playlist)
            if self.current_playlist:
                # Shuffle for large playlists to make it more interesting
                if len(self.current_playlist) > 50:
                    random.shuffle(self.current_playlist)
                    self.sub_title = "🔀 Shuffled and playing..."
                self.current_index = 0
                self._play_track(self.current_playlist[0])
    
    def action_next(self) -> None:
        """Play next track."""
        if self.current_playlist and self.current_index < len(self.current_playlist) - 1:
            self.current_index += 1
            self._play_track(self.current_playlist[self.current_index])
    
    def action_previous(self) -> None:
        """Play previous track."""
        if self.current_playlist and self.current_index > 0:
            self.current_index -= 1
            self._play_track(self.current_playlist[self.current_index])
    
    def action_load_playlist(self) -> None:
        """Load tracks from highlighted playlist."""
        if self._highlighted_playlist:
            self._load_playlist_tracks(self._highlighted_playlist)
        elif self._highlighted_playlist_key and self._highlighted_playlist_key in self.playlist_cache:
            # Fallback: get playlist from cache
            playlist = self.playlist_cache[self._highlighted_playlist_key]['playlist']
            self._highlighted_playlist = playlist
            self._load_playlist_tracks(playlist)
    
    def action_random(self) -> None:
        """Play random track from current playlist."""
        if self.current_playlist:
            random.shuffle(self.current_playlist)
            self.current_index = 0
            self._play_track(self.current_playlist[0])
            self.sub_title = "🔀 Shuffled"
    
    def action_quit(self) -> None:
        """Quit the application."""
        if self.current_process:
            try:
                self.current_process.terminate()
            except:
                pass
        self.exit()


def main():
    """Run the TUI application."""
    app = PlexTUI()
    app.run()


if __name__ == "__main__":
    main()

