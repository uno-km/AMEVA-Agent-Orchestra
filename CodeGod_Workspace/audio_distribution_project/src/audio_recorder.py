import pyaudio
import wave
import threading
import time

class AudioRecorder:
    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(format=pyaudio.paInt16, channels=2, rate=44100, input=True, frames_per_buffer=1024)

    def record_audio(self):
        frames = []
        while True:
            data = self.stream.read(1024)
            frames.append(data)
            time.sleep(60)  # 1 minute

    def save_audio(self, filename):
        wf = wave.open(filename, 'wb')
        wf.setnchannels(2)
        wf.setsampwidth(self.p.get_sample_size(pyaudio.paInt16))
        wf.setframerate(44100)
        wf.writeframes(b''.join(frames))
        wf.close()

# Create an instance of the AudioRecorder class
recorder = AudioRecorder()

# Start recording in a separate thread
threading.Thread(target=recorder.record_audio).start()

# Save the recorded audio to a file
recorder.save_audio('recorded_audio.wav')