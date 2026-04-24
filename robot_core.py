# -------------- IMPORTS --------------
# Standard and third-party library imports for robot operation.
# -------------------------------------
import time
import math
import os
import threading
import subprocess
import base64
import requests
import glob
import random
import datetime
import io

# -------------- GOOGLE DRIVE IMPORTS --------------
# Imports for Google Drive API and OAuth authentication.
# ---------------------------------------------------
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# -------------- HARDWARE & IMAGE LIBRARIES --------------
# Libraries for image processing, GPIO, camera, and TTS.
# --------------------------------------------------------
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageOps, ImageEnhance
from gpiozero import PWMOutputDevice, DigitalOutputDevice, Button
from huskylib import HuskyLensLibrary
from picamera2 import Picamera2
from gtts import gTTS


# -------------- ENVIRONMENT LOADING --------------
# Loads environment variables from a .env file if present.
# --------------------------------------------------
def load_env_file(path):
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception as e:
        print(f"Warning: Could not load .env file ({path}): {e}")

load_env_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


# -------------- CONFIGURATION --------------
# Key settings and configuration for robot operation.
# --------------------------------------------
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
VISION_MODELS = [
    os.environ.get("OPENROUTER_VISION_MODEL", "qwen/qwen3-vl-32b-instruct"),
    "anthropic/claude-sonnet-4.6",
    "qwen/qwen3-vl-32b-instruct",
    "google/gemini-3-pro-image-preview",
    "openai/gpt-5-image-mini"
]
CAPTURE_INTERVAL_SEC = 0.5
STRIP_SIZE = 5
ACTION_BUTTON_PIN = int(os.environ.get("ACTION_BUTTON_PIN", "5"))
POWER_BUTTON_PIN = int(os.environ.get("POWER_BUTTON_PIN", os.environ.get("SHUTDOWN_BUTTON_PIN", "6")))
POWER_HOLD_SEC = float(os.environ.get("POWER_HOLD_SEC", os.environ.get("SHUTDOWN_HOLD_SEC", "5")))
START_BEEP_ENABLED = os.environ.get("START_BEEP_ENABLED", "1") == "1"
POWER_BUTTON_BOUNCE_SEC = float(os.environ.get("POWER_BUTTON_BOUNCE_SEC", "0.12"))
POWER_BUTTON_CONFIRM_SEC = float(os.environ.get("POWER_BUTTON_CONFIRM_SEC", "0.05"))
POWER_TAP_MIN_SEC = float(os.environ.get("POWER_TAP_MIN_SEC", "0.06"))
POWER_EVENT_COOLDOWN_SEC = float(os.environ.get("POWER_EVENT_COOLDOWN_SEC", "0.30"))
POWER_BUTTON_PULL_UP = os.environ.get("POWER_BUTTON_PULL_UP", "1") == "1"
AUDIO_MIXER_CONTROL = os.environ.get("AUDIO_MIXER_CONTROL", "PCM")
AUDIO_VOLUME_PERCENT = os.environ.get("AUDIO_VOLUME_PERCENT", "100%")
BEEP_WAKE_DURATION_SEC = float(os.environ.get("BEEP_WAKE_DURATION_SEC", "0.25"))
BEEP_WAKE_VOLUME = float(os.environ.get("BEEP_WAKE_VOLUME", "0.5"))
BEEP_SETTLE_SEC = float(os.environ.get("BEEP_SETTLE_SEC", "0.05"))
BEEP_INTERVAL_SEC = float(os.environ.get("BEEP_INTERVAL_SEC", "0.8"))

