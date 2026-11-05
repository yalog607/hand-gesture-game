"""
Bộ điều khiển game bằng tay.

- OpenCV  : đọc webcam, lật ảnh, đổi màu BGR->RGB, vẽ thông tin lên khung hình.
- MediaPipe Hands : nhận ảnh RGB, trả về 21 khớp (landmark) của bàn tay.

Từ 21 khớp ta nhận diện cử chỉ:
  * "pinch": chụm ngón cái (khớp 4) và ngón trỏ (khớp 8)
  * "fist" : nắm tay (4 ngón dài đều gập)
Mỗi lần cử chỉ chuyển từ "thả" -> "bật" sinh ra 1 sự kiện FLAP (vỗ cánh).

Chạy độc lập để điều khiển game bất kỳ bằng cách giả lập phím:
    python hand_controller.py --key space
"""
import argparse
import math
import threading
import time

import cv2
import mediapipe as mp

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils
mp_styles = mp.solutions.drawing_styles

# Chỉ số các khớp MediaPipe
WRIST, THUMB_TIP, INDEX_MCP, INDEX_TIP, MIDDLE_MCP = 0, 4, 5, 8, 9
FINGER_TIPS = (8, 12, 16, 20)
FINGER_PIPS = (6, 10, 14, 18)


class HandController:
    def __init__(self, camera_index=0, mode="pinch", width=640, height=480,
                 mirror=True, pinch_on=0.30, pinch_off=0.45, cooldown=0.15):
        self.camera_index = camera_index
        self.mode = mode
        self.width, self.height = width, height
        self.mirror = mirror
        self.pinch_on, self.pinch_off = pinch_on, pinch_off   # ngưỡng có trễ (hysteresis)
        self.cooldown = cooldown

        self._lock = threading.Lock()
        self._flaps = 0
        self._frame = None
        self._last_flap = 0.0
        self._thread = None
        self.cap = None
        self.running = False

        # Trạng thái công khai (chỉ đọc)
        self.hand_visible = False
        self.gesture_active = False
        self.value = None          # tỉ lệ pinch hoặc số ngón duỗi
        self.fps = 0.0

    # ---------------- vòng đời ----------------
    def start(self):
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            raise RuntimeError(f"Không mở được camera {self.camera_index}")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        if self.cap:
            self.cap.release()

    # ---------------- API cho game ----------------
    def consume_flaps(self):
        """Trả về số lần FLAP kể từ lần gọi trước, rồi đặt lại về 0."""
        with self._lock:
            n, self._flaps = self._flaps, 0
        return n

    def get_frame(self):
        """Khung hình BGR mới nhất (đã vẽ khớp tay), hoặc None."""
        with self._lock:
            return self._frame

    # ---------------- xử lý ----------------
    def _loop(self):
        t_prev = time.time()
        with mp_hands.Hands(max_num_hands=1, model_complexity=0,
                            min_detection_confidence=0.6,
                            min_tracking_confidence=0.5) as hands:
            while self.running:
                ok, frame = self.cap.read()
                if not ok:
                    time.sleep(0.01)
                    continue
                if self.mirror:
                    frame = cv2.flip(frame, 1)

                # OpenCV dùng BGR, MediaPipe cần RGB
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                result = hands.process(rgb)

                visible, active, value = False, False, None
                if result.multi_hand_landmarks:
                    hand = result.multi_hand_landmarks[0]
                    visible = True
                    mp_draw.draw_landmarks(
                        frame, hand, mp_hands.HAND_CONNECTIONS,
                        mp_styles.get_default_hand_landmarks_style(),
                        mp_styles.get_default_hand_connections_style())
                    h, w = frame.shape[:2]
                    pts = [(p.x * w, p.y * h) for p in hand.landmark]
                    active, value = self._detect(pts)
                    if self.mode == "pinch":
                        a = tuple(map(int, pts[THUMB_TIP]))
                        b = tuple(map(int, pts[INDEX_TIP]))
                        cv2.line(frame, a, b, (0, 255, 0) if active else (0, 200, 255), 3)

                now = time.time()
                self.fps = 0.9 * self.fps + 0.1 * (1.0 / max(now - t_prev, 1e-6))
                t_prev = now
                self._draw_hud(frame, visible, active, value)

                with self._lock:
                    # Sườn lên: thả -> bật  => FLAP
                    if active and not self.gesture_active and now - self._last_flap > self.cooldown:
                        self._flaps += 1
                        self._last_flap = now
                    self.gesture_active = active
                    self.hand_visible = visible
                    self.value = value
                    self._frame = frame

    def _detect(self, pts):
        if self.mode == "fist":
            # Ngón duỗi nếu đầu ngón xa cổ tay hơn khớp giữa ngón
            extended = sum(
                _dist(pts[t], pts[WRIST]) > _dist(pts[p], pts[WRIST]) * 1.05
                for t, p in zip(FINGER_TIPS, FINGER_PIPS))
            return extended <= 1, extended

        # pinch: khoảng cách cái-trỏ chia cho kích thước lòng bàn tay
        # (không phụ thuộc tay gần hay xa camera)
        palm = _dist(pts[WRIST], pts[MIDDLE_MCP]) or 1.0
        ratio = _dist(pts[THUMB_TIP], pts[INDEX_TIP]) / palm
        threshold = self.pinch_off if self.gesture_active else self.pinch_on
        return ratio < threshold, ratio

    def _draw_hud(self, frame, visible, active, value):
        if not visible:
            text, color = "Khong thay tay", (0, 0, 255)
        elif self.mode == "pinch":
            text = f"PINCH {value:.2f} {'[FLAP]' if active else ''}"
            color = (0, 255, 0) if active else (255, 255, 255)
        else:
            text = f"FINGERS {value} {'[FIST]' if active else ''}"
            color = (0, 255, 0) if active else (255, 255, 255)
        cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
        cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        cv2.putText(frame, f"{self.fps:4.1f} fps", (10, frame.shape[0] - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ---------- Chế độ độc lập: biến cử chỉ thành phím bấm ----------
def main():
    ap = argparse.ArgumentParser(description="Điều khiển game bằng tay -> phím bấm")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--mode", choices=["pinch", "fist"], default="pinch")
    ap.add_argument("--key", default="space", help="phím gửi đi: space, up, w, ...")
    args = ap.parse_args()

    try:
        from pynput.keyboard import Controller, Key
    except ImportError:
        raise SystemExit("Cần cài pynput: pip install pynput")
    kb = Controller()
    key = getattr(Key, args.key, args.key)

    ctrl = HandController(args.camera, args.mode).start()
    print(f"Đang chạy. Cử chỉ '{args.mode}' => phím '{args.key}'. Nhấn q trong cửa sổ camera để thoát.")
    try:
        while True:
            for _ in range(ctrl.consume_flaps()):
                kb.press(key)
                kb.release(key)
            frame = ctrl.get_frame()
            if frame is not None:
                cv2.imshow("Hand Controller", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        ctrl.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
