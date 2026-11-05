"""
Sky Hopper - game bay luồn qua khe, điều khiển bằng cử chỉ tay.

    python sky_hopper.py                 # chụm ngón cái + trỏ để bay lên
    python sky_hopper.py --mode fist     # nắm tay để bay lên
    python sky_hopper.py --no-camera     # chỉ dùng phím SPACE

Phím: SPACE = bay (dự phòng), ESC = thoát.
"""
import argparse
import random
import sys

import cv2
import pygame

W, H = 800, 600
GRAVITY = 1500.0         # px/s^2
FLAP_VY = -460.0         # vận tốc khi vỗ
SPEED = 200.0            # tốc độ cột chạy sang trái
GAP = 180                # độ rộng khe
PILLAR_W = 80
SPAWN_EVERY = 1.6        # giây
PLAYER_X, PLAYER_R = 200, 18
PREVIEW = (220, 165)     # kích thước ô camera

SKY_TOP, SKY_BOT = (24, 20, 58), (92, 60, 140)
PILLAR, PILLAR_EDGE = (60, 200, 170), (30, 120, 110)
PLAYER, PLAYER_GLOW = (255, 170, 60), (255, 220, 120)


class Pillar:
    def __init__(self, x):
        self.x = x
        self.gap_y = random.randint(120, H - 120 - GAP)
        self.scored = False

    def rects(self):
        return (pygame.Rect(int(self.x), 0, PILLAR_W, self.gap_y),
                pygame.Rect(int(self.x), self.gap_y + GAP, PILLAR_W, H - self.gap_y - GAP))


