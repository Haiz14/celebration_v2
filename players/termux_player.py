#v!/usr/bin/env python3

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
from pathlib import Path

# Track active timer thread
timer_thread = None

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

def get_media_files(directory):
    """Scan directory for audio/video files"""
    media_extensions = {'.mp3', '.mp4', '.m4a', '.wav', '.aac', '.flac', '.ogg', '.mkv', '.avi', '.mov'}
    media_files = []
    
    logging.debug(f"Scanning directory for media files: {directory}")
    if not os.path.exists(directory):
        logging.warning(f"Directory not found: {directory}")
        return []
    
    for file in os.listdir(directory):
        file_path = os.path.join(directory, file)
        if os.path.isfile(file_path) and Path(file).suffix.lower() in media_extensions:
            media_files.append(file_path)
    
    logging.debug(f"Scan complete. Found {len(media_files)} matching files.")
    return sorted(media_files)

def stop_playback():
    """Stops current playback using termux-media-player"""
    logging.debug("Executing: termux-media-player stop")
    subprocess.run(['termux-media-player', 'stop'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def play_file(file_path, duration=None):
    """Starts playback using termux-media-player, sleeping for duration if set"""
    global timer_thread
    
    # Always stop current playing track before starting a new one
    stop_playback()

    logging.debug(f"Executing: termux-media-player play {file_path}")
    subprocess.run(
        ['termux-media-player', 'play', file_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # If a duration limit is set, handle sleep and stop in a background thread
    if duration is not None and duration > 0:
        def duration_worker(req_duration, target_file):
            logging.debug(f"Duration worker thread started: Sleeping for {req_duration}s for {os.path.basename(target_file)}")
            time.sleep(req_duration)
            logging.debug(f"Duration time limit ({req_duration}s) reached. Triggering stop.")
            stop_playback()

        timer_thread = threading.Thread(target=duration_worker, args=(duration, file_path), daemon=True)
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

def show_file_list(files, current_index, duration=None):
    """Refresh the UI"""
    os.system('clear' if os.name != 'nt' else 'cls')
    print("=" * 50)
    print(f"  🎶  NOW PLAYING: {os.path.basename(files[current_index])}")
    if duration is not None:
        print(f"  ⏱   Duration Limit: {duration} seconds")
    print("=" * 50)
    
    for i, file_path in enumerate(files):
        prefix = "▶ " if i == current_index else "  "
        print(f"{prefix}[{i+1}] {os.path.basename(file_path)}")
    
    print("=" * 50)
    print(" [n] Next  [p] Prev  [s] Shuffle  [q] Quit")
    print("=" * 50)

def print_prompt():
    """Print the interactive command prompt"""
    sys.stdout.write("\nSelect (n/p/s/q/1-5): ")
    sys.stdout.flush()

def main():
    parser = argparse.ArgumentParser(description="Termux Media Player using termux-api.")
    parser.add_argument('--duration', type=int, default=None, help="Duration (in seconds) to play each song.")
    parser.add_argument('--log-level', type=str, default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help="Set verbosity level for logging (default: INFO). Use DEBUG for detailed logs.")
    args = parser.parse_args()
    
    # Initialize logging configuration
    setup_logging(args.log_level)
    
    # Verify/Install required dependencies
    check_and_install_dependencies()
    
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
    
    all_files = get_media_files(celebration_dir)
    
    if not all_files:
        logging.error(f"No media files found in {celebration_dir}")
        sys.exit(1)
    
    current_files = random.sample(all_files, min(len(all_files), 5))
    current_index = 0
    
    logging.debug(f"Loaded playlist sample: {[os.path.basename(f) for f in current_files]}")

    # Initial Start
    show_file_list(current_files, current_index, args.duration)
    play_file(current_files[current_index], args.duration)
    
    print_prompt()
    
    try:
        while True:
            time.sleep(0.5)

            # Check if track has stopped playing naturally or via duration thread
            if not is_playing():
                logging.debug("Track ended or stopped. Advancing to next track.")
                current_index = (current_index + 1) % len(current_files)
                show_file_list(current_files, current_index, args.duration)
                play_file(current_files[current_index], args.duration)
                print_prompt()
                continue
                
            # Wait for user input with timeout
            rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
            if rlist:
                line = sys.stdin.readline()
                if not line:
                    break
                cmd = line.strip().lower()
                logging.debug(f"User input command received: '{cmd}'")
                
                if not cmd:
                    print_prompt()
                    continue
                
                if cmd == 'q':
                    logging.info("User requested quit ('q'). Exiting main loop.")
                    break
                
                elif cmd == 'n':
                    current_index = (current_index + 1) % len(current_files)
                    show_file_list(current_files, current_index, args.duration)
                    play_file(current_files[current_index], args.duration)
                    print_prompt()
                    
                elif cmd == 'p':
                    current_index = (current_index - 1) % len(current_files)
                    show_file_list(current_files, current_index, args.duration)
                    play_file(current_files[current_index], args.duration)
                    print_prompt()
                    
                elif cmd == 's':
                    logging.debug("Reshuffling track list...")
                    current_files = random.sample(all_files, min(len(all_files), 5))
                    current_index = 0
                    show_file_list(current_files, current_index, args.duration)
                    play_file(current_files[current_index], args.duration)
                    print_prompt()
                    
                elif cmd.isdigit():
                    idx = int(cmd) - 1
                    if 0 <= idx < len(current_files):
                        current_index = idx
                        show_file_list(current_files, current_index, args.duration)
                        play_file(current_files[current_index], args.duration)
                    else:
                        logging.debug(f"Invalid numeric input {cmd}: Out of bounds.")
                    print_prompt()
                else:
                    logging.debug(f"Unrecognized command: '{cmd}'")
                    print_prompt()

    except KeyboardInterrupt:
        logging.info("Received KeyboardInterrupt (Ctrl+C).")
    finally:
        logging.debug("Cleaning up playback before script exit...")
        stop_playback()
        print("\nGoodbye!")

if __name__ == "__main__":
    main()

