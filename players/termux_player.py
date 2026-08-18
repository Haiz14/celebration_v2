#!/usr/bin/env python3

# Script searches parent directory of this script or Android SD card for songs
# Uses ffplay to play songs, with automatic advancement and optional duration limits.
import os
import random
import subprocess
import sys
import select
import shutil
import argparse
from pathlib import Path

# Global to track the ffplay process
current_process = None

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
            return path
    return None

def check_and_install_dependencies():
    """Ensure ffplay is installed, and if not, try to install it on Termux."""
    if shutil.which('ffplay') is not None:
        return

    print("ffplay not found! Attempting to install missing media libraries on Termux...")
    if shutil.which('pkg') is not None:
        try:
            print("Installing ffmpeg via pkg...")
            subprocess.run(['pkg', 'install', '-y', 'ffmpeg'], check=True)
        except Exception as e:
            print(f"Error attempting to run pkg: {e}")
            sys.exit(1)
    elif shutil.which('apt') is not None:
        try:
            print("Installing ffmpeg via apt...")
            subprocess.run(['apt', 'update'], check=False)
            subprocess.run(['apt', 'install', '-y', 'ffmpeg'], check=True)
        except Exception as e:
            print(f"Error attempting to run apt: {e}")
            sys.exit(1)
    else:
        print("Could not find a supported package manager (pkg, apt).")
        print("Please install ffmpeg manually in Termux using: pkg install ffmpeg")
        sys.exit(1)

    if shutil.which('ffplay') is None:
        print("Failed to verify ffplay installation. Please install ffmpeg manually.")
        sys.exit(1)
    else:
        print("Successfully installed ffplay!")

def get_media_files(directory):
    """Scan directory for audio/video files"""
    media_extensions = {'.mp3', '.mp4', '.m4a', '.wav', '.aac', '.flac', '.ogg', '.mkv', '.avi', '.mov'}
    media_files = []
    
    if not os.path.exists(directory):
        print(f"Directory not found: {directory}")
        return []
    
    for file in os.listdir(directory):
        file_path = os.path.join(directory, file)
        if os.path.isfile(file_path) and Path(file).suffix.lower() in media_extensions:
            media_files.append(file_path)
    
    return sorted(media_files)

def play_file(file_path, duration=None):
    """Starts playback in the background without blocking the CLI"""
    global current_process
    
    # Kill previous song if it's still playing
    if current_process and current_process.poll() is None:
        current_process.terminate()
        current_process.wait()

    # Launch ffplay as a background subprocess
    # -nodisp: no video window
    # -autoexit: close process when song ends
    cmd = ['ffplay', '-nodisp', '-autoexit']
    if duration is not None:
        cmd.extend(['-t', str(duration)])
    cmd.append(file_path)

    current_process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

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
    parser = argparse.ArgumentParser(description="Termux Media Player using ffmpeg/ffplay.")
    parser.add_argument('--duration', type=int, default=None, help="Duration (in seconds) to play each song.")
    args = parser.parse_args()
    
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
        # Fallback to parent directory of this script
        script_dir = Path(__file__).resolve().parent
        celebration_dir = script_dir.parent
    
    all_files = get_media_files(celebration_dir)
    
    if not all_files:
        print(f"No media found in {celebration_dir}")
        sys.exit(1)
    
    current_files = random.sample(all_files, min(len(all_files), 5))
    current_index = 0
    
    # Initial Start
    show_file_list(current_files, current_index, args.duration)
    play_file(current_files[current_index], args.duration)
    
    print_prompt()
    
    try:
        while True:
            # Check if the process has exited (song completed or duration elapsed)
            if current_process and current_process.poll() is not None:
                current_index = (current_index + 1) % len(current_files)
                show_file_list(current_files, current_index, args.duration)
                play_file(current_files[current_index], args.duration)
                print_prompt()
                continue
                
            # Wait for user input with timeout (0.1 seconds)
            rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
            if rlist:
                line = sys.stdin.readline()
                if not line: # EOF
                    break
                cmd = line.strip().lower()
                
                if not cmd:
                    # User pressed Enter, just re-prompt
                    print_prompt()
                    continue
                
                if cmd == 'q':
                    print("Stopping music and exiting...")
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
                    print_prompt()
                else:
                    print("Invalid command.")
                    print_prompt()

    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        # CRITICAL: This kills the music when you press 'q' or Ctrl+C
        if current_process and current_process.poll() is None:
            current_process.terminate()
        print("Goodbye!")

if __name__ == "__main__":
    main()
