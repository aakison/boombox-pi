#!/usr/bin/env python3
"""Scan /srv/music for MP3s and report tracks that share the same artist/title tag."""

import os
import sys
from collections import defaultdict

from mutagen.mp3 import MP3
from mutagen.id3 import ID3NoHeaderError

MUSIC_DIR = "/srv/music"


def _find_mp3_files(root_dir):
    """Recursively find all MP3 file paths under root_dir"""
    paths = []
    for root, _dirs, files in os.walk(root_dir):
        for name in files:
            if name.lower().endswith(".mp3"):
                paths.append(os.path.join(root, name))
    return paths


def _read_tags(path):
    """Return (artist, title) tags for an MP3 file, falling back to 'Unknown' when missing"""
    try:
        audio = MP3(path)
        artist = audio.get("TPE1")
        title = audio.get("TIT2")
        artist = str(artist.text[0]) if artist and artist.text else "Unknown Artist"
        title = str(title.text[0]) if title and title.text else "Unknown Title"
        return artist.strip(), title.strip()
    except ID3NoHeaderError:
        return "Unknown Artist", "Unknown Title"
    except Exception as err:
        print(f"  Warning: could not read tags from {path}: {err}")
        return "Unknown Artist", "Unknown Title"


def main():
    if not os.path.isdir(MUSIC_DIR):
        print(f"Music directory not found: {MUSIC_DIR}")
        sys.exit(1)

    print(f"Searching for MP3 files under {MUSIC_DIR}...")
    mp3_paths = _find_mp3_files(MUSIC_DIR)
    total = len(mp3_paths)
    print(f"Found {total} MP3 file(s). Scanning metadata...")

    tracks_by_key = defaultdict(list)
    for index, path in enumerate(mp3_paths, start=1):
        artist, title = _read_tags(path)
        tracks_by_key[(artist.lower(), title.lower())].append((artist, title, path))
        if index % 50 == 0 or index == total:
            print(f"  Scanned {index}/{total}")

    duplicates = {key: entries for key, entries in tracks_by_key.items() if len(entries) > 1}

    if not duplicates:
        print("\nNo duplicate tracks found.")
        return

    print(f"\nFound {len(duplicates)} duplicate track(s):\n")
    for key in sorted(duplicates):
        entries = duplicates[key]
        artist, title = entries[0][0], entries[0][1]
        print(f"{artist} / {title}")
        for _artist, _title, path in entries:
            print(f"  {path}")
        print()


if __name__ == "__main__":
    main()