def make_sky():
    surf = pygame.Surface((W, H))
    for y in range(H):
        t = y / H
        c = [int(a + (b - a) * t) for a, b in zip(SKY_TOP, SKY_BOT)]
        pygame.draw.line(surf, c, (0, y), (W, y))
    rnd = random.Random(7)
    for _ in range(70):
        pygame.draw.circle(surf, (230, 230, 255), (rnd.randint(0, W), rnd.randint(0, H // 2)), rnd.choice((1, 1, 2)))
    return surf


def frame_to_surface(frame):
    small = cv2.resize(frame, PREVIEW)
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    return pygame.image.frombuffer(rgb.tobytes(), PREVIEW, "RGB")


class Game:
    def __init__(self, controller):
        pygame.init()
        pygame.display.set_caption("Sky Hopper - Hand Control")
        self.screen = pygame.display.set_mode((W, H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 28, bold=True)
        self.big = pygame.font.SysFont("arial", 56, bold=True)
        self.sky = make_sky()
        self.ctrl = controller
        self.best = 0
        self.reset()

    def reset(self):
        self.state = "ready"         # ready | playing | over
        self.y, self.vy = H / 2, 0.0
        self.pillars, self.timer = [], 0.0
        self.score, self.over_time = 0, 0.0
        self.trail = []

    def flap(self):
        if self.state == "ready":
            self.state = "playing"
            self.vy = FLAP_VY
        elif self.state == "playing":
            self.vy = FLAP_VY
        elif self.state == "over" and self.over_time > 0.8:
            self.reset()

    def update(self, dt):
        if self.state == "over":
            self.over_time += dt
            return
        if self.state == "ready":
            self.y = H / 2 + 10 * pygame.math.Vector2(1, 0).rotate(pygame.time.get_ticks() * 0.3).y
            return

        self.vy += GRAVITY * dt
        self.y += self.vy * dt
        self.trail = ([(PLAYER_X, self.y)] + self.trail)[:12]

        self.timer += dt
        if self.timer >= SPAWN_EVERY:
            self.timer = 0.0
            self.pillars.append(Pillar(W))
        for p in self.pillars:
            p.x -= SPEED * dt
            if not p.scored and p.x + PILLAR_W < PLAYER_X:
                p.scored = True
                self.score += 1
        self.pillars = [p for p in self.pillars if p.x > -PILLAR_W]

        hit = pygame.Rect(PLAYER_X - PLAYER_R + 4, int(self.y) - PLAYER_R + 4,
                          2 * PLAYER_R - 8, 2 * PLAYER_R - 8)
        if self.y < -PLAYER_R or self.y > H + PLAYER_R or any(
                hit.colliderect(r) for p in self.pillars for r in p.rects()):
            self.state = "over"
            self.best = max(self.best, self.score)

    def text(self, s, font, y, color=(255, 255, 255)):
        img = font.render(s, True, color)
        shadow = font.render(s, True, (0, 0, 0))
        x = W // 2 - img.get_width() // 2
        self.screen.blit(shadow, (x + 2, y + 2))
        self.screen.blit(img, (x, y))

    def draw(self):
        s = self.screen
        s.blit(self.sky, (0, 0))
        for p in self.pillars:
            for r in p.rects():
                pygame.draw.rect(s, PILLAR, r)
                pygame.draw.rect(s, PILLAR_EDGE, r, 4)
            pygame.draw.rect(s, PILLAR_EDGE, (p.x - 6, p.gap_y - 18, PILLAR_W + 12, 18))
            pygame.draw.rect(s, PILLAR_EDGE, (p.x - 6, p.gap_y + GAP, PILLAR_W + 12, 18))

        for i, (tx, ty) in enumerate(self.trail):
            pygame.draw.circle(s, PLAYER_GLOW, (int(tx - i * 6), int(ty)), max(2, PLAYER_R - i * 2) // 2)
        pygame.draw.circle(s, PLAYER_GLOW, (PLAYER_X, int(self.y)), PLAYER_R + 4)
        pygame.draw.circle(s, PLAYER, (PLAYER_X, int(self.y)), PLAYER_R)
        pygame.draw.circle(s, (40, 30, 30), (PLAYER_X + 7, int(self.y) - 5), 4)

        self.text(str(self.score), self.big, 20)
        if self.state == "ready":
            self.text("Chum ngon / nam tay de bat dau", self.font, H // 2 + 60)
        elif self.state == "over":
            self.text("GAME OVER", self.big, H // 2 - 80, (255, 120, 120))
            self.text(f"Diem: {self.score}   Ky luc: {self.best}", self.font, H // 2)
            if self.over_time > 0.8:
                self.text("Vo canh de choi lai", self.font, H // 2 + 45)

        if self.ctrl:
            frame = self.ctrl.get_frame()
            if frame is not None:
                x, y = W - PREVIEW[0] - 10, H - PREVIEW[1] - 10
                s.blit(frame_to_surface(frame), (x, y))
                col = (0, 255, 0) if self.ctrl.gesture_active else (
                    (255, 255, 255) if self.ctrl.hand_visible else (255, 60, 60))
                pygame.draw.rect(s, col, (x - 2, y - 2, PREVIEW[0] + 4, PREVIEW[1] + 4), 3)
        pygame.display.flip()

    def run(self):
        while True:
            dt = min(self.clock.tick(60) / 1000.0, 1 / 30)
            for e in pygame.event.get():
                if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                    return
                if e.type == pygame.KEYDOWN and e.key in (pygame.K_SPACE, pygame.K_UP):
                    self.flap()
            if self.ctrl and self.ctrl.consume_flaps() > 0:
                self.flap()
            self.update(dt)
            self.draw()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--mode", choices=["pinch", "fist"], default="pinch")
    ap.add_argument("--no-camera", action="store_true")
    args = ap.parse_args()

    ctrl = None
    if not args.no_camera:
        from hand_controller import HandController
        ctrl = HandController(args.camera, args.mode).start()
    try:
        Game(ctrl).run()
    finally:
        if ctrl:
            ctrl.stop()
        pygame.quit()


if __name__ == "__main__":
    sys.exit(main())
