import socket
import cv2
import numpy as np
import threading
import time
import struct
import os
import glob
import json
from collections import deque, Counter

# ログ抑制
os.environ["ONNXRUNTIME_LOG_LEVEL"] = "3"
import onnxruntime
from insightface.app import FaceAnalysis

UNITY_IP = "192.168.137.205"  # Quest3のIPアドレス
PORT = 6002
CAMERA_ID = 1                 # 外部カメラ
JPEG_QUALITY = 90
THRESHOLD = 0.5
VOTE_COUNT = 10
CONFIG_FILE = "config.json"

# 滑らかさの調整値 (0.1 〜 1.0)
SMOOTH_FACTOR = 0.4

print("--- お名前アシストAR ---")

# 1. GPUチェック
providers = onnxruntime.get_available_providers()
if 'CUDAExecutionProvider' in providers:
    print(" GPU (CUDA) を使用します")
    PROV = ['CUDAExecutionProvider', 'CPUExecutionProvider']
else:
    print(" GPUが見つかりません。CPUで動作します")
    PROV = ['CPUExecutionProvider']

# 2. AI準備
try:
    user_home = os.path.expanduser("~")
    antelope_path = os.path.join(user_home, ".insightface", "models", "antelopev2")
    if os.path.exists(antelope_path):
        app = FaceAnalysis(name='antelopev2', providers=PROV)
    else:
        app = FaceAnalysis(name='buffalo_l', providers=PROV)
except:
    app = FaceAnalysis(name='buffalo_l', providers=PROV)

app.prepare(ctx_id=0, det_size=(640, 640))

# 3. 学習データ
faces_dir = "faces"
known_embeddings = []
known_names = []
if not os.path.exists(faces_dir): os.makedirs(faces_dir)
files = glob.glob(os.path.join(faces_dir, "*"))
print("顔データをロード中...")
for img_path in files:
    filename = os.path.basename(img_path)
    if filename.startswith("."): continue
    name = filename.split('.')[0].split('_')[0]
    img = cv2.imread(img_path)
    if img is None: continue
    faces = app.get(img)
    if len(faces) > 0:
        target_face = sorted(faces, key=lambda x: (x.bbox[2]-x.bbox[0]) * (x.bbox[3]-x.bbox[1]), reverse=True)[0]
        known_embeddings.append(target_face.embedding)
        known_names.append(name)
        print(f"ロード完了: {name}")

# 4. 変数
vote_history = deque(maxlen=VOTE_COUNT) 
current_display_name = "スキャン中..."
current_display_color = (150, 150, 150)
is_ai_running = False

# スムージング用変数を追加
prev_box = None 

def ai_worker(high_res_image):
    global vote_history, current_display_name, current_display_color, is_ai_running
    try:
        faces = app.get(high_res_image)
        res_name = "分かりません。"
        if len(faces) > 0:
            target_face = sorted(faces, key=lambda x: (x.bbox[2]-x.bbox[0]) * (x.bbox[3]-x.bbox[1]), reverse=True)[0]
            target_emb = target_face.embedding
            max_sim = -1
            for i, known_emb in enumerate(known_embeddings):
                sim = np.dot(target_emb, known_emb)
                if sim > max_sim:
                    max_sim = sim
                    if sim >= THRESHOLD:
                        res_name = known_names[i]
        vote_history.append(res_name)
        if len(vote_history) > 0:
            most_common = Counter(vote_history).most_common(1)[0]
            winner_name = most_common[0]
            count = most_common[1]
            if count >= 3:
                if winner_name != "分かりません。":
                    current_display_name = winner_name
                    current_display_color = (0, 255, 0)
                else:
                    if count >= VOTE_COUNT * 0.8:
                        current_display_name = "分かりません。"
                        current_display_color = (0, 0, 255)
    except:
        pass
    finally:
        is_ai_running = False

# 5. カメラクラス
class WebcamStream:
    def __init__(self, src=0):
        self.stream = cv2.VideoCapture(src)
        self.stream.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self.stream.set(cv2.CAP_PROP_FPS, 60)
        self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        (self.grabbed, self.frame) = self.stream.read()
        self.stopped = False
    def start(self):
        threading.Thread(target=self.update, daemon=True).start()
        return self
    def update(self):
        while not self.stopped:
            self.grabbed, self.frame = self.stream.read()
    def read(self):
        return self.frame
    def stop(self):
        self.stopped = True
        self.stream.release()

# 6. 設定
def load_settings():
    defaults = {"x": 500, "y": 500, "size": 70}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f: return json.load(f)
        except: return defaults
    return defaults

def save_settings(x, y, size):
    data = {"x": x, "y": y, "size": size}
    with open(CONFIG_FILE, 'w') as f: json.dump(data, f)
    print(f"設定保存: {CONFIG_FILE}")

