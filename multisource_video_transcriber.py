import subprocess
import sys
import os
import logging
from tqdm import tqdm
import json
import time
import warnings
import hashlib
from datetime import timedelta
from termcolor import colored
import torch
import re
import yt_dlp

# Set up logging
log_file = 'transcription_debug.log'
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename=log_file,
    filemode='w'  # 'w' mode overwrites the file each time
)

# Add a stream handler for WARNING and above to show these in console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
logging.getLogger('').addHandler(console_handler)

# Suppress warnings
warnings.filterwarnings("ignore")

def check_dependencies():
    dependencies = [
        "whisper",
        "yt_dlp",
        "tqdm",
        "termcolor",
        "torch"
    ]
    missing = []

    for dep in dependencies:
        try:
            __import__(dep)
        except ImportError:
            missing.append(dep)

    if missing:
        logging.error(f"Missing dependencies: {', '.join(missing)}")
        print("Some dependencies are missing. Please run the dependency installer script first.")
        print("Missing dependencies:", ", ".join(missing))
        print("Run: python install_dependencies.py")
        sys.exit(1)

    # Check for ffmpeg
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        logging.error("FFmpeg is not installed or not in the system PATH.")
        print("FFmpeg is not installed or not in the system PATH.")
        print("Please install FFmpeg and make sure it's in your system PATH.")
        print("You can download it from: https://ffmpeg.org/download.html")
        sys.exit(1)

import whisper

class TqdmProgressBar(object):
    def __init__(self, file_num, total_files):
        self._pbar = None
        self.file_num = file_num
        self.total_files = total_files

    def __call__(self, d):
        if d['status'] == 'downloading':
            if self._pbar is None:
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                self._pbar = tqdm(total=total, unit='B', unit_scale=True, 
                                  desc=f"Downloading file {self.file_num}/{self.total_files}")
            downloaded = d.get('downloaded_bytes', 0)
            self._pbar.update(downloaded - self._pbar.n)
        elif d['status'] == 'finished':
            if self._pbar is not None:
                self._pbar.close()
            print(f"Extracting audio for file {self.file_num}/{self.total_files}...")

def find_firefox_profile():
    """Find the Firefox profile directory automatically"""
    possible_paths = [
        # macOS
        os.path.expanduser("~/Library/Application Support/Firefox/Profiles"),
        # Linux
        os.path.expanduser("~/.mozilla/firefox"),
        # Windows
        os.path.expanduser(r"~\AppData\Roaming\Mozilla\Firefox\Profiles")
    ]
    
    profiles = []
    for base_path in possible_paths:
        if os.path.exists(base_path):
            print(f"\nFound Firefox profiles directory: {base_path}")
            # List all profiles
            for profile in os.listdir(base_path):
                profile_path = os.path.join(base_path, profile)
                if os.path.isdir(profile_path):
                    print(f"Found profile: {profile}")
                    profiles.append(profile_path)
    
    if not profiles:
        print("No Firefox profiles found!")
        return None
    
    print("\nAvailable Firefox profiles:")
    for i, profile in enumerate(profiles, 1):
        print(f"{i}. {os.path.basename(profile)}")
    
    while True:
        try:
            choice = input("\nChoose a profile number (or press Enter to skip using cookies): ").strip()
            if not choice:  # If user just presses Enter
                print("Skipping cookie usage.")
                return None  # Return None to indicate no profile selected
            
            choice = int(choice)
            if 1 <= choice <= len(profiles):
                selected_profile = profiles[choice - 1]
                print(f"Using profile: {os.path.basename(selected_profile)}")
                return selected_profile
            else:
                print(f"Please enter a number between 1 and {len(profiles)}")
        except ValueError:
            print("Please enter a valid number")

