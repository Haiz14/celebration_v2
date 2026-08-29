#!/usr/bin/env python3

# Script searches parent directory of this script or Android SD card for songs
# Uses termux-media-player to play songs, with automatic advancement, duration limits, and logging.
import os
import random
import subprocess
import sys
import select
import shutil
import argparse
import time
import threading
import logging
import signal
import termios
import tty
from pathlib import Path

# Track active timer thread + a generation counter so stale timers don't
# stop a track that has since changed.
timer_thread = None
play_generation = 0
paused = False

# New state for elapsed time and track length
play_start_time = None
elapsed_before_pause = 0.0
track_length = None
duration_cache = {}


def setup_logging(log_level_str):
    """Configures Python logging based on user CLI argument."""
    numeric_level = getattr(logging, log_level_str.upper(), None)
    if not isinstance(numeric_level, int):
        print(f"Invalid log level: {log_level_str}. Defaulting to INFO.")
        numeric_level = logging.INFO

    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    logging.debug(f"Logging initialized at level: {logging.getLevelName(numeric_level)}")


def format_time(seconds):
    """Format seconds into mm:ss or h:mm:ss."""
    if seconds is None:
        return "--:--"

    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "--:--"

    if seconds < 0:
        seconds = 0

    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)

    if h:
        return f"{h}:{m:02d}:{s:02d}"

    return f"{m}:{s:02d}"


def get_track_duration(file_path):
    """
    Uses ffprobe from ffmpeg to get track duration in seconds.
    Returns None if ffprobe is unavailable or duration cannot be read.
    """
    if shutil.which('ffprobe') is None:
        return None

    key = os.path.abspath(file_path)
    if key in duration_cache:
        return duration_cache[key]

    commands = [
        # Normal container/format duration
        [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path
        ],
        # Fallback: first audio stream duration
        [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'a:0',
            '-show_entries', 'stream=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path
        ],
    ]

    for cmd in commands:
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )

            value = res.stdout.strip()
            if value and value != "N/A":
                duration = float(value)
                if duration > 0:
                    duration_cache[key] = duration
                    return duration

        except Exception as e:
            logging.debug(f"ffprobe duration check failed for {file_path}: {e}")

    duration_cache[key] = None
    return None


def get_elapsed():
    """Return elapsed playback time for the current track, respecting pause."""
    if paused or play_start_time is None:
        return elapsed_before_pause

    return elapsed_before_pause + (time.time() - play_start_time)


def cancel_duration_timer():
    """
    Cancels any pending duration stop for the current playback instance.
    This lets the current track continue until it naturally ends.
    """
    global play_generation
    play_generation += 1
    logging.debug("Duration timer canceled by generation increment.")


def get_sdcard_path():
    """Get the SD card path - common locations on Android"""
    possible_paths = [
        "/storage/emulated/6339-6135",
        "/storage/emulated/0",
        "/sdcard",
        "/storage/sdcard0",
        "/mnt/sdcard"
    ]

    for path in possible_paths:
        if os.path.exists(path):
            logging.debug(f"Found SD card path at: {path}")
            return path

    logging.debug("No valid SD card path found among default checks.")
    return None


def check_and_install_dependencies():
    """Ensure termux-media-player (termux-api) is installed."""
    if shutil.which('termux-media-player') is not None:
        logging.debug("Dependency check passed: 'termux-media-player' exists in PATH.")
        return

    logging.info("termux-media-player not found! Attempting to install termux-api package...")

    if shutil.which('pkg') is not None:
        try:
            logging.debug("Executing 'pkg install -y termux-api'...")
            subprocess.run(['pkg', 'install', '-y', 'termux-api'], check=True)
        except Exception as e:
            logging.error(f"Error attempting to run pkg: {e}")
            sys.exit(1)

    elif shutil.which('apt') is not None:
        try:
            logging.debug("Executing 'apt update' and 'apt install -y termux-api'...")
            subprocess.run(['apt', 'update'], check=False)
            subprocess.run(['apt', 'install', '-y', 'termux-api'], check=True)
        except Exception as e:
            logging.error(f"Error attempting to run apt: {e}")
            sys.exit(1)

    else:
        logging.error("Could not find a supported package manager (pkg, apt).")
        sys.exit(1)

    if shutil.which('termux-media-player') is None:
        logging.error("Failed to verify termux-media-player installation.")
        sys.exit(1)
    else:
        logging.info("Successfully installed termux-api!")