# 7. UI初期化
def nothing(x): pass
window_name = "Debug Monitor (Smooth)"
cv2.namedWindow(window_name)
settings = load_settings()
cv2.createTrackbar("Shift X", window_name, settings["x"], 1000, nothing) 
cv2.createTrackbar("Shift Y", window_name, settings["y"], 1000, nothing) 
cv2.createTrackbar("Size %", window_name, settings["size"], 200, nothing)

# 8. メイン実行
vs = WebcamStream(src=CAMERA_ID).start()
time.sleep(2.0)
fps_start_time = time.time()
frame_count = 0

print("システム起動。Unity待機中...")

while True:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        sock.connect((UNITY_IP, PORT))
        print(f"Unity ({UNITY_IP}) に接続！")

        while True:
            frame = vs.read()
            if frame is None: continue
            frame_count += 1
            
            frame_resized = cv2.resize(frame, (640, 360))
            h, w, _ = frame_resized.shape
            
            # 透過用黒背景
            send_image = np.zeros((h, w, 3), dtype=np.uint8)

            val_x = cv2.getTrackbarPos("Shift X", window_name)
            val_y = cv2.getTrackbarPos("Shift Y", window_name)
            val_size = cv2.getTrackbarPos("Size %", window_name)

            offset_x = val_x - 500
            offset_y = val_y - 500
            scale_factor = val_size / 100.0

            faces = app.get(frame_resized)
            
            if len(faces) > 0:
                # ターゲットの顔座標
                detection = sorted(faces, key=lambda x: (x.bbox[2]-x.bbox[0]) * (x.bbox[3]-x.bbox[1]), reverse=True)[0]
                box = detection.bbox.astype(int)
                rx1, ry1, rx2, ry2 = box[0], box[1], box[2], box[3]
                
                cx = rx1 + (rx2 - rx1) / 2
                cy = ry1 + (ry2 - ry1) / 2
                bw = int((rx2 - rx1) * scale_factor)
                bh = int((ry2 - ry1) * scale_factor)
                
                target_x = cx - bw/2 + offset_x
                target_y = cy - bh/2 + offset_y
                target_w = bw
                target_h = bh

                # ここでスムージング計算
                if prev_box is None:
                    # 初回はいきなりそこに移動
                    current_x, current_y = target_x, target_y
                    current_w, current_h = target_w, target_h
                else:
                    px, py, pw, ph = prev_box
                    current_x = px * (1 - SMOOTH_FACTOR) + target_x * SMOOTH_FACTOR
                    current_y = py * (1 - SMOOTH_FACTOR) + target_y * SMOOTH_FACTOR
                    current_w = pw * (1 - SMOOTH_FACTOR) + target_w * SMOOTH_FACTOR
                    current_h = ph * (1 - SMOOTH_FACTOR) + target_h * SMOOTH_FACTOR

                # 計算結果を保存
                prev_box = (current_x, current_y, current_w, current_h)

                # 描画用に整数に戻す
                x = int(current_x)
                y = int(current_y)
                bw = int(current_w)
                bh = int(current_h)
                
                x, y = max(0, x), max(0, y)

                if bw > 10:
                    if not is_ai_running and frame_count % 5 == 0:
                        is_ai_running = True
                        threading.Thread(target=ai_worker, args=(frame.copy(),), daemon=True).start()

                    display_name = current_display_name
                    display_color = current_display_color

                    cv2.rectangle(send_image, (x, y), (x+bw, y+bh), display_color, 2)
                    cv2.putText(send_image, display_name, (x, y+bh+25), 2, 0.7, display_color, 2)
                    
                    cv2.rectangle(frame_resized, (x, y), (x+bw, y+bh), display_color, 2)
                    info = f"Settings - X:{val_x} Y:{val_y} S:{val_size}"
                    cv2.putText(frame_resized, info, (10, h - 20), 2, 0.6, (0, 255, 255), 1)

            else:
                # 顔が見えなくなったらリセット（次に見つけた時パッと表示するため）
                prev_box = None

            fps = frame_count / (time.time() - fps_start_time)
            cv2.putText(frame_resized, f"FPS: {int(fps)}", (10, 30), 2, 1, (0, 255, 255), 2)

            _, buffer = cv2.imencode('.jpg', send_image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            data = buffer.tobytes()
            sock.sendall(b'IMG!' + struct.pack(">L", len(data)) + data)

            cv2.imshow(window_name, frame_resized)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                save_settings(val_x, val_y, val_size)
                vs.stop()
                sock.close()
                exit()

    except Exception as e:
        print(f"Unity待機中... ({e})")

        time.sleep(2)
