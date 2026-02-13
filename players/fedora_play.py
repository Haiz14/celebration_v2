#!/usr/bin/env python3

# Script searchs for file /home/haiz/Desktop/celebration for songs
# Uses ffplay to play song
import os
import random
import subprocess
import sys
from pathlib import Path

# Global to track the ffplay process
current_process = None

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
    
    return media_files

def play_file(file_path):
    """Starts playback in the background without blocking the CLI"""
    global current_process
    
    # Kill previous song if it's still playing
    if current_process and current_process.poll() is None:
        current_process.terminate()
        current_process.wait()

    # Launch ffplay as a background subprocess
    # -nodisp: no video window
    # -autoexit: close process when song ends
    current_process = subprocess.Popen(
        ['ffplay', '-nodisp', '-autoexit', file_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

def show_file_list(files, current_index):
    """Refresh the UI"""
    os.system('clear' if os.name != 'nt' else 'cls')
    print("=" * 50)
    print(f"  🎶  NOW PLAYING: {os.path.basename(files[current_index])}")
    print("=" * 50)
    
    for i, file_path in enumerate(files):
        prefix = "▶ " if i == current_index else "  "
        print(f"{prefix}[{i+1}] {os.path.basename(file_path)}")
    
    print("=" * 50)
    print(" [n] Next  [p] Prev  [s] Shuffle  [q] Quit")
    print("=" * 50)

def main():
    # Update this path to your celebration folder
    base_path = os.path.expanduser("~/Desktop/") 
    celebration_dir = os.path.join(base_path, "celebration")
    
    all_files = get_media_files(celebration_dir)
    
    if not all_files:
        print(f"No media found in {celebration_dir}")
        sys.exit(1)
    
    current_files = random.sample(all_files, min(len(all_files), 5))
    current_index = 0
    
    # Initial Start
    show_file_list(current_files, current_index)
    play_file(current_files[current_index])
    
    try:
        while True:
            cmd = input("\nSelect (n/p/s/q/1-5): ").strip().lower()
            
            if cmd == 'q':
                print("Stopping music and exiting...")
                break # Exit the while loop
            
            elif cmd == 'n':
                current_index = (current_index + 1) % len(current_files)
                show_file_list(current_files, current_index)
                play_file(current_files[current_index])
                
            elif cmd == 'p':
                current_index = (current_index - 1) % len(current_files)
                show_file_list(current_files, current_index)
                play_file(current_files[current_index])
                
            elif cmd == 's':
                current_files = random.sample(all_files, min(len(all_files), 5))
                current_index = 0
                show_file_list(current_files, current_index)
                play_file(current_files[current_index])
                
            elif cmd.isdigit():
                idx = int(cmd) - 1
                if 0 <= idx < len(current_files):
                    current_index = idx
                    show_file_list(current_files, current_index)
                    play_file(current_files[current_index])

    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        # CRITICAL: This kills the music when you press 'q' or Ctrl+C
        if current_process and current_process.poll() is None:
            current_process.terminate()
        print("Goodbye!")

if __name__ == "__main__":
    main()