def check_url(url, firefox_profile=None):
    """Check if a URL is downloadable with yt-dlp (using minimal options)"""
    # Minimal options for checking URL validity, closer to CLI defaults
    ydl_opts = {
        'simulate': True,
        'verbose': True,
        'no_playlist': True,  # Still useful to prevent accidental playlist downloads
        'ignoreconfig': True, # Keep this from previous debugging
        'cachedir': False,    # Keep this from previous debugging
        # Removed: format, quiet, no_warnings, ignoreerrors, extract_flat,
        #          youtube_include_dash_manifest, http_headers, extractor_args,
        #          socket_timeout, retries
    }

    # Add cookies from Firefox if profile path exists
    if firefox_profile:
        ydl_opts['cookiesfrombrowser'] = ('firefox', firefox_profile)
        print(f"Using Firefox profile: {firefox_profile}")

    try:
        print(f"Checking URL with options: {ydl_opts}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("Attempting to extract video info...")
            info = ydl.extract_info(url, download=False)
            if info:
                print("Successfully extracted video info")
                return True
            else:
                logging.warning(f"Unable to extract info from URL: {url}")
                return False
    except Exception as e:
        logging.error(f"Error checking URL {url}: {str(e)}")
        print(f"Detailed error: {str(e)}")
        return False

def test_ffprobe(file_path):
    command = ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_name', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        print(f"FFprobe test output: {result.stdout.strip()}")
        logging.info(f"FFprobe test output: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        print(f"FFprobe test error: {e.stderr.strip()}")
        logging.error(f"FFprobe test error: {e.stderr.strip()}")

def download_audio(url, output_path, file_num, total_files, firefox_profile=None, max_retries=3, delay=5):
    """Download audio from a video URL with retries"""
    # Simplified options, keeping only essentials for download/postprocessing
    output_dir = os.path.dirname(output_path)
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(output_dir, '%(uploader)s_%(id)s_%(title)s.%(ext)s'),
        'progress_hooks': [TqdmProgressBar(file_num, total_files)],
        'verbose': True,
        'no_playlist': True,
        'ignoreconfig': True,
        'cachedir': False,
        # Removed: quiet, no_warnings, ignoreerrors, nocheckcertificate, 
        #          youtube_include_dash_manifest, extract_flat, 
        #          writesubtitles, writeautomaticsub, http_headers, 
        #          extractor_args, socket_timeout, retries 
        #          (using script's retry logic instead)
    }

    if firefox_profile:
        ydl_opts['cookiesfrombrowser'] = ('firefox', firefox_profile)
        print(f"Using Firefox profile: {firefox_profile}")

    print(f"yt-dlp version: {yt_dlp.version.__version__}")
    
    for attempt in range(max_retries):
        try:
            print(f"Attempting download {attempt + 1}/{max_retries}")
            print(f"Attempting to download to: {output_dir}")
            logging.info(f"Attempting to download to: {output_dir}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url)
                filename = ydl.prepare_filename(info)
                # Get the actual output filename (after conversion to m4a)
                actual_filename = os.path.splitext(filename)[0] + '.m4a'
                
                if os.path.exists(actual_filename):
                    print(f"Download completed. File saved as: {actual_filename}")
                    return actual_filename
            
            if attempt < max_retries - 1:
                print(f"Waiting {delay} seconds before retrying...")
                time.sleep(delay)
        except Exception as e:
            logging.error(f"Download attempt {attempt + 1} failed: {str(e)}")
            print(f"Download attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                print(f"Waiting {delay} seconds before retrying...")
                time.sleep(delay)
    
    raise Exception(f"Failed to download audio after {max_retries} attempts.")

def get_audio_duration(file_path):
    """Get the duration of an audio file using ffprobe"""
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    return float(result.stdout)

def choose_whisper_model():
    models = ["tiny", "base", "small", "medium", "large"]
    print("Available Whisper models:")
    for i, model in enumerate(models, 1):
        print(f"{i}. {model}")
    while True:
        choice = input("Choose a model (1-5): ")
        try:
            index = int(choice) - 1
            if 0 <= index < len(models):
                return models[index]
            else:
                print("Invalid choice. Please enter a number between 1 and 5.")
        except ValueError:
            print("Invalid input. Please enter a number.")

def transcribe_audio(audio_file, file_num, total_files, model_name):
    """Transcribe audio file using Whisper"""
    try:
        if not os.path.exists(audio_file):
            logging.error(f"Audio file not found: {audio_file}")
            print(f"Audio file not found: {audio_file}")
            raise FileNotFoundError(f"Audio file not found: {audio_file}")
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = whisper.load_model(model_name).to(device)
        
        logging.info(f"Transcribing file {file_num}/{total_files}: {audio_file}")
        print(f"Transcribing file {file_num}/{total_files}: {audio_file}")
        print(f"Using device: {device}")
        print(f"Using Whisper model: {model_name}")
        print("Whisper transcription in progress...")
        
        start_time = time.time()
        result = model.transcribe(audio_file, verbose=True)
        end_time = time.time()
        
        transcription_time = end_time - start_time
        audio_duration = get_audio_duration(audio_file)
        
        # Create transcript filename based on audio filename
        base_name = os.path.splitext(audio_file)[0]  # Remove .m4a extension
        transcript_path = f"{base_name}_transcript.txt"
        
        # Save the transcript
        with open(transcript_path, "w") as f:
            f.write(result["text"])
        print(f"Transcript saved as: {transcript_path}")
        
        logging.info(f"Transcription of file {file_num}/{total_files} complete.")
        print(f"Transcription of file {file_num}/{total_files} complete.")
        
        return result["text"], transcription_time, audio_duration
    except Exception as e:
        logging.error(f"Error transcribing {audio_file}: {str(e)}")
        raise

def save_processed_urls(urls):
    """Save the processed URLs to a file"""
    try:
        with open('processed_urls.json', 'w') as f:
            json.dump(urls, f)
    except Exception as e:
        logging.error(f"Error saving processed URLs: {str(e)}")
        print(f"Warning: Could not save processed URLs: {str(e)}")

def load_processed_urls():
    """Load the previously processed URLs from a file"""
    try:
        with open('processed_urls.json', 'r') as f:
            content = f.read().strip()
            if content:  # Only try to parse if file has content
                return json.load(f)
            return None
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def generate_url_hash(urls):
    """Generate a hash of the URLs to quickly compare sets of URLs"""
    return hashlib.md5(','.join(sorted(urls)).encode()).hexdigest()

def get_video_title(url):
    """Extract video title and original filename from the URL"""
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # For Facebook videos, create a more meaningful filename
            if 'facebook.com' in url:
                # Extract video ID from URL
                video_id = url.split('/')[-1].split('?')[0]
                
                # Try to get metadata
                uploader = info.get('uploader', '')
                title = info.get('title', '')
                upload_date = info.get('upload_date', '')
                
                # Clean up title (remove "Facebook video" if it's the default)
                if title == "Facebook video":
                    title = ''
                
                # Build filename parts
                parts = []
                if uploader:
                    parts.append(uploader)
                if title:
                    parts.append(title)
                if upload_date:
                    parts.append(upload_date)
                parts.append(f"fb_{video_id}")  # Always include video ID with prefix
                
                # Join parts with underscores and clean up
                filename = '_'.join(parts)
                # Remove any problematic characters
                filename = re.sub(r'[<>:"/\\|?*]', '', filename)
                # Replace multiple underscores with single
                filename = re.sub(r'_+', '_', filename)
                # Remove leading/trailing underscores
                filename = filename.strip('_')
                
                return filename
            
            # For other platforms, try original filename first
            filename = info.get('_filename', '')
            if filename:
                filename = os.path.splitext(filename)[0]
                return filename
            
            # Fallback to title
            title = info.get('title', '')
            if title:
                return title
            
            # Last resort
            return 'video'
    except Exception as e:
        logging.error(f"Error extracting video title: {str(e)}")
        return 'video'

# ... (rest of the code)

def simplify_filename(title):
    """Simplify and shorten the filename"""
    # Remove special characters and spaces
    simplified = re.sub(r'[^\w\-_\. ]', '', title)
    # Replace spaces with underscores
    simplified = simplified.replace(' ', '_')
    # Remove trailing underscores
    simplified = simplified.rstrip('_')
    # If the simplified title is longer than 50 characters, truncate it
    # and ensure it doesn't end with an underscore
    if len(simplified) > 50:
        simplified = simplified[:50].rstrip('_')
    return simplified

def load_urls_from_file(filename):
    """Load URLs from a text file, one URL per line"""
    try:
        with open(filename, 'r') as f:
            urls = [line.strip() for line in f if line.strip()]
        return urls
    except FileNotFoundError:
        return None

def download_video(url, output_path, file_num, total_files, firefox_profile=None, max_retries=3, delay=5):
    """Download video in MP4 format"""
    # Simplified options, keeping only essentials for download/merging
    output_dir = os.path.dirname(output_path)
    ydl_opts = {
        'format': 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4] / bv*+ba/b',
        'merge_output_format': 'mp4',
        'outtmpl': os.path.join(output_dir, '%(uploader)s_%(id)s_%(title)s.%(ext)s'),
        'progress_hooks': [TqdmProgressBar(file_num, total_files)],
        'verbose': True,
        'no_playlist': True,
        'ignoreconfig': True,
        'cachedir': False,
        # Removed: quiet, no_warnings, ignoreerrors, nocheckcertificate, 
        #          http_headers, extractor_args, socket_timeout, retries
        #          (using script's retry logic instead)
    }

    if firefox_profile:
        ydl_opts['cookiesfrombrowser'] = ('firefox', firefox_profile)
        print(f"Using Firefox profile: {firefox_profile}")

    print(f"yt-dlp version: {yt_dlp.version.__version__}")
    
    for attempt in range(max_retries):
        try:
            print(f"Attempting download {attempt + 1}/{max_retries}")
            print(f"Attempting to download to: {output_dir}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url)
                filename = ydl.prepare_filename(info)
                ydl.download([url])
                
                if os.path.exists(filename):
                    print(f"Download completed. File saved as: {filename}")
                    return filename
            
            if attempt < max_retries - 1:
                print(f"Waiting {delay} seconds before retrying...")
                time.sleep(delay)
        except Exception as e:
            logging.error(f"Download attempt {attempt + 1} failed: {str(e)}")
            print(f"Download attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                print(f"Waiting {delay} seconds before retrying...")
                time.sleep(delay)
    
    raise Exception(f"Failed to download video after {max_retries} attempts")

def main():
    logging.info("Starting the process")
    check_dependencies()
    
    current_dir = os.getcwd()
    logging.info(f"Current working directory: {current_dir}")
    
    # Ask for mode
    print("\nChoose mode:")
    print("1. Download and transcribe audio")
    print("2. Download video only (QuickTime compatible MP4)")
    while True:
        mode = input("Enter mode (1 or 2): ").strip()
        if mode in ['1', '2']:
            break
        print("Please enter 1 or 2")
    
    # Create appropriate output directory
    if mode == '1':
        output_dir = os.path.join(current_dir, "transcription_output")
    else:
        output_dir = os.path.join(current_dir, "video_output")
    os.makedirs(output_dir, exist_ok=True)
    logging.info(f"Created output directory: {output_dir}")
    
    # Check for URLs file
    urls_file = os.path.join(current_dir, "urls.txt")
    urls = load_urls_from_file(urls_file)
    
    if urls is None:
        print("No urls.txt file found. Please enter URLs manually.")
        urls = []
        while True:
            url = input("Enter a video URL (or press Enter to finish): ")
            if url == "":
                break
            urls.append(url)
    else:
        print(f"Found {len(urls)} URLs in urls.txt")
        print("URLs found:")
        for url in urls:
            print(f"  {url}")
        use_file = input("Use these URLs? (y/n): ").lower().strip()
        if use_file != 'y':
            print("Please enter URLs manually:")
            urls = []
            while True:
                url = input("Enter a video URL (or press Enter to finish): ")
                if url == "":
                    break
                urls.append(url)

    if not urls:
        logging.error("No URLs provided. Exiting.")
        print("No URLs provided. Exiting.")
        return

    whisper_model = choose_whisper_model()
    logging.info(f"Chosen Whisper model: {whisper_model}")

    firefox_profile = find_firefox_profile()  # Get Firefox profile once
    
    logging.info("Checking URLs...")
    print("Checking URLs...")
    valid_urls = []
    for url in urls:
        if check_url(url, firefox_profile):
            valid_urls.append(url)
            logging.info(f"URL is valid: {url}")
            print(f"URL is valid: {url}")
        else:
            logging.warning(f"Unable to download from URL: {url}")
            print(f"Unable to download from URL: {url}")
    
    if not valid_urls:
        logging.error("No valid URLs provided. Exiting.")
        print("No valid URLs provided. Exiting.")
        return

    if mode == '2':
        # Video download mode
        total_files = len(valid_urls)
        logging.info(f"Downloading {total_files} videos...")
        print(f"Downloading {total_files} videos...")
        for i, url in enumerate(valid_urls, 1):
            try:
                output_path = os.path.join(output_dir, "temp.mp4")  # This is just a placeholder now
                actual_path = download_video(url, output_path, i, total_files, firefox_profile)
                print(f"Successfully downloaded: {actual_path}")
                logging.info(f"Successfully downloaded: {actual_path}")
            except Exception as e:
                logging.error(f"Error downloading video from {url}: {str(e)}")
                print(f"Error downloading video from {url}")
        return

    # Audio transcription mode
    current_url_hash = generate_url_hash(valid_urls)
    previous_urls = load_processed_urls()

    combined_transcript_file = os.path.join(output_dir, "combined_transcription.txt")
    transcription_exists = False

    if previous_urls and current_url_hash == previous_urls['hash']:
        print("Same URLs as previous run detected. Checking for existing transcription.")
        logging.info("Same URLs as previous run detected. Checking for existing transcription.")
        
        if os.path.exists(combined_transcript_file):
            print(f"Existing combined transcription found at: {os.path.abspath(combined_transcript_file)}")
            transcription_exists = True
        else:
            logging.error(f"Previous combined transcription file {combined_transcript_file} not found.")
            print(f"Previous combined transcription file {combined_transcript_file} not found.")
            print("Will proceed with download and transcription.")

    if not transcription_exists:
        total_files = len(valid_urls)
        logging.info(f"Downloading and extracting audio for {total_files} files...")
        print(f"Downloading and extracting audio for {total_files} files...")
        audio_files = []
        for i, url in enumerate(valid_urls, 1):
            try:
                output_path = os.path.join(output_dir, "temp.m4a")  # Temporary path
                actual_path = download_audio(url, output_path, i, total_files, firefox_profile)
                audio_files.append((actual_path, url))
            except Exception as e:
                logging.error(f"Error downloading audio from {url}: {str(e)}")
                print(f"Error downloading audio from {url}")

        if not audio_files:
            logging.error("No audio files were successfully downloaded. Exiting.")
            print("No audio files were successfully downloaded. Exiting.")
            return

        logging.info(f"Transcribing {len(audio_files)} audio files...")
        print(f"Transcribing {len(audio_files)} audio files...")
        transcriptions = []
        total_transcription_time = 0
        total_audio_duration = 0
        
        for i, (audio_file, url) in enumerate(audio_files, 1):
            try:
                transcription, transcription_time, audio_duration = transcribe_audio(audio_file, i, len(audio_files), whisper_model)
                transcriptions.append(transcription)
                total_transcription_time += transcription_time
                total_audio_duration += audio_duration
                logging.info(f"Successfully transcribed: {audio_file}")
            except Exception as e:
                logging.error(f"Error transcribing {audio_file}: {str(e)}")
                print(f"Error transcribing {audio_file}")

        if not transcriptions:
            logging.error("No transcriptions were successfully generated. Exiting.")
            print("No transcriptions were successfully generated. Exiting.")
            return

        logging.info("Concatenating transcriptions...")
        full_transcription = "\n\n".join(transcriptions)
        
        # Save combined transcript
        with open(combined_transcript_file, "w") as f:
            f.write(full_transcription)

        # Save the processed URLs
        save_processed_urls({'hash': current_url_hash, 'urls': valid_urls})

        # Cleanup audio files
        for audio_file, _ in audio_files:
            if os.path.exists(audio_file):
                os.remove(audio_file)
                logging.info(f"Removed temporary file: {audio_file}")
            else:
                logging.warning(f"Could not find temporary file to remove: {audio_file}")

        print(f"\nCombined transcript saved to: {os.path.abspath(combined_transcript_file)}")

        # Calculate and print timing information
        speed_factor = total_audio_duration / total_transcription_time
        print("\nTranscription process completed.")
        print(colored(f"Total transcription time: {timedelta(seconds=int(total_transcription_time))}", "green"))
        print(colored(f"Total audio duration: {timedelta(seconds=int(total_audio_duration))}", "green"))
        print(colored(f"Transcription speed: {speed_factor:.2f}x real-time", "green"))

    else:
        print("\nTranscription process completed.")
        print(colored("Using existing transcription. No timing information available.", "green"))

    print(f"Individual transcripts are available in: {os.path.abspath(output_dir)}")
    print("You can use these files for summarization with ClaudeAI, ChatGPT, or the Conversational AI of your choice.")

    logging.info("Transcription process completed")

if __name__ == "__main__":
    main()