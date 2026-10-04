"""
Subtitle service — captures system audio and sends it to the backend for
transcription.

Uses PulseAudio to capture what the machine is playing.  A null-sink +
loopback pipeline ensures we always receive audio frames, even when the
real output device is suspended (nothing actively playing).  Audio chunks
are posted to the backend's /api/subtitles/transcribe endpoint; the server
runs the speech-to-text model so the child's machine needs no GPU or large
dependencies.  The child toggles this on/off themselves.
"""

import base64
import io
import os
import struct
import subprocess
import threading
import time
import wave

import gi
import requests

gi.require_version("Gtk", "3.0")
from gi.repository import GLib


# ---------------------------------------------------------------------------
# Dependency checking  (only local tools — the heavy model lives on the server)
# ---------------------------------------------------------------------------

def check_dependencies():
    """Return None if ready, or a user-facing string explaining what to install."""
    problems = []

    for cmd in ["parec", "pactl"]:
        try:
            subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
        except FileNotFoundError:
            problems.append(cmd)

    if problems:
        return (
            "Subtitle support needs PulseAudio tools to capture audio.\n\n"
            f"Missing commands: {', '.join(problems)}\n\n"
            "Install with:\n"
            "  sudo apt-get install pulseaudio-utils\n\n"
            "After installing, restart the app and try again."
        )
    return None


# ---------------------------------------------------------------------------
# PulseAudio capture pipeline
# ---------------------------------------------------------------------------

_SINK_NAME = "parentchat_subtitle"