alarm_proc_lock = threading.Lock()
current_alarm_proc = None
last_alarm_started_at = 0.0
tts_cache_lock = threading.Lock()
cached_tts_text = ""
BEEP_FREQ_HZ = float(os.environ.get("BEEP_FREQ_HZ", "1200"))
BEEP_DURATION_SEC = float(os.environ.get("BEEP_DURATION_SEC", "0.18"))
BEEP_GAIN_DB = float(os.environ.get("BEEP_GAIN_DB", "12.0"))
BEEP_BURST_COUNT = int(os.environ.get("BEEP_BURST_COUNT", "2"))
BEEP_BURST_GAP_SEC = float(os.environ.get("BEEP_BURST_GAP_SEC", "0.10"))
SPEECH_WAKE_DURATION_SEC = float(os.environ.get("SPEECH_WAKE_DURATION_SEC", "0.25"))
SPEECH_WAKE_VOLUME = float(os.environ.get("SPEECH_WAKE_VOLUME", "0.5"))
SPEAKER_SETTLE_SEC = float(os.environ.get("SPEAKER_SETTLE_SEC", "0.15"))
RECENT_ALARM_SKIP_WAKE_WINDOW_SEC = float(os.environ.get("RECENT_ALARM_SKIP_WAKE_WINDOW_SEC", "8.0"))
RECENT_ALARM_SETTLE_SEC = float(os.environ.get("RECENT_ALARM_SETTLE_SEC", "0.08"))
ALARM_SOUND_PATH = os.environ.get("ALARM_SOUND_PATH", "/home/roverpi/alarm.mp3")
ALARM_MP3_PATH = "/tmp/roverpi_alarm.mp3"
SYSTEM_ALARM_PATH = "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"
ALARM_REPEAT_COUNT = int(os.environ.get("ALARM_REPEAT_COUNT", "1"))
ALARM_REPEAT_GAP_SEC = float(os.environ.get("ALARM_REPEAT_GAP_SEC", "0.15"))
AFFIRMATION_TTS_CACHE_PATH = "/tmp/roverpi_affirmation_cache.mp3"


# -------------- GOOGLE DRIVE CONFIG --------------
# File paths and folder ID for Google Drive integration.
# --------------------------------------------------
GDRIVE_CREDS = "/home/roverpi/credentials.json"
GDRIVE_FOLDER_ID = "1xbg2vaMZ2UPwY5aEKG-ZxQxcfJb1JHYC"

def get_random_affirmation():
    try:
        with open("affirmations.txt", "r") as f:
            lines = [line.strip() for line in f if line.strip()]
        return random.choice(lines) if lines else "I am ready"
    except FileNotFoundError:
        print("Warning: affirmations.txt not found! Using fallback.")
        return "I am ready"


