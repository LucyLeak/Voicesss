import unittest

import numpy as np

from voicesss.transcription import WHISPER_SAMPLE_RATE, pcm16_to_float32_audio, resample_audio


class AudioConversionTests(unittest.TestCase):
    def test_resamples_48khz_to_whisper_rate(self) -> None:
        source = np.ones(48_000, dtype=np.float32)

        result = resample_audio(source, source_sample_rate=48_000)

        self.assertEqual(result.shape, (WHISPER_SAMPLE_RATE,))

    def test_pcm16_conversion_resamples_when_needed(self) -> None:
        samples = np.zeros(48_000, dtype=np.int16)

        result = pcm16_to_float32_audio(samples.tobytes(), source_sample_rate=48_000)

        self.assertEqual(result.shape, (WHISPER_SAMPLE_RATE,))


if __name__ == "__main__":
    unittest.main()
