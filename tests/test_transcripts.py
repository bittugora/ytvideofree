import unittest

from downloader.core.transcripts import format_srt, normalize_segments


class TranscriptTests(unittest.TestCase):
    def test_normalize_segments_accepts_raw_dicts(self):
        segments = normalize_segments(
            [
                {"text": "Hello\nworld", "start": 1.25, "duration": 2.5},
                {"text": "Done", "start": 4.0, "duration": 1.0},
            ]
        )

        self.assertEqual(segments[0]["text"], "Hello world")
        self.assertEqual(segments[0]["timestamp"], "00:01")
        self.assertEqual(segments[1]["text"], "Done")

    def test_format_srt(self):
        srt = format_srt(
            [
                {"text": "Hello world", "start": 1.25, "duration": 2.5},
                {"text": "Done", "start": 4.0, "duration": 1.0},
            ]
        )

        self.assertIn("1\n00:00:01,250 --> 00:00:03,750\nHello world", srt)
        self.assertIn("2\n00:00:04,000 --> 00:00:05,000\nDone", srt)


if __name__ == "__main__":
    unittest.main()
