import subprocess
import sys
import logging
import os

# Set up logging
log_file = 'dependency_installation.log'
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename=log_file,
    filemode='w'  # 'w' mode overwrites the file each time
)

# Add a stream handler for INFO and above to show these in console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(levelname)s: %(message)s')
console_handler.setFormatter(formatter)
logging.getLogger('').addHandler(console_handler)

def install(package):
    logging.info(f"Attempting to install {package}")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        logging.info(f"Successfully installed {package}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to install {package}. Error: {str(e)}")
        raise

def main():
    logging.info("Starting dependency installation process")
    print(f"Installation log will be saved to: {os.path.abspath(log_file)}")

    dependencies = [
        "openai-whisper",
        "yt-dlp",
        "tqdm",
        "torch",
        "termcolor"
    ]

    for dep in dependencies:
        try:
            install(dep)
            print(f"{dep} installed successfully.")
        except subprocess.CalledProcessError:
            print(f"Failed to install {dep}. Please check the log file and install it manually.")

    # Special installation for PyTorch with CUDA support
    try:
        import torch
        if torch.cuda.is_available():
            print("CUDA is available. PyTorch with CUDA support is already installed.")
        else:
            print("CUDA is not available. Installing PyTorch with CPU support.")
            install("torch")
    except ImportError:
        print("PyTorch is not installed. Installing PyTorch with CPU support.")
        install("torch")

    logging.info("Checking for FFmpeg...")
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logging.info("FFmpeg is already installed.")
        print("FFmpeg is already installed.")
    except FileNotFoundError:
        logging.warning("FFmpeg is not installed or not in the system PATH.")
        print("FFmpeg is not installed or not in the system PATH.")
        print("Please install FFmpeg manually and make sure it's in your system PATH.")
        print("You can download it from: https://ffmpeg.org/download.html")

    logging.info("Installation process completed")
    print("\nInstallation process completed. If you encountered any errors,")
    print(f"please check the log file at {os.path.abspath(log_file)} for details.")
    print("Resolve any issues manually before running the main script.")

if __name__ == "__main__":
    main()