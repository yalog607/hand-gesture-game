# Điều khiển game bằng tay (OpenCV + MediaPipe)

## Cài đặt
```bash
pip install -r requirements.txt
```
(Dùng Python 3.9–3.12. `mediapipe==0.10.21` được ghim vì các bản mới hơn có thể bỏ API `mp.solutions`.)

## Chơi Sky Hopper
```bash
python sky_hopper.py              # chụm ngón cái + ngón trỏ = bay lên
python sky_hopper.py --mode fist  # nắm tay = bay lên
python sky_hopper.py --no-camera  # chỉ dùng phím SPACE
```

## Điều khiển game khác (giả lập phím)
```bash
python hand_controller.py --key space
```
Mở game trên trình duyệt/máy tính, focus vào cửa sổ game, mỗi lần chụm tay sẽ bấm phím SPACE.

## Luồng xử lý
1. **OpenCV** `VideoCapture` đọc khung hình → `flip` (soi gương) → `cvtColor` BGR→RGB.
2. **MediaPipe Hands** `process(rgb)` → 21 khớp tay (x, y chuẩn hoá 0..1).
3. Nhận diện cử chỉ:
   - *pinch*: `dist(khớp 4, khớp 8) / dist(khớp 0, khớp 9)` < 0.30 → bật, > 0.45 → thả (có trễ để không bị rung).
   - *fist*: đếm ngón duỗi (đầu ngón xa cổ tay hơn khớp PIP); ≤ 1 ngón duỗi = nắm tay.
4. Khi cử chỉ chuyển **thả → bật** → sinh 1 sự kiện FLAP (có cooldown 0.15s).
5. Camera chạy trong luồng riêng nên game vẫn mượt 60 fps; game lấy sự kiện qua `consume_flaps()`.
