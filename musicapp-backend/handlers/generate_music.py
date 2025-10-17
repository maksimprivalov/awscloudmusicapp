import math, wave, struct, os

OUT_DIR = "demo_wav"
DURATION_SEC = 3
SAMPLE_RATE = 44100
AMPLITUDE = 16000

# par lepih frekvencija (A dur akord + još nešto)
FREQS = [440, 554.37, 659.25, 880, 987.77]

os.makedirs(OUT_DIR, exist_ok=True)

for i, freq in enumerate(FREQS, start=1):
    fname = os.path.join(OUT_DIR, f"track_{i:02d}_{int(freq)}Hz.wav")
    with wave.open(fname, "w") as wf:
        wf.setnchannels(1)          # mono
        wf.setsampwidth(2)          # 16-bit
        wf.setframerate(SAMPLE_RATE)
        frames = []
        for n in range(int(DURATION_SEC * SAMPLE_RATE)):
            t = n / SAMPLE_RATE
            sample = int(AMPLITUDE * math.sin(2 * math.pi * freq * t))
            frames.append(struct.pack("<h", sample))
        wf.writeframes(b"".join(frames))
    print("Created", fname)

print("Done. WAV files are in", OUT_DIR)
