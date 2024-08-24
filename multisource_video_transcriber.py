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

def check_url(url):
    """Check if a URL is downloadable with yt-dlp"""
    ydl_opts = {
        'simulate': True,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                return True
            else:
                logging.warning(f"Unable to extract info from URL: {url}")
                return False
    except Exception as e:
        logging.error(f"Error checking URL {url}: {str(e)}")
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

def download_audio(url, output_path, file_num, total_files, max_retries=3, delay=5):
    """Download audio from a video URL with retries"""
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
            'preferredquality': '192',
        }],
        'outtmpl': output_path,
        'progress_hooks': [TqdmProgressBar(file_num, total_files)],
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'no_warnings': True,
        'quiet': True,
        'verbose': False,
    }

    for attempt in range(max_retries):
        try:
            print(f"Attempting to download to: {output_path}")
            logging.info(f"Attempting to download to: {output_path}")
            
            dir_path = os.path.dirname(output_path)
            is_writable = os.access(dir_path, os.W_OK)
            print(f"Directory path: {dir_path}")
            print(f"Directory writable: {is_writable}")
            logging.info(f"Directory path: {dir_path}")
            logging.info(f"Directory writable: {is_writable}")
            
            if not is_writable:
                print(f"Attempting to create directory: {dir_path}")
                logging.info(f"Attempting to create directory: {dir_path}")
                os.makedirs(dir_path, exist_ok=True)
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            print(f"Download completed. Checking file...")
            logging.info(f"Download completed. Checking file...")
            
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                print(f"File exists after download: True")
                print(f"File size after download: {file_size} bytes")
                logging.info(f"File exists after download: True")
                logging.info(f"File size after download: {file_size} bytes")
            else:
                print(f"File does not exist after download: {output_path}")
                logging.warning(f"File does not exist after download: {output_path}")
                
                # Check if file exists with an additional extension
                if os.path.exists(output_path + '.m4a'):
                    print(f"File exists with additional .m4a extension")
                    logging.info(f"File exists with additional .m4a extension")
                    os.rename(output_path + '.m4a', output_path)
                    print(f"Renamed {output_path + '.m4a'} to {output_path}")
                    logging.info(f"Renamed {output_path + '.m4a'} to {output_path}")
            
            # Verify the file exists and is not empty
            if not os.path.exists(output_path):
                raise FileNotFoundError(f"Output file not found: {output_path}")
            if os.path.getsize(output_path) == 0:
                raise ValueError(f"Output file is empty: {output_path}")
            
            test_ffprobe(output_path)
            
            return output_path
        except Exception as e:
            logging.warning(f"Attempt {attempt + 1} failed. Error: {str(e)}")
            if attempt < max_retries - 1:
                logging.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                logging.error(f"Failed to download audio after {max_retries} attempts.")
                raise

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
    """Transcribe audio file using Whisper with GPU acceleration if available"""
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
    
    logging.info(f"Transcription of file {file_num}/{total_files} complete.")
    print(f"Transcription of file {file_num}/{total_files} complete.")
    
    return result["text"], transcription_time, audio_duration

def save_processed_urls(urls):
    """Save the processed URLs to a file"""
    with open('processed_urls.json', 'w') as f:
        json.dump(urls, f)

def load_processed_urls():
    """Load the previously processed URLs from a file"""
    try:
        with open('processed_urls.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def generate_url_hash(urls):
    """Generate a hash of the URLs to quickly compare sets of URLs"""
    return hashlib.md5(','.join(sorted(urls)).encode()).hexdigest()

def get_video_title(url):
    """Extract video title from the URL"""
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('title', 'Untitled Video')
    except Exception as e:
        logging.error(f"Error extracting video title: {str(e)}")
        return 'Untitled Video'

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

def main():
    logging.info("Starting the transcription process")
    check_dependencies()
    
    current_dir = os.getcwd()
    logging.info(f"Current working directory: {current_dir}")
    
    output_dir = os.path.join(current_dir, "transcription_output")
    os.makedirs(output_dir, exist_ok=True)
    logging.info(f"Created output directory: {output_dir}")
    
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

    logging.info("Checking URLs...")
    print("Checking URLs...")
    valid_urls = []
    for url in urls:
        if check_url(url):
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
            output_path = os.path.join(output_dir, f"audio_{i}.m4a")
            try:
                actual_path = download_audio(url, output_path, i, total_files)
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
                
                # Get video title and create simplified filename
                video_title = get_video_title(url)
                simplified_title = simplify_filename(video_title)
                transcript_filename = f"{simplified_title}_transcript.txt"
                full_transcript_path = os.path.join(output_dir, transcript_filename)
                
                # Save individual transcript
                with open(full_transcript_path, "w") as f:
                    f.write(transcription)
                
                transcriptions.append(transcription)
                total_transcription_time += transcription_time
                total_audio_duration += audio_duration
                logging.info(f"Successfully transcribed: {audio_file}")
                print(f"Transcript saved as: {full_transcript_path}")
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