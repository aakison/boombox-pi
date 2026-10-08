#!/usr/bin/env python3
"""Deletes MP3 files logged as skipped by mp3_player.py, then clears the log.

Tracks that fail to delete (e.g. the file is locked/in use) are kept in the
log so a later run can retry them. Tracks already missing from disk are
simply dropped from the log.
"""
import os

# Must match the paths used in mp3_player.py
MUSIC_DIR = "/srv/music"
SKIP_TRACKS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mp3_player_skip_tracks")


def expunge_skipped():
    try:
        with open(SKIP_TRACKS_FILE, "r") as f:
            tracks = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"No skip log found at {SKIP_TRACKS_FILE!r}")
        return

    remaining = []
    seen = set()
    for track in tracks:
        if track in seen:
            continue
        seen.add(track)

        full_path = os.path.join(MUSIC_DIR, track)
        try:
            os.remove(full_path)
            print(f"Deleted: {track}")
        except FileNotFoundError:
            print(f"Already gone: {track}")
        except OSError as e:
            print(f"Could not delete {track!r} (left in skip log): {e}")
            remaining.append(track)

    with open(SKIP_TRACKS_FILE, "w") as f:
        for track in remaining:
            f.write(track + "\n")


if __name__ == "__main__":
    expunge_skipped()
