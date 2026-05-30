import queue
import threading
import unittest

from voicesss.audio import InputDevice, MicrophoneVAD, _is_recommended_input_device


class FakeVad:
    def is_speech(self, frame: bytes, sample_rate: int) -> bool:
        del frame, sample_rate
        return False


class MicrophoneVADTests(unittest.TestCase):
    def test_collect_utterances_stops_when_requested(self) -> None:
        microphone = MicrophoneVAD()
        stop_event = threading.Event()
        stop_event.set()

        chunks = list(
            microphone._collect_utterances(
                queue.Queue(),
                FakeVad(),
                sample_rate=16000,
                stop_event=stop_event,
            )
        )

        self.assertEqual(chunks, [])


class InputDeviceFilterTests(unittest.TestCase):
    def test_recommends_real_wasapi_microphone(self) -> None:
        device = InputDevice(
            index=42,
            name="Microfone (Realtek(R) Audio)",
            channels=2,
            default_sample_rate=48000,
            host_api="Windows WASAPI",
        )

        self.assertTrue(_is_recommended_input_device(device))

    def test_hides_windows_placeholder(self) -> None:
        device = InputDevice(
            index=0,
            name="Mapeador de som da Microsoft - Input",
            channels=2,
            default_sample_rate=44100,
            host_api="MME",
            is_default=True,
        )

        self.assertFalse(_is_recommended_input_device(device))

    def test_hides_virtual_devices_by_default(self) -> None:
        device = InputDevice(
            index=41,
            name="CABLE Output (VB-Audio Virtual Cable)",
            channels=2,
            default_sample_rate=48000,
            host_api="Windows WASAPI",
        )

        self.assertFalse(_is_recommended_input_device(device))


if __name__ == "__main__":
    unittest.main()
