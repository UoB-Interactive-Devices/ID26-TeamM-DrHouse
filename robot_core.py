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

# --- NEW: GOOGLE DRIVE IMPORTS ---
# --- GOOGLE DRIVE OAUTH IMPORTS ---
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageOps, ImageEnhance
from gpiozero import PWMOutputDevice, DigitalOutputDevice
from huskylib import HuskyLensLibrary
from picamera2 import Picamera2

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
        print(f"⚠️ Could not load .env file ({path}): {e}")

load_env_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ==========================================
# --- YOUR KEYS & CONFIG ---
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

# --- GOOGLE DRIVE CONFIG ---
GDRIVE_CREDS = "/home/roverpi/credentials.json"
GDRIVE_FOLDER_ID = "1xbg2vaMZ2UPwY5aEKG-ZxQxcfJb1JHYC"
# ==========================================

def get_random_affirmation():
    try:
        with open("affirmations.txt", "r") as f:
            lines = [line.strip() for line in f if line.strip()]
        return random.choice(lines) if lines else "I am ready"
    except FileNotFoundError:
        print("⚠️ affirmations.txt not found! Using fallback.")
        return "I am ready"

def speak(text):
    print(f"🔊 Robot says: '{text}'")
    try:
        subprocess.run(["pinctrl", "set", "12", "a0"], check=False)
        subprocess.run(["espeak", "-ven+m3", "-s150", text], stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"⚠️ Audio failed: {e}")

