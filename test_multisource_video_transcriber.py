import unittest
import os
import json
import io
import logging
import torch
from unittest.mock import patch, MagicMock
from multisource_video_transcriber import (
    check_url, download_audio, transcribe_audio, get_audio_duration,
    generate_url_hash, save_processed_urls, load_processed_urls,
    choose_whisper_model, simplify_filename, get_video_title
)

class TestMultiSourceVideoTranscriber(unittest.TestCase):

    def setUp(self):
        self.test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.test_audio_file = "test_audio.m4a"
        self.test_transcription = "This is a test transcription."

    def tearDown(self):
        if os.path.exists(self.test_audio_file):
            os.remove(self.test_audio_file)
        if os.path.exists('processed_urls.json'):
            os.remove('processed_urls.json')

    @patch('multisource_video_transcriber.yt_dlp.YoutubeDL')
    def test_check_url(self, mock_ytdl):
        mock_ytdl_instance = MagicMock()
        mock_ytdl_instance.extract_info.return_value = {"title": "Test Video"}
        mock_ytdl.return_value.__enter__.return_value = mock_ytdl_instance
        
        self.assertTrue(check_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))

        mock_ytdl_instance.extract_info.side_effect = Exception("Invalid URL")
        
        with self.assertLogs(level='ERROR') as log, patch('sys.stderr', new=io.StringIO()) as fake_stderr:
            self.assertFalse(check_url("https://www.invalid-url.com"))
            self.assertTrue(any("Error checking URL https://www.invalid-url.com" in msg for msg in log.output))
            self.assertEqual(fake_stderr.getvalue(), '')

    @patch('multisource_video_transcriber.yt_dlp.YoutubeDL')
    @patch('multisource_video_transcriber.os.path.exists')
    @patch('multisource_video_transcriber.os.access')
    @patch('multisource_video_transcriber.test_ffprobe')
    @patch('multisource_video_transcriber.os.path.getsize')
    def test_download_audio(self, mock_getsize, mock_test_ffprobe, mock_access, mock_exists, mock_ytdl):
        mock_ytdl.return_value.download.return_value = None
        mock_exists.return_value = True
        mock_access.return_value = True
        mock_test_ffprobe.return_value = None
        mock_getsize.return_value = 1024  # Mock file size
        
        result = download_audio(self.test_url, self.test_audio_file, 1, 1)
        self.assertEqual(result, self.test_audio_file)

    @patch('multisource_video_transcriber.whisper.load_model')
    @patch('multisource_video_transcriber.os.path.exists')
    @patch('torch.cuda.is_available')
    def test_transcribe_audio(self, mock_cuda_available, mock_exists, mock_whisper_load):
        mock_exists.return_value = True
        mock_cuda_available.return_value = False
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": self.test_transcription}
        mock_whisper_load.return_value.to.return_value = mock_model

        with patch('multisource_video_transcriber.get_audio_duration', return_value=10.0):
            transcription, time, duration = transcribe_audio(self.test_audio_file, 1, 1, "base")
        
        self.assertEqual(transcription, self.test_transcription)
        self.assertIsInstance(time, float)
        self.assertEqual(duration, 10.0)

    @patch('multisource_video_transcriber.subprocess.run')
    def test_get_audio_duration(self, mock_run):
        mock_run.return_value.stdout = b"10.5"
        duration = get_audio_duration(self.test_audio_file)
        self.assertEqual(duration, 10.5)

    def test_generate_url_hash(self):
        urls = ["https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
        hash1 = generate_url_hash(urls)
        hash2 = generate_url_hash(urls[::-1])
        self.assertEqual(hash1, hash2)

    def test_save_and_load_processed_urls(self):
        test_data = {'hash': 'test_hash', 'urls': ['url1', 'url2']}
        save_processed_urls(test_data)
        loaded_data = load_processed_urls()
        self.assertEqual(test_data, loaded_data)

    @patch('builtins.input')
    def test_choose_whisper_model(self, mock_input):
        mock_input.side_effect = ["3"]
        model = choose_whisper_model()
        self.assertEqual(model, "small")

        mock_input.side_effect = ["6", "invalid", "2"]
        model = choose_whisper_model()
        self.assertEqual(model, "base")

    @patch('multisource_video_transcriber.yt_dlp.YoutubeDL')
    def test_get_video_title(self, mock_ytdl):
        # Test successful title extraction
        mock_instance = MagicMock()
        mock_instance.extract_info.return_value = {'title': 'Test Video Title'}
        mock_ytdl.return_value.__enter__.return_value = mock_instance

        title = get_video_title("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(title, 'Test Video Title')

        # Test error handling
        mock_instance.extract_info.side_effect = Exception("Error")
        title = get_video_title("https://www.youtube.com/watch?v=invalid")
        self.assertEqual(title, 'Untitled Video')

if __name__ == '__main__':
    unittest.main()