def get_media_files(directory, recursive=False):
    """Scan directory for audio/video files"""
    media_extensions = {'.mp3', '.mp4', '.m4a', '.wav', '.aac', '.flac', '.ogg', '.mkv', '.avi', '.mov'}
    media_files = []

    logging.debug(f"Scanning directory for media files: {directory} (recursive={recursive})")

    if not os.path.exists(directory):
        logging.warning(f"Directory not found: {directory}")
        return []

    if recursive:
        for root, _dirs, files in os.walk(directory):
            for file in files:
                if Path(file).suffix.lower() in media_extensions:
                    media_files.append(os.path.join(root, file))
    else:
        for file in os.listdir(directory):
            file_path = os.path.join(directory, file)
            if os.path.isfile(file_path) and Path(file).suffix.lower() in media_extensions:
                media_files.append(file_path)

    logging.debug(f"Scan complete. Found {len(media_files)} matching files.")
    return sorted(media_files)


def stop_playback():
    """Stops current playback using termux-media-player"""
    logging.debug("Executing: termux-media-player stop")
    subprocess.run(
        ['termux-media-player', 'stop'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


def pause_playback():
    """Pause playback and freeze elapsed time."""
    global paused, play_start_time, elapsed_before_pause

    logging.debug("Executing: termux-media-player pause")
    subprocess.run(
        ['termux-media-player', 'pause'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    if not paused and play_start_time is not None:
        elapsed_before_pause += time.time() - play_start_time
        play_start_time = None

    paused = True


def resume_playback():
    """Resume playback and continue elapsed time."""
    global paused, play_start_time

    logging.debug("Executing: termux-media-player play")
    subprocess.run(
        ['termux-media-player', 'play'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    if paused:
        play_start_time = time.time()

    paused = False


def play_file(file_path, duration=None):
    """Starts playback using termux-media-player, sleeping for duration if set."""
    global timer_thread, play_generation, paused
    global play_start_time, elapsed_before_pause, track_length

    # Always stop current playing track before starting a new one
    stop_playback()
    paused = False
    play_generation += 1
    my_generation = play_generation

    # Get track length before starting playback, if ffprobe is available
    track_length = get_track_duration(file_path)

    logging.debug(f"Executing: termux-media-player play {file_path}")
    result = subprocess.run(
        ['termux-media-player', 'play', file_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    if result.returncode != 0:
        logging.error(f"Failed to start playback for {file_path} (exit code {result.returncode})")
        play_start_time = None
        elapsed_before_pause = 0.0
        track_length = None
        return

    play_start_time = time.time()
    elapsed_before_pause = 0.0

    logging.info(f"Now playing: {os.path.basename(file_path)}")

    # If a duration limit is set, handle sleep and stop in a background thread.
    # Guard with the generation counter so a stale timer from a previous
    # track can't stop a track that started after it.
    if duration is not None and duration > 0:
        def duration_worker(req_duration, target_file, generation):
            logging.debug(
                f"Duration worker thread started: Sleeping for {req_duration}s "
                f"for {os.path.basename(target_file)}"
            )
            time.sleep(req_duration)

            if generation != play_generation:
                logging.debug("Duration worker stale (track already changed); skipping stop.")
                return

            logging.debug(f"Duration time limit ({req_duration}s) reached. Triggering stop.")
            stop_playback()

        timer_thread = threading.Thread(
            target=duration_worker,
            args=(duration, file_path, my_generation),
            daemon=True
        )
        timer_thread.start()


def is_playing():
    """Check if termux-media-player is currently playing media"""
    try:
        res = subprocess.run(
            ['termux-media-player', 'info'],
            capture_output=True,
            text=True
        )
        status_playing = "Playing" in res.stdout
        logging.debug(f"Playback status check: is_playing={status_playing} (raw='{res.stdout.strip()}')")
        return status_playing
    except Exception as e:
        logging.error(f"Failed to query player status: {e}")
        return False


def show_file_list(files, current_index, duration=None, repeat=False,
                   full_once=False, full_loop=False, elapsed=None, total=None):
    """Refresh the UI"""
    os.system('clear' if os.name != 'nt' else 'cls')

    print("=" * 50)
    print(f"  \U0001F3B6  NOW PLAYING: {os.path.basename(files[current_index])}")
    print(f"  \u23F1   Time: {format_time(elapsed)} / {format_time(total)}")

    if full_loop:
        print("  \U0001F501  Full Loop: ON (full track, infinite)")
    elif full_once:
        print("  \U0001F3B5  Full Play: ON (this instance only)")

    if duration is not None and duration > 0:
        if full_loop or full_once:
            print(f"  \u23F1   Duration Limit: {duration} seconds (overridden)")
        else:
            print(f"  \u23F1   Duration Limit: {duration} seconds")

    if repeat:
        print("  \U0001F501  Repeat: ON (current track)")

    print("=" * 50)

    for i, file_path in enumerate(files):
        prefix = "\u25B6 " if i == current_index else "  "
        print(f"{prefix}[{i+1}] {os.path.basename(file_path)}")

    print("=" * 50)
    print(" [n] Next  [p] Prev  [s] Shuffle  [space] Pause/Resume")
    print(" [f] Full once  [l] Full loop  [r] Repeat  [q] Quit")
    print("=" * 50)


def print_prompt():
    """Print the interactive command prompt"""
    sys.stdout.write("\nSelect (n/p/s/r/f/l/space/q/1-5): ")
    sys.stdout.flush()


def read_key(timeout=0.1):
    """Read a single keypress (non-blocking, with timeout) from stdin.
    Returns None if no key was pressed within the timeout. Requires stdin
    to be a real tty; falls back to line-buffered input otherwise."""
    if not sys.stdin.isatty():
        rlist, _, _ = select.select([sys.stdin], [], [], timeout)
        if rlist:
            line = sys.stdin.readline()
            return line.strip().lower() if line else None
        return None

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setcbreak(fd)
        rlist, _, _ = select.select([sys.stdin], [], [], timeout)
        if rlist:
            ch = sys.stdin.read(1)
            return ch.lower()
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def main():
    global paused

    parser = argparse.ArgumentParser(description="Termux Media Player using termux-api.")
    parser.add_argument('--duration', type=int, default=None, help="Duration (in seconds) to play each song.")
    parser.add_argument('--playlist-size', type=int, default=5, help="Number of tracks to sample into the active playlist (default: 5).")
    parser.add_argument('--recursive', action='store_true', help="Scan the media directory recursively (include subfolders).")
    parser.add_argument('--log-level', type=str, default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help="Set verbosity level for logging (default: INFO). Use DEBUG for detailed logs.")
    args = parser.parse_args()

    # Initialize logging configuration
    setup_logging(args.log_level)

    # Ensure playback is stopped on termination signals too, not just Ctrl+C.
    def handle_sigterm(signum, frame):
        logging.info("Received SIGTERM. Stopping playback and exiting.")
        stop_playback()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)

    # Verify/Install required dependencies
    check_and_install_dependencies()

    # Optional warning for track length support
    if shutil.which('ffprobe') is None:
        logging.warning("ffprobe not found. Install ffmpeg to display track lengths.")

    # Get SD card path
    sdcard_path = "/storage/6339-3135"
    if not os.path.exists(sdcard_path):
        fallback = get_sdcard_path()
        if fallback:
            sdcard_path = fallback

    # Define the celebration directory
    celebration_dir = os.path.join(sdcard_path, "celebration")
    if not os.path.exists(celebration_dir):
        script_dir = Path(__file__).resolve().parent
        celebration_dir = script_dir.parent
        logging.debug(f"Target folder fallback to: {celebration_dir}")

    all_files = get_media_files(celebration_dir, recursive=args.recursive)

    if not all_files:
        logging.error(f"No media files found in {celebration_dir}")
        sys.exit(1)

    playlist_size = max(1, args.playlist_size)
    current_files = random.sample(all_files, min(len(all_files), playlist_size))
    current_index = 0
    history = []  # stack of previously visited indices, for real "prev"
    repeat_current = False

    # New full-duration modes
    full_once = False
    full_loop = False

    logging.debug(f"Loaded playlist sample: {[os.path.basename(f) for f in current_files]}")

    def render():
        show_file_list(
            current_files,
            current_index,
            args.duration,
            repeat_current,
            full_once,
            full_loop,
            get_elapsed(),
            track_length
        )

    def goto(index, record_history=True):
        nonlocal current_index, full_once, full_loop

        if record_history:
            history.append(current_index)

        current_index = index

        # Changing tracks cancels special full-track modes
        full_once = False
        full_loop = False

        play_file(current_files[current_index], args.duration)

    # Initial Start
    play_file(current_files[current_index], args.duration)
    render()
    print_prompt()

    try:
        while True:
            # Check if track has stopped playing naturally or via duration thread
            if not paused and not is_playing():
                if full_loop:
                    logging.debug("Track ended. Full loop is ON. Replaying full track.")
                    play_file(current_files[current_index], None)
                    continue

                if full_once:
                    logging.debug("Full-duration single playback finished.")
                    full_once = False

                    if repeat_current:
                        play_file(current_files[current_index], args.duration)
                    else:
                        goto((current_index + 1) % len(current_files))

                    continue

                if repeat_current:
                    logging.debug("Track ended. Repeat is ON, replaying current track.")
                    play_file(current_files[current_index], args.duration)
                    continue

                logging.debug("Track ended. Advancing to next track.")
                goto((current_index + 1) % len(current_files))
                continue

            # Refresh UI continuously so elapsed time updates
            render()
            print_prompt()

            cmd = read_key(timeout=0.3)
            if cmd is None:
                continue

            logging.debug(f"User input command received: '{cmd}'")

            if cmd in ('', '\n', '\r'):
                continue

            if cmd == 'q':
                logging.info("User requested quit ('q'). Exiting main loop.")
                break

            elif cmd == 'n':
                goto((current_index + 1) % len(current_files))

            elif cmd == 'p':
                if history:
                    prev_index = history.pop()
                    current_index = prev_index

                    # Changing tracks cancels special full-track modes
                    full_once = False
                    full_loop = False

                    play_file(current_files[current_index], args.duration)
                else:
                    goto((current_index - 1) % len(current_files), record_history=False)

            elif cmd == 's':
                logging.debug("Reshuffling track list...")

                current_files = random.sample(all_files, min(len(all_files), playlist_size))
                current_index = 0
                history.clear()

                # Shuffle cancels special full-track modes
                full_once = False
                full_loop = False

                play_file(current_files[current_index], args.duration)

            elif cmd == 'r':
                repeat_current = not repeat_current
                logging.info(f"Repeat toggled {'ON' if repeat_current else 'OFF'}.")

            elif cmd == ' ':
                if paused:
                    resume_playback()
                    logging.info("Playback resumed.")
                else:
                    pause_playback()
                    logging.info("Playback paused.")

            elif cmd == 'f':
                full_once = True
                full_loop = False
                cancel_duration_timer()

                logging.info("Full-duration play enabled for current track (once).")

                # If playback is somehow stopped, start the current track fully.
                if not paused and not is_playing():
                    play_file(current_files[current_index], None)

            elif cmd == 'l':
                full_loop = not full_loop

                if full_loop:
                    full_once = False
                    cancel_duration_timer()

                    logging.info("Full-duration infinite loop ON for current track.")

                    # If playback is somehow stopped, start the current track fully.
                    if not paused and not is_playing():
                        play_file(current_files[current_index], None)
                else:
                    logging.info("Full-duration infinite loop OFF.")

            elif cmd.isdigit():
                idx = int(cmd) - 1
                if 0 <= idx < len(current_files):
                    goto(idx)
                else:
                    logging.debug(f"Invalid numeric input {cmd}: Out of bounds.")

            else:
                logging.debug(f"Unrecognized command: '{cmd}'")

    except KeyboardInterrupt:
        logging.info("Received KeyboardInterrupt (Ctrl+C).")
    finally:
        logging.debug("Cleaning up playback before script exit...")
        stop_playback()
        print("\nGoodbye!")


if __name__ == "__main__":
    main()