def play_tone_via_aplay(duration_sec, frequency_hz, wav_path, volume=None):
    try:
        # Keep audio mux routed to the speaker path used by the voice pipeline.
        try:
            subprocess.run(
                ["pinctrl", "set", "12", "a0"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        except FileNotFoundError:
            pass

        cmd = [
            "sox", "-n", "-r", "44100", "-b", "16", "-c", "1", wav_path,
            "synth", str(duration_sec), "sine", str(frequency_hz)
        ]
        if volume is not None:
            cmd.extend(["vol", str(volume)])

        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
        if not os.path.exists(wav_path):
            return False

        subprocess.run(
            ["aplay", "-q", wav_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
        return True
    except Exception:
        return False
    finally:
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except OSError:
                pass


def ensure_beep_mp3():
    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"sine=frequency={BEEP_FREQ_HZ}:duration={BEEP_DURATION_SEC}",
            "-filter:a", f"volume={BEEP_GAIN_DB}dB",
            "-ac", "1",
            "-ar", "44100",
            "-q:a", "4",
            BEEP_MP3_PATH
        ]
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
        return os.path.exists(BEEP_MP3_PATH)
    except Exception:
        return False


def ensure_alarm_mp3():
    try:
        if os.path.exists(ALARM_MP3_PATH):
            return True

        source_path = None

        if os.path.exists(ALARM_SOUND_PATH):
            source_path = ALARM_SOUND_PATH

        if source_path is None and os.path.exists(SYSTEM_ALARM_PATH):
            source_path = SYSTEM_ALARM_PATH

        if source_path is None:
            return False

        rc = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", source_path,
                "-ac", "1",
                "-ar", "44100",
                "-q:a", "4",
                ALARM_MP3_PATH
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        ).returncode
        return rc == 0 and os.path.exists(ALARM_MP3_PATH)
    except Exception:
        return False


def ensure_cached_tts(text):
    global cached_tts_text
    with tts_cache_lock:
        if cached_tts_text == text and os.path.exists(AFFIRMATION_TTS_CACHE_PATH):
            return True
    try:
        tts = gTTS(text=text, lang='en', tld='co.uk')
        tts.save(AFFIRMATION_TTS_CACHE_PATH)
        with tts_cache_lock:
            cached_tts_text = text
        return True
    except Exception:
        return False


def prefetch_affirmation_tts_async(text):
    threading.Thread(target=ensure_cached_tts, args=(text,), daemon=True).start()


def play_alarm_via_mpg123():
    global current_alarm_proc, last_alarm_started_at
    try:
        if not ensure_alarm_mp3():
            return False

        proc = subprocess.Popen(
            ["mpg123", "-q", ALARM_MP3_PATH],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        with alarm_proc_lock:
            current_alarm_proc = proc
            last_alarm_started_at = time.monotonic()

        while proc.poll() is None:
            if not keep_beeping.is_set() or shutdown_requested.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=0.25)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return True
            time.sleep(0.02)

        return proc.returncode == 0
    except Exception:
        return False
    finally:
        with alarm_proc_lock:
            current_alarm_proc = None


def play_beep_via_mpg123():
    try:
        if not ensure_beep_mp3():
            return False
        rc = subprocess.run(
            ["mpg123", "-q", BEEP_MP3_PATH],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        ).returncode
        return rc == 0
    except Exception:
        return False

def speak(text):
    global last_alarm_started_at
    print(f"Robot says: '{text}'")
    speech_path = "/tmp/roverpi_speech.mp3"
    playback_path = speech_path
    used_temp_speech = False
    try:
        try:
            subprocess.run(
                ["pinctrl", "set", "12", "a0"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        except FileNotFoundError:
            pass

        # If alarm just played, speaker is already awake: skip long wake tone.
        recently_active = (time.monotonic() - last_alarm_started_at) <= RECENT_ALARM_SKIP_WAKE_WINDOW_SEC
        if recently_active:
            time.sleep(RECENT_ALARM_SETTLE_SEC)
        else:
            play_tone_via_aplay(SPEECH_WAKE_DURATION_SEC, "10", "/tmp/roverpi_wakeup.wav", volume=SPEECH_WAKE_VOLUME)
            time.sleep(SPEAKER_SETTLE_SEC)

        with tts_cache_lock:
            has_cached = cached_tts_text == text and os.path.exists(AFFIRMATION_TTS_CACHE_PATH)

        if has_cached:
            playback_path = AFFIRMATION_TTS_CACHE_PATH
        else:
            tts = gTTS(text=text, lang='en', tld='co.uk')
            tts.save(speech_path)
            used_temp_speech = True

        rc = subprocess.run(
            ["mpg123", "-q", playback_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        ).returncode
        if rc != 0:
            subprocess.run(
                ["espeak", "-ven+m3", "-s150", text],
                stderr=subprocess.DEVNULL,
                check=False
            )
    except Exception as e:
        print(f"Warning: Audio failed: {e}")
        subprocess.run(["espeak", "-ven+m3", "-s150", text], stderr=subprocess.DEVNULL, check=False)
    finally:
        if used_temp_speech and os.path.exists(speech_path):
            try:
                os.remove(speech_path)
            except OSError:
                pass


def enforce_boot_volume():
    try:
        subprocess.run(
            ["amixer", "sset", AUDIO_MIXER_CONTROL, AUDIO_VOLUME_PERCENT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
        print(f"Volume enforced: {AUDIO_MIXER_CONTROL}={AUDIO_VOLUME_PERCENT}")
    except Exception as e:
        print(f"Warning: Could not set boot volume: {e}")


def system_shutdown():
    global global_running
    print("Shutdown button held. Powering down...")
    keep_beeping.clear()
    system_awake.clear()
    stop_run_requested.set()
    shutdown_requested.set()
    global_running = False
    set_motors(0, 0)
    speak("Goodbye, have a good day. See you tomorrow.")
    time.sleep(1.5)
    subprocess.run(["sudo", "shutdown", "-h", "now"], check=False)



# -------------- BEEPING & ALARM LOGIC --------------
# Handles alarm and beeping sounds for user feedback.
# ---------------------------------------------------
def alarm_beep_thread():
    while not shutdown_requested.is_set():
        if keep_beeping.is_set():
            try:
                repeat_count = max(1, ALARM_REPEAT_COUNT)
                for alarm_idx in range(repeat_count):
                    ok = play_alarm_via_mpg123()
                    if not ok:
                        ok = play_beep_via_mpg123()
                    if not ok:
                        play_tone_via_aplay(BEEP_DURATION_SEC, BEEP_FREQ_HZ, "/tmp/roverpi_beep.wav")
                    if alarm_idx < repeat_count - 1:
                        time.sleep(ALARM_REPEAT_GAP_SEC)
            except Exception:
                pass
            time.sleep(BEEP_INTERVAL_SEC)
        else:
            time.sleep(0.1)


def start_beeping():
    if not START_BEEP_ENABLED:
        print("Beeping disabled by START_BEEP_ENABLED=0")
        return
    # Wake up Bluetooth speakers before the repeating beep starts.
    if not keep_beeping.is_set():
        play_tone_via_aplay(
            BEEP_WAKE_DURATION_SEC,
            "10",
            "/tmp/roverpi_beep_wakeup.wav",
            volume=BEEP_WAKE_VOLUME
        )
        time.sleep(BEEP_SETTLE_SEC)
        if not ensure_alarm_mp3():
            ensure_beep_mp3()
    keep_beeping.set()


def stop_beeping():
    keep_beeping.clear()
    with alarm_proc_lock:
        proc = current_alarm_proc
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=0.25)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def toggle_awake_state():
    global global_running, affirmation_heard, autonomous_active
    # Ignore power button only during actual autonomous run
    if system_awake.is_set() and autonomous_active:
        print("Power button ignored during autonomous run.")
        return
    if system_awake.is_set():
        if not mission_completed and current_affirmation_global:
            print("Power button tapped: replaying today's affirmation.")
            stop_beeping()
            speak(f"Good morning. Your affirmation is: {current_affirmation_global}")
            affirmation_heard = True
            return

        print("Power button tapped, but the mission is already complete. Ignoring replay.")
        return

    print("Power button tapped: waking system and starting beep.")
    stop_run_requested.clear()
    system_awake.set()
    start_beeping()


def power_button_monitor_loop():
    if power_button is None:
        return

    last_power_event_at = 0.0
    while not shutdown_requested.is_set():
        power_button.wait_for_press()
        if shutdown_requested.is_set():
            break

        press_start = time.monotonic()

        # Confirm press stays active briefly; ignore EMI spikes/noise.
        time.sleep(POWER_BUTTON_CONFIRM_SEC)
        if not power_button.is_pressed:
            continue

        while power_button.is_pressed and not shutdown_requested.is_set():
            time.sleep(0.01)

        held_for = time.monotonic() - press_start

        if held_for >= POWER_HOLD_SEC:
            system_shutdown()
            break

        if held_for < POWER_TAP_MIN_SEC:
            continue

        now = time.monotonic()
        if now - last_power_event_at < POWER_EVENT_COOLDOWN_SEC:
            continue
        last_power_event_at = now

        toggle_awake_state()


def setup_buttons():
    global action_button, power_button
    try:
        action_button = Button(ACTION_BUTTON_PIN, bounce_time=0.05)
        power_button = Button(
            POWER_BUTTON_PIN,
            pull_up=POWER_BUTTON_PULL_UP,
            hold_time=POWER_HOLD_SEC,
            bounce_time=POWER_BUTTON_BOUNCE_SEC
        )
        threading.Thread(target=power_button_monitor_loop, daemon=True).start()
        print(
            f"Buttons ready: action pin={ACTION_BUTTON_PIN}, power pin={POWER_BUTTON_PIN}, "
            f"hold={POWER_HOLD_SEC}s, bounce={POWER_BUTTON_BOUNCE_SEC}s"
        )
    except Exception as e:
        action_button = None
        power_button = None
        print(f"Warning: Button init failed, keyboard fallback enabled: {e}")


def show_affirmation_context(target_text):
    print("\n" + "*" * 50)
    print(f"📝 Target Affirmation: {target_text}")
    current_streak = get_current_streak_only()
    if current_streak > 0:
        print(f"🔥 Current Streak: {current_streak}")
    print("*" * 50)


def wait_for_action_press(prompt_text, stop_beep_on_press=False):
    if action_button is not None:
        print(prompt_text)
        while system_awake.is_set() and not shutdown_requested.is_set():
            if action_button.is_pressed:
                while action_button.is_pressed and system_awake.is_set() and not shutdown_requested.is_set():
                    time.sleep(0.03)
                if stop_beep_on_press:
                    stop_beeping()
                time.sleep(0.15)
                return True
            time.sleep(0.05)
        return False

    input("\nPress [ENTER] to continue: ")
    if stop_beep_on_press:
        stop_beeping()
    return True

def evaluate_affirmation(target, detected):
    print("\nEvaluating the user's handwritten affirmation...")
    prompt = f"""
    You are a lenient judge grading a handwritten affirmation.
    The target phrase the user was supposed to write is: "{target}"
    The robot's camera scanned and read: "{detected}"
    
    Are these similar enough? (Ignore minor spelling mistakes, messy handwriting errors, missing single or few letters, or missing single words).
    Respond ONLY with the word "PASS" or "FAIL".
    """
    payload = {"model": "openai/gpt-4o-mini", "messages": [{"role": "user", "content": prompt}]}
    result, err = openrouter_chat_completion(payload, "eval_judge")
    if err or not result: return "FAIL"
    return "PASS" if "PASS" in result.upper() else "FAIL"

# --- NEW: GOOGLE DRIVE UPLOAD & STREAK LOGIC ---
# --- UPDATED: SINGLE FILE GOOGLE DRIVE LOGIC ---
def handle_drive_upload(detected_text):
    CLIENT_SECRET_FILE = '/home/roverpi/client_secrets.json'
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    FILE_NAME = "affirmation_log.txt"
    creds = None

    if not os.path.exists(CLIENT_SECRET_FILE) or GDRIVE_FOLDER_ID == "PASTE_YOUR_FOLDER_ID_HERE":
        print("Warning: Google Drive OAuth not configured. Skipping upload.")
        return None

    print("\nConnecting to Google Drive as YOU...")
    
    # 1. Login Logic
    if os.path.exists('/home/roverpi/token.json'):
        creds = Credentials.from_authorized_user_file('/home/roverpi/token.json', SCOPES)
        
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("🌐 FIRST TIME SETUP: Please log in via the web browser that is opening...")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open('/home/roverpi/token.json', 'w') as token:
            token.write(creds.to_json())

    # 2. Download, Append, and Upload Logic
    try:
        service = build('drive', 'v3', credentials=creds)
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)

        # Look for the single log file
        results = service.files().list(
            q=f"'{GDRIVE_FOLDER_ID}' in parents and name='{FILE_NAME}' and trashed=false",
            fields="files(id, name)"
        ).execute()
        items = results.get('files', [])

        streak = 1
        file_id = None
        existing_content = ""

        if items:
            file_id = items[0]['id']
            # Download the existing text file
            request = service.files().get_media(fileId=file_id)
            existing_content = request.execute().decode('utf-8')
            
            # Read the last line to figure out the streak
            lines = existing_content.strip().split('\n')
            if lines:
                last_line = lines[-1]
                # Format we are looking for: "2026-04-17 | Streak: 3 | Message: I am ready"
                try:
                    parts = last_line.split(" | ")
                    last_date_str = parts[0].strip()
                    last_streak = int(parts[1].replace("Streak:", "").strip())
                    last_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()

                    if last_date == yesterday:
                        streak = last_streak + 1
                    elif last_date == today:
                        streak = last_streak # Keep the streak the same if done twice today
                except Exception as e:
                    print(f"Warning: Could not parse previous streak from log: {e}")

        # Format the new entry
        # Example: "2026-04-17 | Streak: 4 | Message: I am capable of amazing things."
        new_line = f"{today.strftime('%Y-%m-%d')} | Streak: {streak} | Message: {detected_text}"
        
        if existing_content:
            updated_content = existing_content + "\n" + new_line
        else:
            updated_content = new_line

        # Package it up as a text file
        media = MediaIoBaseUpload(io.BytesIO(updated_content.encode('utf-8')), mimetype='text/plain')

        if file_id:
            # Overwrite the existing file with the appended version
            service.files().update(fileId=file_id, media_body=media).execute()
            print(f"Appended new line to: {FILE_NAME}")
        else:
            # First time ever running it: Create the file
            file_metadata = {'name': FILE_NAME, 'parents': [GDRIVE_FOLDER_ID]}
            service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            print(f"Created new Drive log: {FILE_NAME}")

        return streak

    except Exception as e:
        print(f"Google Drive Error: {e}")
        return None


def get_current_streak_only():
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    FILE_NAME = "affirmation_log.txt"
    token_path = '/home/roverpi/token.json'

    if not os.path.exists(token_path):
        return 0

    try:
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                return 0

        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(
            q=f"'{GDRIVE_FOLDER_ID}' in parents and name='{FILE_NAME}' and trashed=false",
            fields="files(id)"
        ).execute()
        items = results.get('files', [])
        if not items:
            return 0

        content = service.files().get_media(fileId=items[0]['id']).execute().decode('utf-8')
        lines = [line for line in content.strip().split('\n') if line.strip()]
        if not lines:
            return 0

        parts = lines[-1].split(" | ")
        if len(parts) < 2:
            return 0
        return int(parts[1].replace("Streak:", "").strip())
    except Exception as e:
        print(f"Warning: Could not read streak history: {e}")
        return 0


def format_streak_unit(streak_value):
    return "day" if int(streak_value) == 1 else "days"

affirmation_heard = False

# -------------- DRIVING CONTROLS --------------
# Motor and state configuration for robot movement and navigation.
# ----------------------------------------------
ena = PWMOutputDevice(16)
in1 = DigitalOutputDevice(17)
in2 = DigitalOutputDevice(27)
enb = PWMOutputDevice(26)
in3 = DigitalOutputDevice(22)
in4 = DigitalOutputDevice(23)

speed_multiplier = 0.8  # for 8V
speed_multiplier = 1.07  # for 6V
auto_base_speed = 0.25 * speed_multiplier
auto_soft_inner = 0.25 * speed_multiplier
auto_soft_outer = 0.3 * speed_multiplier
auto_hard_push = 0.35 * speed_multiplier
auto_hard_rev = -0.35 * speed_multiplier

pos_x, pos_y, heading = 0.0, 0.0, 1.5708
last_detection_time = 0
MEMORY_TIMEOUT = 0.05
END_RUN_TIMEOUT = 2.0
robot_state = 0
active_mode = "TIP"
last_slant = 0
last_tip_x = 160
global_running = True
first_capture_done = threading.Event()
FIRST_CAPTURE_WAIT_TIMEOUT = 5.0
action_button = None
power_button = None
keep_beeping = threading.Event()
system_awake = threading.Event()
stop_run_requested = threading.Event()
shutdown_requested = threading.Event()

affirmation_heard = False
mission_completed = False
current_affirmation_global = ""
affirmation_heard = False
autonomous_active = False

hl = HuskyLensLibrary("I2C", "", address=0x32)

def set_motors(left, right):
    min_move = 0
    adj_left = left; adj_right = right
    if adj_left != 0 and abs(adj_left) < min_move:
        adj_left = min_move if adj_left > 0 else -min_move
    if adj_right != 0 and abs(adj_right) < min_move:
        adj_right = min_move if adj_right > 0 else -min_move
    if adj_left > 0:
        in1.on(); in2.off(); ena.value = min(abs(adj_left), 1.0)
    elif adj_left < 0:
        in1.off(); in2.on(); ena.value = min(abs(adj_left), 1.0)
    else:
        in1.off(); in2.off(); ena.value = 0
    if adj_right > 0:
        in3.on(); in4.off(); enb.value = min(abs(adj_right), 1.0)
    elif adj_right < 0:
        in3.off(); in4.on(); enb.value = min(abs(adj_right), 1.0)
    else:
        in3.off(); in4.off(); enb.value = 0

# --- CAMERA THREAD ---
def background_camera_loop():
    global global_running
    save_folder = "/home/roverpi/images"
    if not os.path.exists(save_folder): os.makedirs(save_folder)
    for f in glob.glob(f"{save_folder}/*.jpg"): os.remove(f)

    try:
        picam2 = Picamera2()
        picam2.configure(picam2.create_still_configuration(main={"size": (800, 600)}))
        picam2.start()
        
        print("SNAP! Immediate Start-Photo Taken (Capture 0000).")
        img_count = 0
        
        picam2.capture_file(f"{save_folder}/capture_{img_count:04d}.jpg")
        img_count += 1
        first_capture_done.set()
        
        while global_running:
            time.sleep(CAPTURE_INTERVAL_SEC)
            picam2.capture_file(f"{save_folder}/capture_{img_count:04d}.jpg")
            img_count += 1
            
        picam2.stop(); picam2.close()
    except Exception as e:
        first_capture_done.set()
        print(f"Camera Error: {e}")

def openrouter_chat_completion(payload, request_tag):
    if not API_KEY: return None, "missing_api_key"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    
    # Force the model to be deterministic (no "creativity")
    payload["temperature"] = 0.0 
    payload["top_p"] = 0.1

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost/roverpi",
        "X-Title": "RoverPi Robot Core"
    }

    try:
        res = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
    except requests.exceptions.RequestException as e:
        return None, f"network_error:{e}"

    if res.status_code != 200:
        body = res.text.strip().replace("\n", " ")
        body = body[:300] + ("..." if len(body) > 300 else "")
        return None, f"http_{res.status_code}:{body}"

    try:
        data = res.json()
        message = data["choices"][0]["message"]["content"]
    except Exception as e:
        body = res.text.strip().replace("\n", " ")
        body = body[:300] + ("..." if len(body) > 300 else "")
        return None, f"bad_response:{e}; body={body}"

    if isinstance(message, list):
        text_parts = [part.get("text", "") for part in message if isinstance(part, dict)]
        message = " ".join(text_parts).strip()
    else:
        message = str(message).strip()

    if not message:
        return None, "empty_message"
    return message, None


# -------------- OCR LOGIC --------------
# Sends images to OCR model for literal text extraction.
# ----------------------------------------
def vision_call_multi(image_paths):
    try:
        content = [{
            "type": "text",
            "text": (
                "You are a Literal OCR engine. Your ONLY goal is to transcribe text exactly as seen. "
                "1. These are sequential, OVERLAPPING strips from a camera. "
                "2. Transcribe exactly what you see. Do NOT fix grammar, do NOT fix spelling, and do NOT try to make the sentence 'cohesive'. "
                "3. If words or parts of words are repeated across images (overlap), merge them into a single word. "
                "4. NEVER 'hallucinate' or guess a different sentence. If the handwriting is messy, just give your best literal guess of the characters. "
                "Respond with ONLY the literal text and nothing else."
            )
        }]

        for image_path in image_paths:
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

        model_candidates = []
        for m in VISION_MODELS:
            if m and m not in model_candidates:
                model_candidates.append(m)

        last_err = None
        for model_name in model_candidates:
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": content}]
            }
            text, err = openrouter_chat_completion(payload, request_tag=f"multi:{model_name}")
            if not err:
                print(f"Multi-strip result ({model_name}): {text}")
                return text
            last_err = err
            print(f"Model failed for multi-strip request ({model_name}): {err}")

        print(f"OpenRouter multi-strip error: {last_err}")
        return f"ERROR::{last_err}"
    except Exception as e:
        err = f"image_read_error:{e}"
        print(f"OpenRouter multi-strip error: {err}")
        return f"ERROR::{err}"


# -------------- RESULTS PROCESSING --------------
# Processes captured images, runs OCR, and returns detected text.
# -----------------------------------------------
def process_mission_results():
    save_folder = "/home/roverpi/images"
    images = sorted([img for img in os.listdir(save_folder) if img.startswith("capture_")])
    if not images:
        print("\nMISSION FAILED: No images captured.")
        return None

    if len(images) > 4: images = images[:-4]

    strips = [images[i:i + STRIP_SIZE] for i in range(0, len(images), STRIP_SIZE)]
    strip_paths = []

    for idx, chunk in enumerate(strips):
        sample = Image.open(os.path.join(save_folder, chunk[0])).transpose(Image.ROTATE_90)
        w, h = sample.size
        strip_img = Image.new('RGB', (len(chunk) * w, h))
        for i, img_file in enumerate(chunk):
            img = Image.open(os.path.join(save_folder, img_file)).transpose(Image.ROTATE_90)
            strip_img.paste(img, (i * w, 0))
        strip_img = ImageEnhance.Contrast(strip_img).enhance(1.8)
        strip_img = ImageEnhance.Sharpness(strip_img).enhance(2.0)
        path = os.path.join(save_folder, f"strip_{idx}.jpg")
        strip_img.save(path); strip_paths.append(path)

    print(f"\nBeaming {len(strip_paths)} strips in one vision request...")
    final = vision_call_multi(strip_paths)

    if not isinstance(final, str) or not final:
        print("\nMISSION REPORT: Vision returned no output.")
        return None
    if final.startswith("ERROR::"):
        print("\nMISSION REPORT: Vision request failed.")
        return None
    if final.strip().upper() == "NULL":
        print("\nMISSION REPORT: No readable text found.")
        return None

    print("\n" + "="*40 + f"\nFINAL MESSAGE: {final}\n" + "="*40 + "\n")
    return final



# -------------- MAIN GAME LOOP --------------
# Main control loop for robot operation and user interaction.
# ---------------------------------------------

setup_buttons()
print("RoverPi Morning Coach Initialised.")
enforce_boot_volume()
threading.Thread(target=alarm_beep_thread, daemon=True).start()

current_affirmation_global = get_random_affirmation()
prefetch_affirmation_tts_async(f"Good morning. Your affirmation is: {current_affirmation_global}")
system_awake.set()
start_beeping()

if power_button is None:
    print("Warning: Power button unavailable. Auto-waking system for keyboard fallback.")
    affirmation_heard = True

print("Standby mode: tap power button to hear/replay affirmation, then press action to start. Hold power to power off.")

try:
    while not shutdown_requested.is_set():
        if not system_awake.is_set():
            time.sleep(0.1)
            continue

        if not current_affirmation_global:
            current_affirmation_global = get_random_affirmation()
            affirmation_heard = False
        current_affirmation = current_affirmation_global
        current_affirmation_global = current_affirmation
        current_streak = get_current_streak_only()
        prefetch_affirmation_tts_async(f"Good morning. Your affirmation is: {current_affirmation}")
        print(f"System awake. Current streak: {current_streak}")

        while system_awake.is_set() and not shutdown_requested.is_set():
            if not wait_for_action_press("Press Action Button to start scan and line-follow.", stop_beep_on_press=True):
                break

            if not affirmation_heard:
                speak("Please get today's affirmation before starting the engines!")
                continue

            stop_run_requested.clear()
            global_running = True
            autonomous_active = True
            first_capture_done = threading.Event()
            last_detection_time = time.time()

            print("\nRoverPi Autonomous Mode Starting...")
            cam_thread = threading.Thread(target=background_camera_loop, daemon=True)
            cam_thread.start()

            set_motors(0, 0)
            # Do NOT reset autonomous_active here; keep it True through result handling
            print("Waiting for first startup image before movement...")
            if first_capture_done.wait(timeout=FIRST_CAPTURE_WAIT_TIMEOUT):
                print("First startup image captured. Beginning movement logic.")
            else:
                print("Warning: First capture wait timed out. Proceeding to avoid deadlock.")

            while global_running and system_awake.is_set() and not stop_run_requested.is_set() and not shutdown_requested.is_set():
                try:
                    arrows = hl.arrows()
                except Exception as e:
                    print(f"Warning: HuskyLens glitch: {e}. Soft reconnecting...")
                    set_motors(0, 0)
                    time.sleep(0.5)
                    try:
                        hl = HuskyLensLibrary("I2C", "", address=0x32)
                    except Exception:
                        pass
                    continue

                if arrows and len(arrows) > 0:
                    last_detection_time = time.time()
                    a = arrows[0]
                    tip_x, tip_y, tail_x = a.xHead, a.yHead, a.xTail
                    last_tip_x = tip_x
                    if tip_y < 60:
                        active_mode = "TIP"
                        last_slant = 0
                        if tip_x < 100:
                            robot_state = 4
                        elif 100 <= tip_x < 150:
                            robot_state = 2
                        elif 170 < tip_x <= 220:
                            robot_state = 3
                        elif tip_x > 220:
                            robot_state = 5
                        else:
                            robot_state = 1
                    else:
                        active_mode = "VEC"
                        last_slant = tip_x - tail_x
                        if tip_x > 250:
                            robot_state = 5
                        elif tip_x < 70:
                            robot_state = 4
                        elif last_slant < -40:
                            robot_state = 4
                        elif -40 <= last_slant < -15:
                            robot_state = 2
                        elif 15 < last_slant <= 40:
                            robot_state = 3
                        elif last_slant > 40:
                            robot_state = 5
                        else:
                            robot_state = 1

                if time.time() - last_detection_time > MEMORY_TIMEOUT:
                    if robot_state != 0:
                        print("!!! CAMERA LOST LINE !!!")
                    robot_state = 0
                    set_motors(0, 0)
                    if time.time() - last_detection_time > END_RUN_TIMEOUT:
                        global_running = False
                        break

                if robot_state == 4:
                    set_motors(auto_hard_rev, auto_hard_push)
                    heading += 0.0075
                elif robot_state == 5:
                    set_motors(auto_hard_push, auto_hard_rev)
                    heading -= 0.0075
                elif robot_state == 2:
                    set_motors(auto_soft_inner, auto_soft_outer)
                    heading += 0.002
                    pos_x += math.cos(heading) * 0.8
                    pos_y += math.sin(heading) * 0.8
                elif robot_state == 3:
                    set_motors(auto_soft_outer, auto_soft_inner)
                    heading -= 0.002
                    pos_x += math.cos(heading) * 0.8
                    pos_y += math.sin(heading) * 0.8
                elif robot_state == 1:
                    set_motors(auto_base_speed, auto_base_speed)
                    pos_x += math.cos(heading) * 1.0
                    pos_y += math.sin(heading) * 1.0
                else:
                    set_motors(0, 0)

            set_motors(0, 0)


            if not system_awake.is_set() or stop_run_requested.is_set() or shutdown_requested.is_set():
                autonomous_active = False
                continue


            detected_text = process_mission_results()
            if detected_text:
                print(f"\n[DEBUG] The OCR read your floor as: '{detected_text}'\n")
                judgment = evaluate_affirmation(current_affirmation, detected_text)
                if judgment == "PASS":
                    mission_completed = True
                    streak = handle_drive_upload(detected_text)
                    if streak:
                        speak(f"Excellent! Your streak is now {streak} {format_streak_unit(streak)}. See you tomorrow!")
                    else:
                        speak("Great! Now you are ready to seize the day.")
                    system_awake.clear()
                    stop_beeping()
                    autonomous_active = False
                    break

                stop_beeping()
                speak(f"That's not quite today's affirmation. Try again if you want to keep your {current_streak} day streak!")
                autonomous_active = False
            else:
                stop_beeping()
                speak("I couldn't read your writing. Let's try again.")
                autonomous_active = False

except KeyboardInterrupt:
    global_running = False
    stop_beeping()
    system_awake.clear()
    shutdown_requested.set()
    set_motors(0, 0)
