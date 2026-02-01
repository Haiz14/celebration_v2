#!/usr/bin/env python3
import os
import random
import subprocess
import sys
from pathlib import Path

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

def get_media_files(directory):
    """Get all media files from directory"""
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

def select_random_files(files, count=5):
    """Select random files from the list"""
    if len(files) <= count:
        return files.copy()
    return random.sample(files, count)

def play_file(file_path, play=True):
    """Play or stop media file using termux-media-player"""
    if play:
        subprocess.run(['termux-media-player', 'play', file_path])
    else:
        subprocess.run(['termux-media-player', 'stop'])

def show_file_list(files, current_index=None):
    """Display the list of files with current file highlighted"""
    os.system('clear' if os.name != 'nt' else 'cls')
    print("=" * 50)
    print(f"Media Player - {len(files)} files")
    print("=" * 50)
    
    for i, file_path in enumerate(files):
        prefix = "▶ " if i == current_index else "  "
        file_name = os.path.basename(file_path)
        print(f"{prefix}[{i+1}] {file_name}")
    
    print("=" * 50)
    print("Commands: n=next, p=previous, s=shuffle, q=quit")
    print("=" * 50)

def main():
    # Get SD card path
    sdcard_path = "/storage/6339-3135"
    if not sdcard_path:
        print("Could not find SD card path")
        sys.exit(1)
    
    # Define the celebration directory
    celebration_dir = os.path.join(sdcard_path, "celebration")
    
    # Get all media files
    all_files = get_media_files(celebration_dir)
    
    if not all_files:
        print(f"No media files found in {celebration_dir}")
        print("Supported formats: mp3, mp4, m4a, wav, aac, flac, ogg, mkv, avi, mov")
        sys.exit(1)
    
    print(f"Found {len(all_files)} media files")
    
    # Initial selection
    current_files = select_random_files(all_files, 5)
    current_index = 0
    current_process = None
    
    try:
        # Play first file
        if current_files:
            show_file_list(current_files, current_index)
            play_file(current_files[current_index])
        
        # Main control loop
        while True:
            command = input("\n> ").strip().lower()
            
            if command == 'q':
                print("Exiting...")
                subprocess.run(['termux-media-player', 'stop'])
                break
            
            elif command == 'n':  # Next
                if current_files:
                    subprocess.run(['termux-media-player', 'stop'])
                    current_index = (current_index + 1) % len(current_files)
                    show_file_list(current_files, current_index)
                    play_file(current_files[current_index])
            
            elif command == 'p':  # Previous
                if current_files:
                    subprocess.run(['termux-media-player', 'stop'])
                    current_index = (current_index - 1) % len(current_files)
                    show_file_list(current_files, current_index)
                    play_file(current_files[current_index])
            
            elif command == 's':  # Shuffle
                if current_files:
                    subprocess.run(['termux-media-player', 'stop'])
                current_files = select_random_files(all_files, 5)
                current_index = 0
                show_file_list(current_files, current_index)
                if current_files:
                    play_file(current_files[current_index])
            
            elif command.isdigit():  # Jump to specific track
                track_num = int(command) - 1
                if 0 <= track_num < len(current_files):
                    subprocess.run(['termux-media-player', 'stop'])
                    current_index = track_num
                    show_file_list(current_files, current_index)
                    play_file(current_files[current_index])
            
            else:
                print("Unknown command. Use: n=next, p=previous, s=shuffle, q=quit")
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        subprocess.run(['termux-media-player', 'stop'])
    except Exception as e:
        print(f"Error: {e}")
        subprocess.run(['termux-media-player', 'stop'])

if __name__ == "__main__":
    # Check if running on Termux
    if not os.path.exists('/data/data/com.termux/files/usr/bin/termux-media-player'):
        print("Warning: This script is designed for Termux on Android")
        print("Make sure you have termux-media-player installed:")
        print("pkg install termux-api")
    
    main()
