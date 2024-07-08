# MultiSource Video Transcriber (MVT)

MultiSource Video Transcriber (MVT) is a powerful tool that downloads audio from a wide variety of online video sources, transcribes them using OpenAI's Whisper, and provides the option for summarization. It's designed to work with multiple video URLs from different platforms and can cache results for efficiency in subsequent runs. It runs locally on your PC so no credits or tokens are required from the cloud. 

## Features

- Download audio from various video sources (YouTube, Reddit, Twitter, and any other platform supported by yt-dlp)
- Transcribe audio using Whisper
- Cache processed URLs to skip redundant downloads and transcriptions
- Measure transcription speed and performance
- Unit tests for key functionalities

## Prerequisites

- Python 3.11
- FFmpeg installed and available in your system PATH

## Setup

1. Clone this repository:
   ```
   git clone https://github.com/tatsuikeda/MultiSource-Video-Transcriber.git
   cd MultiSource-Video-Transcriber
   ```

2. Create and activate a Python 3.11 virtual environment:
   ```
   python3.11 -m venv mvt
   source mvt/bin/activate  # On Windows, use `mvt\Scripts\activate`
   ```

3. Run the dependency installer script:
   ```
   python install_dependencies.py
   ```

## Usage

1. Run the main script:
   ```
   python video_transcription.py
   ```

2. When prompted, enter the video URLs you want to process. These can be from various platforms, including but not limited to YouTube, Reddit, and Twitter. Press Enter without typing a URL to finish input.

3. The script will download the audio, transcribe it, and save the full transcript.

4. After processing, you'll see timing information about the transcription process.

## Output

- The full transcript will be saved as `full_transcription.txt` in the same directory as the script.
- You can find the exact path of the transcript file in the console output at the end of the script execution.

## Running Unit Tests

To run the unit tests:

```
python -m unittest test_multisource_video_transcriber.py
```

## Notes

- The script uses yt-dlp, which supports a wide range of video platforms. For a full list of supported sites, refer to the [yt-dlp documentation](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).
- The script caches processed URLs. If you run the script with the same URLs, it will skip the download and transcription steps and use the existing transcription.
- Make sure you have sufficient disk space for audio downloads and transcription files.
- The transcription quality depends on the Whisper model used. You can adjust this in the script if needed.

## Troubleshooting

- If you encounter any issues with FFmpeg, ensure it's correctly installed and available in your system PATH.
- For any dependency issues, try running the `install_dependencies.py` script again or install the required packages manually.
- If a particular video fails to download, check if yt-dlp supports that platform or if the video is still available.

## Contributing

Feel free to fork this repository and submit pull requests with any enhancements.

## License

MIT License

Copyright (c) [2024] [Tatsu Ikeda]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.