def evaluate_affirmation(target, detected):
    print("\n⚖️ Evaluating the user's handwritten affirmation...")
    prompt = f"""
    You are a lenient judge grading a handwritten affirmation.
    The target phrase the user was supposed to write is: "{target}"
    The robot's camera scanned and read: "{detected}"
    
    Are these similar enough? (Ignore minor spelling mistakes, messy handwriting errors, or missing single words).
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
        print("⚠️ Google Drive OAuth not configured. Skipping upload.")
        return None

    print("\n☁️ Connecting to Google Drive as YOU...")
    
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
                    print(f"⚠️ Could not parse previous streak from log: {e}")

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
            print(f"✅ Appended new line to: {FILE_NAME}")
        else:
            # First time ever running it: Create the file
            file_metadata = {'name': FILE_NAME, 'parents': [GDRIVE_FOLDER_ID]}
            service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            print(f"✅ Created new Drive log: {FILE_NAME}")

        return streak

    except Exception as e:
        print(f"❌ Google Drive Error: {e}")
        return None

# --- Motor/State Configuration (100% ORIGINAL) ---
ena = PWMOutputDevice(16); in1 = DigitalOutputDevice(17); in2 = DigitalOutputDevice(27)
enb = PWMOutputDevice(26); in3 = DigitalOutputDevice(22); in4 = DigitalOutputDevice(23)

speedMultiplier = 0.8
autoBaseSpeed = 0.25 * speedMultiplier
autoSoftInner = 0.25 * speedMultiplier
autoSoftOuter = 0.3 * speedMultiplier
autoHardPush  = 0.35 * speedMultiplier
autoHardRev   = -0.35 * speedMultiplier

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
        
        print("📸 SNAP! Immediate Start-Photo Taken (Capture 0000).")
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
        print(f"❌ Camera Error: {e}")

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

# --- VISION CALL ---
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
                print(f"🔎 Multi-strip result ({model_name}): {text}")
                return text
            last_err = err
            print(f"⚠️ Model failed for multi-strip request ({model_name}): {err}")

        print(f"❌ OpenRouter multi-strip error: {last_err}")
        return f"ERROR::{last_err}"
    except Exception as e:
        err = f"image_read_error:{e}"
        print(f"❌ OpenRouter multi-strip error: {err}")
        return f"ERROR::{err}"

# --- RESULTS PROCESSING ---
def process_mission_results():
    save_folder = "/home/roverpi/images"
    images = sorted([img for img in os.listdir(save_folder) if img.startswith("capture_")])
    if not images:
        print("\n❌ MISSION FAILED: No images captured.")
        return None

    if len(images) > 4: images = images[:-4]

    strips = [images[i:i + STRIP_SIZE] for i in range(0, len(images), STRIP_SIZE)]
    strip_paths = []

    for idx, chunk in enumerate(strips):
        sample = Image.open(os.path.join(save_folder, chunk[0])).transpose(Image.ROTATE_270)
        w, h = sample.size
        strip_img = Image.new('RGB', (len(chunk) * w, h))
        for i, img_file in enumerate(chunk):
            img = Image.open(os.path.join(save_folder, img_file)).transpose(Image.ROTATE_270)
            strip_img.paste(img, (i * w, 0))
        strip_img = ImageEnhance.Contrast(strip_img).enhance(1.8)
        strip_img = ImageEnhance.Sharpness(strip_img).enhance(2.0)
        path = os.path.join(save_folder, f"strip_{idx}.jpg")
        strip_img.save(path); strip_paths.append(path)

    print(f"\n🚀 Beaming {len(strip_paths)} strips in ONE vision request...")
    final = vision_call_multi(strip_paths)

    if not isinstance(final, str) or not final:
        print("\n🤖 MISSION REPORT: Vision returned no output.")
        return None
    if final.startswith("ERROR::"):
        print("\n🤖 MISSION REPORT: Vision request failed.")
        return None
    if final.strip().upper() == "NULL":
        print("\n🤖 MISSION REPORT: AI found no readable text.")
        return None

    print("\n" + "="*40 + f"\n🤖 FINAL MESSAGE: {final}\n" + "="*40 + "\n")
    return final


# ==============================================================
# --- MAIN GAME LOOP ---
# ==============================================================

current_affirmation = get_random_affirmation()
speak(current_affirmation)

print("\n" + "*"*50)
print(f"📝 Target Affirmation: {current_affirmation}")
print("*"*50)
input("\n👉 Write this on the floor, line up the robot, and press [ENTER] to start: ")

print("\n🤖 RoverPi Autonomous Mode Starting...")
cam_thread = threading.Thread(target=background_camera_loop, daemon=True)
cam_thread.start()

set_motors(0, 0)
print("⏳ Waiting for first startup image before movement...")
if first_capture_done.wait(timeout=FIRST_CAPTURE_WAIT_TIMEOUT):
    print("✅ First startup image captured. Beginning movement logic.")
else:
    print("⚠️ First capture wait timed out. Proceeding to avoid deadlock.")

run_start_time = time.time()

try:
    while global_running:
        try:
            arrows = hl.arrows()
        except Exception as e:
            print(f"⚠️ HuskyLens glitch: {e}. Soft reconnecting...")
            set_motors(0, 0)
            time.sleep(0.5)
            try:
                hl = HuskyLensLibrary("I2C", "", address=0x32)
            except:
                pass
            continue

        if arrows and len(arrows) > 0:
            last_detection_time = time.time()
            a = arrows[0]; tip_x, tip_y, tail_x = a.xHead, a.yHead, a.xTail
            last_tip_x = tip_x
            if tip_y < 60:
                active_mode = "TIP"; last_slant = 0
                if tip_x < 100: robot_state = 4
                elif 100 <= tip_x < 150: robot_state = 2
                elif 170 < tip_x <= 220: robot_state = 3
                elif tip_x > 220: robot_state = 5
                else: robot_state = 1
            else:
                active_mode = "VEC"; last_slant = tip_x - tail_x
                if tip_x > 250: robot_state = 5
                elif tip_x < 70: robot_state = 4
                elif last_slant < -40: robot_state = 4
                elif -40 <= last_slant < -15: robot_state = 2
                elif 15 < last_slant <= 40: robot_state = 3
                elif last_slant > 40: robot_state = 5
                else: robot_state = 1
        if time.time() - last_detection_time > MEMORY_TIMEOUT:
            if robot_state != 0: print("!!! CAMERA LOST LINE !!!")
            robot_state = 0; set_motors(0, 0)
            if time.time() - last_detection_time > END_RUN_TIMEOUT: global_running = False; break

        if robot_state == 4: set_motors(autoHardRev, autoHardPush); heading += 0.0075
        elif robot_state == 5: set_motors(autoHardPush, autoHardRev); heading -= 0.0075
        elif robot_state == 2: set_motors(autoSoftInner, autoSoftOuter); heading += 0.002; pos_x += math.cos(heading) * 0.8; pos_y += math.sin(heading) * 0.8
        elif robot_state == 3: set_motors(autoSoftOuter, autoSoftInner); heading -= 0.002; pos_x += math.cos(heading) * 0.8; pos_y += math.sin(heading) * 0.8
        elif robot_state == 1: set_motors(autoBaseSpeed, autoBaseSpeed); pos_x += math.cos(heading) * 1.0; pos_y += math.sin(heading) * 1.0
        else: set_motors(0, 0)
        
    set_motors(0, 0)
    detected_text = process_mission_results()
    
    # 5. Judge and Upload
    if detected_text:
        print(f"\n👀 [DEBUG] The AI read your floor as: '{detected_text}'\n")
        judgment = evaluate_affirmation(current_affirmation, detected_text)
        if judgment == "PASS":
            streak = handle_drive_upload(detected_text)
            if streak:
                speak(f"Great! Now you are ready to seize the day. Your current streak is {streak} days!")
            else:
                speak("Great! Now you are ready to seize the day.")
        else:
            speak("Please write the correct affirmation")
    else:
        speak("I couldn't read your writing. Let's try again.")
        
except KeyboardInterrupt:
    global_running = False; set_motors(0, 0)