class _PulsePipeline:
    """Manages a null-sink + loopback pair so parec always gets frames.

    A PulseAudio monitor source only produces data when the underlying sink
    is actively playing audio.  If the sink is SUSPENDED (nothing playing),
    parec blocks forever.  To avoid that we:

    1. Create a null sink (``parentchat_subtitle``).
    2. Create a loopback from the real output's monitor into our null sink.
    3. Capture from ``parentchat_subtitle.monitor`` — the null sink is always
       RUNNING while the loopback is active, so parec never blocks.

    Call ``setup()`` before starting capture, ``teardown()`` when done.
    """

    def __init__(self):
        self._sink_module = None
        self._loop_module = None
        self.source_name = None   # set by setup()
        self.rate = 44100
        self.channels = 2

    def setup(self):
        """Create the null sink + loopback.  Returns True on success."""
        hw_source = self._find_hw_monitor()
        if not hw_source:
            return False

        self.rate, self.channels = self._detect_format(hw_source)

        # Load null sink
        try:
            out = subprocess.run(
                ["pactl", "load-module", "module-null-sink",
                 f"sink_name={_SINK_NAME}",
                 f"rate={self.rate}",
                 f"channels={self.channels}",
                 "sink_properties=device.description=ParentChatSubtitle"],
                capture_output=True, text=True, timeout=5,
            )
            if out.returncode != 0:
                print(f"[subtitle] null-sink load failed: {out.stderr.strip()}")
                return False
            self._sink_module = out.stdout.strip()
        except Exception as exc:
            print(f"[subtitle] null-sink error: {exc}")
            return False

        # Load loopback: real monitor → our null sink
        try:
            out = subprocess.run(
                ["pactl", "load-module", "module-loopback",
                 f"source={hw_source}",
                 f"sink={_SINK_NAME}",
                 "latency_msec=100"],
                capture_output=True, text=True, timeout=5,
            )
            if out.returncode != 0:
                print(f"[subtitle] loopback load failed: {out.stderr.strip()}")
                self.teardown()
                return False
            self._loop_module = out.stdout.strip()
        except Exception as exc:
            print(f"[subtitle] loopback error: {exc}")
            self.teardown()
            return False

        self.source_name = f"{_SINK_NAME}.monitor"
        return True

    def teardown(self):
        """Remove the PulseAudio modules we loaded."""
        for mod_id in [self._loop_module, self._sink_module]:
            if mod_id is not None:
                try:
                    subprocess.run(
                        ["pactl", "unload-module", str(mod_id)],
                        capture_output=True, timeout=5,
                    )
                except Exception:
                    pass
        self._loop_module = None
        self._sink_module = None
        self.source_name = None

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _find_hw_monitor():
        """Return the first hardware monitor source name, or None."""
        try:
            result = subprocess.run(
                ["pactl", "list", "short", "sources"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.strip().splitlines():
                parts = line.split("\t")
                if len(parts) >= 2 and ".monitor" in parts[1]:
                    # Skip our own sink if it's left over from a previous run
                    if _SINK_NAME in parts[1]:
                        continue
                    return parts[1]
        except Exception as exc:
            print(f"[subtitle] pactl error: {exc}")
        return None

    @staticmethod
    def _detect_format(source):
        """Parse pactl output for a source's sample rate and channel count."""
        rate, channels = 44100, 2
        try:
            result = subprocess.run(
                ["pactl", "list", "short", "sources"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.strip().splitlines():
                parts = line.split("\t")
                if len(parts) >= 5 and parts[1] == source:
                    for tok in parts[3].split():
                        if tok.endswith("ch"):
                            channels = int(tok[:-2])
                        elif tok.endswith("Hz"):
                            rate = int(tok[:-2])
                    break
        except Exception:
            pass
        return rate, channels


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def _raw_to_wav(raw_bytes, channels=1, rate=16000, sampwidth=2):
    """Wrap raw PCM bytes in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(rate)
        wf.writeframes(raw_bytes)
    buf.seek(0)
    return buf


def _resample_s16le(data, src_channels, src_rate, dst_rate=16000):
    """Downmix to mono and resample to *dst_rate* (nearest-neighbour)."""
    n_samples = len(data) // (2 * src_channels)
    fmt = f"<{n_samples * src_channels}h"
    samples = struct.unpack(fmt, data[: n_samples * src_channels * 2])

    # Downmix to mono
    mono = []
    for i in range(0, len(samples), src_channels):
        chunk = samples[i : i + src_channels]
        mono.append(sum(chunk) // src_channels)

    # Resample
    ratio = dst_rate / src_rate
    out_len = int(len(mono) * ratio)
    resampled = []
    for i in range(out_len):
        idx = min(int(i / ratio), len(mono) - 1)
        resampled.append(mono[idx])

    return struct.pack(f"<{len(resampled)}h", *resampled)


# ---------------------------------------------------------------------------
# Subtitle service
# ---------------------------------------------------------------------------

class SubtitleService:
    """Captures system audio and gets transcriptions from the backend.

    Audio is captured locally via a PulseAudio loopback pipeline, compressed
    to 16 kHz mono WAV, and posted to the server for transcription.  Only
    the resulting text comes back — no heavy model runs on the child's machine.

    Call ``start()`` / ``stop()`` to toggle.  *on_subtitle* is invoked on the
    GTK main thread with ``(kind, text)`` where *kind* is ``'subtitle'`` for
    transcribed speech or ``'status'`` for informational messages.
    """

    CHUNK_SECONDS = 4
    TARGET_RATE = 16000
    # RMS below this is treated as silence and not sent to the server.
    SILENCE_THRESHOLD = 50

    def __init__(self, config, on_subtitle=None):
        """
        Args:
            config: Config instance (provides server_url, auth_token).
            on_subtitle: callback(kind: str, text: str) dispatched on GTK thread.
        """
        self._config = config
        self._on_subtitle = on_subtitle
        self._running = False
        self._thread = None
        self._process = None
        self._pipeline = None
        self._silent_chunks = 0
        self._lock = threading.Lock()

    @property
    def is_running(self):
        return self._running

    def start(self):
        """Begin capturing and transcribing."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop capturing and tear down PulseAudio pipeline."""
        self._running = False
        with self._lock:
            if self._process and self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                self._process = None
        if self._pipeline:
            self._pipeline.teardown()
            self._pipeline = None

    # -- internals ----------------------------------------------------------

    def _run(self):
        # Set up the PulseAudio loopback pipeline
        print("[subtitle] Setting up PulseAudio capture pipeline…")
        self._pipeline = _PulsePipeline()
        if not self._pipeline.setup():
            print("[subtitle] Pipeline setup FAILED — no monitor source found")
            self._emit(
                "Could not set up audio capture — no monitor source found.",
                kind="status",
            )
            self._pipeline = None
            self._running = False
            return

        source = self._pipeline.source_name
        src_rate = self._pipeline.rate
        src_channels = self._pipeline.channels
        bytes_per_chunk = src_rate * src_channels * 2 * self.CHUNK_SECONDS

        print(f"[subtitle] Pipeline ready: {source} ({src_rate}Hz {src_channels}ch)")
        print(f"[subtitle] Chunk size: {bytes_per_chunk} bytes ({self.CHUNK_SECONDS}s)")
        self._silent_chunks = 0
        self._emit("Listening — play some audio to see subtitles.", kind="status")

        try:
            while self._running:
                try:
                    self._capture_and_send(
                        source, src_rate, src_channels, bytes_per_chunk,
                    )
                except Exception as exc:
                    if self._running:
                        self._emit(f"Error: {exc}", kind="status")
                        time.sleep(2)
        finally:
            if self._pipeline:
                self._pipeline.teardown()
                self._pipeline = None

    def _capture_and_send(self, source, src_rate, src_channels, bytes_per_chunk):
        """Run parec against the loopback source and post chunks to backend."""
        cmd = [
            "parec", "--format=s16le",
            f"--rate={src_rate}", f"--channels={src_channels}",
            f"--device={source}",
        ]
        with self._lock:
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
        proc = self._process

        try:
            while self._running:
                raw = proc.stdout.read(bytes_per_chunk)
                if not raw:
                    break

                # Resample to 16 kHz mono
                mono16k = _resample_s16le(raw, src_channels, src_rate, self.TARGET_RATE)

                # Check audio level
                samples = struct.unpack(f"<{len(mono16k)//2}h", mono16k)
                rms = (sum(s * s for s in samples) / len(samples)) ** 0.5

                if rms < self.SILENCE_THRESHOLD:
                    self._silent_chunks += 1
                    # Log every ~20 seconds of silence so the user knows
                    # the service is alive but waiting for audio
                    if self._silent_chunks == 1:
                        print(f"[subtitle] Silence (rms={rms:.0f}), waiting for audio…")
                    elif self._silent_chunks % 5 == 0:
                        secs = self._silent_chunks * self.CHUNK_SECONDS
                        print(f"[subtitle] Still silent ({secs}s), waiting for audio…")
                    if self._silent_chunks == 5:
                        self._emit(
                            "No audio detected yet — play something to see subtitles.",
                            kind="status",
                        )
                    continue

                self._silent_chunks = 0
                print(f"[subtitle] Audio detected (rms={rms:.0f}), sending to server…")

                # Encode as WAV and send to backend
                wav_buf = _raw_to_wav(mono16k, channels=1, rate=self.TARGET_RATE)
                audio_b64 = base64.b64encode(wav_buf.read()).decode("ascii")

                try:
                    resp = requests.post(
                        f"{self._config.server_url}/api/subtitles/transcribe",
                        json={"audioData": audio_b64},
                        headers={"X-Child-Token": self._config.auth_token},
                        timeout=30,
                    )
                    if resp.status_code == 200:
                        text = resp.json().get("text", "").strip()
                        if text:
                            print(f"[subtitle] Transcribed: {text[:80]}")
                            self._emit(text)
                        else:
                            print("[subtitle] Server returned empty text (no speech detected in chunk)")
                    elif resp.status_code == 503:
                        self._emit(
                            "Server doesn't have a speech model installed yet.",
                            kind="status",
                        )
                        self._running = False
                        return
                    else:
                        self._emit(
                            f"Server returned {resp.status_code}",
                            kind="status",
                        )
                except requests.ConnectionError:
                    self._emit("Lost connection to server.", kind="status")
                except requests.Timeout:
                    pass  # skip this chunk, try next
        finally:
            with self._lock:
                if proc.poll() is None:
                    proc.terminate()
                self._process = None

    def _emit(self, text, kind="subtitle"):
        """Send text to the callback on the GTK main thread.

        Args:
            text: The text content.
            kind: 'subtitle' for transcribed speech, 'status' for info/errors.
        """
        if self._on_subtitle:
            GLib.idle_add(self._on_subtitle, kind, text)
