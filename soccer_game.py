"""
2-player / vs-bot soccer game in Pygame.
One-button control: each player rotates continuously, press key to dash.
Russian keyboard layout is handled via scancode → key mapping.
"""

import pygame
import math
import random
import sys
import json
import os

# ─── Constants ────────────────────────────────────────────────────────────────
W, H = 900, 900
FPS  = 60

# Field geometry (pixels)
FIELD_LEFT   = 80
FIELD_RIGHT  = 820
FIELD_TOP    = 60
FIELD_BOTTOM = 840
FIELD_W = FIELD_RIGHT - FIELD_LEFT
FIELD_H = FIELD_BOTTOM - FIELD_TOP

# Goal geometry  (centred on left/right walls)
GOAL_W    = 18   # depth into field
GOAL_H    = 140  # opening height
GOAL_Y    = (FIELD_TOP + FIELD_BOTTOM) // 2 - GOAL_H // 2
# Left goal  : x = FIELD_LEFT  →  FIELD_LEFT - GOAL_W  (outside field)
# Right goal : x = FIELD_RIGHT →  FIELD_RIGHT + GOAL_W

# Player
PLAYER_R    = 22
ROT_SPEED   = 2.5   # degrees per frame
DASH_FORCE  = 6.0
FRICTION    = 0.88

# Ball
BALL_R      = 13
BALL_FRIC   = 0.985

# Colours
C_GREEN_D  = (34,  139, 34)
C_GREEN_L  = (50,  205, 50)
C_WHITE    = (255, 255, 255)
C_BLACK    = (0,   0,   0)
C_RED      = (220, 50,  50)
C_BLUE     = (50,  100, 220)
C_YELLOW   = (255, 220, 0)
C_GRAY     = (180, 180, 180)
C_DARKGRAY = (80,  80,  80)
C_BG       = (20,  20,  40)
C_PANEL    = (30,  30,  60)
C_ACCENT   = (100, 200, 255)

# Scancode → latin key name (so Russian layout works)
SCANCODE_TO_KEY = {
    pygame.K_a: "a", pygame.K_b: "b", pygame.K_c: "c", pygame.K_d: "d",
    pygame.K_e: "e", pygame.K_f: "f", pygame.K_g: "g", pygame.K_h: "h",
    pygame.K_i: "i", pygame.K_j: "j", pygame.K_k: "k", pygame.K_l: "l",
    pygame.K_m: "m", pygame.K_n: "n", pygame.K_o: "o", pygame.K_p: "p",
    pygame.K_q: "q", pygame.K_r: "r", pygame.K_s: "s", pygame.K_t: "t",
    pygame.K_u: "u", pygame.K_v: "v", pygame.K_w: "w", pygame.K_x: "x",
    pygame.K_y: "y", pygame.K_z: "z",
    pygame.K_SPACE: "space", pygame.K_RETURN: "enter",
    pygame.K_UP: "up", pygame.K_DOWN: "down",
    pygame.K_LEFT: "left", pygame.K_RIGHT: "right",
    pygame.K_LSHIFT: "lshift", pygame.K_RSHIFT: "rshift",
    pygame.K_LCTRL: "lctrl",  pygame.K_RCTRL: "rctrl",
    pygame.K_TAB: "tab",
}
KEY_TO_SCANCODE = {v: k for k, v in SCANCODE_TO_KEY.items()}

DEFAULT_SETTINGS = {
    "p1_key": "lshift",
    "p2_key": "rshift",
    "volume": 0.5,
}

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")


# ─── Sound helpers ────────────────────────────────────────────────────────────

def make_beep(freq=440, duration_ms=80, volume=0.4, wave="sine"):
    """Generate a simple beep sound as a pygame Sound object."""
    sample_rate = 44100
    n = int(sample_rate * duration_ms / 1000)
    buf = bytearray(n * 2)
    for i in range(n):
        t = i / sample_rate
        if wave == "sine":
            v = math.sin(2 * math.pi * freq * t)
        elif wave == "square":
            v = 1.0 if math.sin(2 * math.pi * freq * t) >= 0 else -1.0
        else:
            v = math.sin(2 * math.pi * freq * t)
        # fade out
        env = 1.0 - i / n
        val = int(v * env * volume * 32767)
        val = max(-32768, min(32767, val))
        buf[i*2]   = val & 0xFF
        buf[i*2+1] = (val >> 8) & 0xFF
    return pygame.mixer.Sound(buffer=bytes(buf))


def build_sounds():
    sounds = {}
    try:
        sounds["kick"]   = make_beep(300, 60,  0.5, "square")
        sounds["goal"]   = make_beep(660, 400, 0.7, "sine")
        sounds["bounce"] = make_beep(200, 40,  0.3, "sine")
        sounds["whistle"]= make_beep(880, 200, 0.6, "sine")
    except Exception:
        pass
    return sounds


def make_music_track():
    """Build a tiny looping drum+bass music buffer."""
    sr = 44100
    beat = sr // 4        # 120 bpm quarter note
    pattern_len = beat * 8
    buf = bytearray(pattern_len * 2)

    def add_wave(buf, start, freq, dur, vol, wave="sine"):
        n = min(dur, len(buf)//2 - start)
        for i in range(n):
            t = i / sr
            if wave == "sine":
                v = math.sin(2*math.pi*freq*t)
            elif wave == "square":
                v = 1.0 if math.sin(2*math.pi*freq*t) >= 0 else -1.0
            else:
                v = math.sin(2*math.pi*freq*t)
            env = max(0.0, 1.0 - i/dur)
            val = int(v * env * vol * 32767)
            val = max(-32768, min(32767, val))
            idx = (start + i) * 2
            # mix
            existing = int.from_bytes(buf[idx:idx+2], 'little', signed=True)
            mixed = max(-32768, min(32767, existing + val))
            buf[idx]   = mixed & 0xFF
            buf[idx+1] = (mixed >> 8) & 0xFF

    # kick on beats 0, 2
    for b in [0, 2]:
        add_wave(buf, b*beat, 80,  int(sr*0.15), 0.5, "sine")
    # hi-hat every beat
    for b in range(8):
        add_wave(buf, b*beat + beat//2, 1200, int(sr*0.04), 0.15, "square")
    # bass line
    bass_notes = [110, 110, 147, 110, 110, 147, 110, 165]
    for b, f in enumerate(bass_notes):
        add_wave(buf, b*beat, f, int(sr*0.18), 0.35, "sine")

    return pygame.mixer.Sound(buffer=bytes(buf))


# ─── Utility ──────────────────────────────────────────────────────────────────

def norm_vec(angle_deg):
    r = math.radians(angle_deg)
    return math.cos(r), math.sin(r)


def circle_rect_collision(cx, cy, cr, rx, ry, rw, rh):
    """Returns True if circle overlaps rectangle."""
    nearest_x = max(rx, min(cx, rx + rw))
    nearest_y = max(ry, min(cy, ry + rh))
    dx = cx - nearest_x
    dy = cy - nearest_y
    return dx*dx + dy*dy < cr*cr


def resolve_circle_rect(cx, cy, cr, rx, ry, rw, rh):
    """Push circle out of rectangle. Returns (new_cx, new_cy, nx, ny)."""
    nearest_x = max(rx, min(cx, rx + rw))
    nearest_y = max(ry, min(cy, ry + rh))
    dx = cx - nearest_x
    dy = cy - nearest_y
    dist = math.hypot(dx, dy)
    if dist == 0:
        return cx, cy + cr, 0, 1
    nx, ny = dx/dist, dy/dist
    new_cx = nearest_x + nx * cr
    new_cy = nearest_y + ny * cr
    return new_cx, new_cy, nx, ny


def load_settings():
    try:
        with open(SETTINGS_FILE) as f:
            s = json.load(f)
        for k, v in DEFAULT_SETTINGS.items():
            if k not in s:
                s[k] = v
        return s
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(s):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(s, f, indent=2)
    except Exception:
        pass


# ─── Goal posts (rectangles that block movement) ──────────────────────────────

def get_goal_rects():
    """
    Returns list of pygame.Rect representing the physical post walls of both goals.
    Left goal opens to the LEFT (players can't enter from field side).
    Right goal opens to the RIGHT.
    Post thickness = 6px.
    """
    POST = 6
    rects = []
    # LEFT GOAL (opening faces left, mouth at x=FIELD_LEFT)
    # top post
    rects.append(pygame.Rect(FIELD_LEFT - GOAL_W, GOAL_Y - POST, GOAL_W + POST, POST))
    # bottom post
    rects.append(pygame.Rect(FIELD_LEFT - GOAL_W, GOAL_Y + GOAL_H, GOAL_W + POST, POST))
    # back wall
    rects.append(pygame.Rect(FIELD_LEFT - GOAL_W - POST, GOAL_Y - POST, POST, GOAL_H + POST*2))

    # RIGHT GOAL (opening faces right, mouth at x=FIELD_RIGHT)
    rects.append(pygame.Rect(FIELD_RIGHT - POST, GOAL_Y - POST, GOAL_W + POST, POST))
    rects.append(pygame.Rect(FIELD_RIGHT - POST, GOAL_Y + GOAL_H, GOAL_W + POST, POST))
    rects.append(pygame.Rect(FIELD_RIGHT + GOAL_W, GOAL_Y - POST, POST, GOAL_H + POST*2))

    return rects


# ─── Player ───────────────────────────────────────────────────────────────────

class Player:
    def __init__(self, x, y, color, rot_dir=1):
        self.x    = float(x)
        self.y    = float(y)
        self.vx   = 0.0
        self.vy   = 0.0
        self.angle = 0.0        # degrees; 0 = right
        self.rot_dir = rot_dir  # +1 or -1
        self.color = color
        self.r    = PLAYER_R
        self.rot_speed = ROT_SPEED

    def spawn(self, x, y):
        self.x, self.y = float(x), float(y)
        self.vx = self.vy = 0.0
        self.angle = 90.0 if self.color == C_RED else 270.0

    def update(self, key_pressed, goal_rects):
        # Rotate only when key is NOT held — while held, lock angle
        if not key_pressed:
            self.angle = (self.angle + self.rot_speed * self.rot_dir) % 360

        # dash on key press — use the frozen angle
        if key_pressed:
            dx, dy = norm_vec(self.angle)
            self.vx += dx * DASH_FORCE
            self.vy += dy * DASH_FORCE

        # friction
        self.vx *= FRICTION
        self.vy *= FRICTION

        # clamp speed
        spd = math.hypot(self.vx, self.vy)
        max_spd = DASH_FORCE * 2.5
        if spd > max_spd:
            self.vx = self.vx/spd * max_spd
            self.vy = self.vy/spd * max_spd

        self.x += self.vx
        self.y += self.vy

        # Field walls
        self.x = max(FIELD_LEFT + self.r, min(FIELD_RIGHT - self.r, self.x))
        self.y = max(FIELD_TOP  + self.r, min(FIELD_BOTTOM - self.r, self.y))

        # Goal post collisions
        for rect in goal_rects:
            if circle_rect_collision(self.x, self.y, self.r,
                                     rect.x, rect.y, rect.width, rect.height):
                self.x, self.y, nx, ny = resolve_circle_rect(
                    self.x, self.y, self.r,
                    rect.x, rect.y, rect.width, rect.height)
                dot = self.vx*nx + self.vy*ny
                self.vx -= 2*dot*nx
                self.vy -= 2*dot*ny
                self.vx *= 0.4
                self.vy *= 0.4

    def draw(self, surf):
        # Body shadow
        pygame.draw.circle(surf, (0,0,0,80), (int(self.x)+3, int(self.y)+4), self.r)
        # Body
        pygame.draw.circle(surf, self.color, (int(self.x), int(self.y)), self.r)
        # Highlight
        pygame.draw.circle(surf, C_WHITE, (int(self.x)-5, int(self.y)-5), 6)
        # Direction arrow
        dx, dy = norm_vec(self.angle)
        ax = self.x + dx * (self.r - 4)
        ay = self.y + dy * (self.r - 4)
        pygame.draw.circle(surf, C_WHITE, (int(ax), int(ay)), 5)
        pygame.draw.line(surf, C_BLACK, (int(self.x), int(self.y)), (int(ax), int(ay)), 2)
        # Outline
        pygame.draw.circle(surf, C_BLACK, (int(self.x), int(self.y)), self.r, 2)


# ─── Ball ─────────────────────────────────────────────────────────────────────

class Ball:
    def __init__(self):
        self.spawn()

    def spawn(self):
        cx = (FIELD_LEFT + FIELD_RIGHT) // 2
        cy = (FIELD_TOP  + FIELD_BOTTOM) // 2
        self.x = float(cx)
        self.y = float(cy)
        angle = random.uniform(0, 360)
        spd = random.uniform(1.5, 3.0)
        dx, dy = norm_vec(angle)
        self.vx = dx * spd
        self.vy = dy * spd
        self.r  = BALL_R
        self.spin = 0.0

    def update(self, goal_rects, sounds, vol):
        self.vx *= BALL_FRIC
        self.vy *= BALL_FRIC
        self.x += self.vx
        self.y += self.vy
        self.spin += math.hypot(self.vx, self.vy) * 2

        bounced = False
        # Field walls — but let ball pass through goal openings
        # Top / bottom walls
        if self.y - self.r < FIELD_TOP:
            self.y = FIELD_TOP + self.r
            self.vy = abs(self.vy)
            bounced = True
        if self.y + self.r > FIELD_BOTTOM:
            self.y = FIELD_BOTTOM - self.r
            self.vy = -abs(self.vy)
            bounced = True

        # Left wall — but not in goal opening
        if self.x - self.r < FIELD_LEFT:
            in_goal = GOAL_Y - 2 < self.y < GOAL_Y + GOAL_H + 2
            if not in_goal:
                self.x = FIELD_LEFT + self.r
                self.vx = abs(self.vx)
                bounced = True

        # Right wall — but not in goal opening
        if self.x + self.r > FIELD_RIGHT:
            in_goal = GOAL_Y - 2 < self.y < GOAL_Y + GOAL_H + 2
            if not in_goal:
                self.x = FIELD_RIGHT - self.r
                self.vx = -abs(self.vx)
                bounced = True

        if bounced and sounds:
            s = sounds.get("bounce")
            if s:
                s.set_volume(vol * 0.4)
                s.play()

        # Goal post rects
        for rect in goal_rects:
            if circle_rect_collision(self.x, self.y, self.r,
                                     rect.x, rect.y, rect.width, rect.height):
                self.x, self.y, nx, ny = resolve_circle_rect(
                    self.x, self.y, self.r,
                    rect.x, rect.y, rect.width, rect.height)
                dot = self.vx*nx + self.vy*ny
                self.vx -= 2*dot*nx * 0.7
                self.vy -= 2*dot*ny * 0.7

    def check_goal(self):
        """Returns 'left' if left goal scored (blue scores), 'right' if right scored (red), None otherwise."""
        # Ball centre crosses left goal line and is within goal height
        if (self.x < FIELD_LEFT and
                GOAL_Y + self.r < self.y < GOAL_Y + GOAL_H - self.r):
            return "left"   # blue scored
        # Ball centre crosses right goal line and is within goal height
        if (self.x > FIELD_RIGHT and
                GOAL_Y + self.r < self.y < GOAL_Y + GOAL_H - self.r):
            return "right"  # red scored
        return None

    def kick(self, player, sounds, vol):
        dx = self.x - player.x
        dy = self.y - player.y
        dist = math.hypot(dx, dy)
        if dist < player.r + self.r + 4:
            if dist < 1:
                dx, dy, dist = 1, 0, 1
            nx, ny = dx/dist, dy/dist
            spd = math.hypot(player.vx, player.vy)
            impulse = max(4.0, spd * 1.4 + 2.5)
            self.vx = nx * impulse + player.vx * 0.3
            self.vy = ny * impulse + player.vy * 0.3
            # separate
            overlap = player.r + self.r - dist + 1
            self.x += nx * overlap
            self.y += ny * overlap
            if sounds:
                s = sounds.get("kick")
                if s:
                    s.set_volume(vol)
                    s.play()
            return True
        return False

    def draw(self, surf):
        angle_r = math.radians(self.spin)
        bx, by = int(self.x), int(self.y)
        pygame.draw.circle(surf, (0,0,0,80), (bx+3, by+4), self.r)
        pygame.draw.circle(surf, C_WHITE, (bx, by), self.r)
        # Pentagons pattern (simplified lines)
        for i in range(6):
            a = angle_r + i * math.pi / 3
            x1 = bx + int(math.cos(a) * self.r * 0.55)
            y1 = by + int(math.sin(a) * self.r * 0.55)
            x2 = bx + int(math.cos(a + math.pi/3) * self.r * 0.55)
            y2 = by + int(math.sin(a + math.pi/3) * self.r * 0.55)
            pygame.draw.line(surf, C_BLACK, (x1,y1), (x2,y2), 2)
        pygame.draw.circle(surf, C_BLACK, (bx, by), self.r, 2)


# ─── Field drawing ────────────────────────────────────────────────────────────

def draw_field(surf):
    # Striped green background
    surf.fill(C_GREEN_D)
    stripe_w = FIELD_W // 10
    for i in range(10):
        if i % 2 == 0:
            x = FIELD_LEFT + i * stripe_w
            pygame.draw.rect(surf, C_GREEN_L, (x, FIELD_TOP, stripe_w, FIELD_H))

    # Outer boundary
    pygame.draw.rect(surf, C_WHITE, (FIELD_LEFT, FIELD_TOP, FIELD_W, FIELD_H), 3)

    # Centre line
    pygame.draw.line(surf, C_WHITE,
                     ((FIELD_LEFT+FIELD_RIGHT)//2, FIELD_TOP),
                     ((FIELD_LEFT+FIELD_RIGHT)//2, FIELD_BOTTOM), 2)

    # Centre circle
    cx = (FIELD_LEFT+FIELD_RIGHT)//2
    cy = (FIELD_TOP+FIELD_BOTTOM)//2
    pygame.draw.circle(surf, C_WHITE, (cx, cy), 70, 2)
    pygame.draw.circle(surf, C_WHITE, (cx, cy), 4)

    # Penalty areas (left & right)
    pa_w, pa_h = 110, 250
    pa_top = cy - pa_h//2
    pygame.draw.rect(surf, C_WHITE, (FIELD_LEFT, pa_top, pa_w, pa_h), 2)
    pygame.draw.rect(surf, C_WHITE, (FIELD_RIGHT - pa_w, pa_top, pa_w, pa_h), 2)

    # Small boxes
    sb_w, sb_h = 50, 130
    sb_top = cy - sb_h//2
    pygame.draw.rect(surf, C_WHITE, (FIELD_LEFT, sb_top, sb_w, sb_h), 2)
    pygame.draw.rect(surf, C_WHITE, (FIELD_RIGHT - sb_w, sb_top, sb_w, sb_h), 2)

    # Corner arcs
    corner_r = 18
    corners = [(FIELD_LEFT, FIELD_TOP, 0, 90),
               (FIELD_RIGHT, FIELD_TOP, 90, 180),
               (FIELD_RIGHT, FIELD_BOTTOM, 180, 270),
               (FIELD_LEFT, FIELD_BOTTOM, 270, 360)]
    for cx2, cy2, a1, a2 in corners:
        rect = pygame.Rect(cx2-corner_r, cy2-corner_r, corner_r*2, corner_r*2)
        pygame.draw.arc(surf, C_WHITE, rect, math.radians(a1), math.radians(a2), 2)

    # Goals
    _draw_goals(surf)


def _draw_goals(surf):
    POST = 6
    # Left goal (red's goal — blue attacks here)
    gx = FIELD_LEFT - GOAL_W
    gy = GOAL_Y
    # Net background
    pygame.draw.rect(surf, (200, 50, 50, 120), (gx, gy, GOAL_W, GOAL_H))
    # Net lines
    for i in range(0, GOAL_H, 15):
        pygame.draw.line(surf, (180,80,80), (gx, gy+i), (FIELD_LEFT, gy+i), 1)
    for i in range(0, GOAL_W, 15):
        pygame.draw.line(surf, (180,80,80), (gx+i, gy), (gx+i, gy+GOAL_H), 1)
    # Posts
    pygame.draw.rect(surf, C_WHITE, (gx, gy-POST, GOAL_W+POST, POST))           # top
    pygame.draw.rect(surf, C_WHITE, (gx, gy+GOAL_H, GOAL_W+POST, POST))         # bottom
    pygame.draw.rect(surf, C_WHITE, (gx-POST, gy-POST, POST, GOAL_H+POST*2))    # back

    # Right goal (blue's goal — red attacks here)
    gx2 = FIELD_RIGHT
    pygame.draw.rect(surf, (50, 50, 200, 120), (gx2, gy, GOAL_W, GOAL_H))
    for i in range(0, GOAL_H, 15):
        pygame.draw.line(surf, (80,80,180), (gx2, gy+i), (gx2+GOAL_W, gy+i), 1)
    for i in range(0, GOAL_W, 15):
        pygame.draw.line(surf, (80,80,180), (gx2+i, gy), (gx2+i, gy+GOAL_H), 1)
    pygame.draw.rect(surf, C_WHITE, (FIELD_RIGHT-POST, gy-POST, GOAL_W+POST, POST))
    pygame.draw.rect(surf, (255,255,255), (FIELD_RIGHT-POST, gy+GOAL_H, GOAL_W+POST, POST))
    pygame.draw.rect(surf, C_WHITE, (gx2+GOAL_W, gy-POST, POST, GOAL_H+POST*2))


# ─── HUD ──────────────────────────────────────────────────────────────────────

def draw_hud(surf, font, score_red, score_blue):
    # Top bar
    pygame.draw.rect(surf, C_BG, (0, 0, W, FIELD_TOP))
    # Scores
    red_txt  = font.render(str(score_red),  True, C_RED)
    blue_txt = font.render(str(score_blue), True, C_BLUE)
    dash_txt = font.render("-", True, C_WHITE)
    cx = W // 2
    surf.blit(dash_txt,  dash_txt.get_rect(center=(cx, FIELD_TOP//2)))
    surf.blit(red_txt,   red_txt.get_rect(midright=(cx - 25, FIELD_TOP//2)))
    surf.blit(blue_txt,  blue_txt.get_rect(midleft=(cx + 25,  FIELD_TOP//2)))


# ─── Goal animation ───────────────────────────────────────────────────────────

class GoalAnim:
    def __init__(self, scorer):
        self.scorer = scorer   # "red" or "blue"
        self.timer  = FPS * 2  # 2 seconds

    def update(self):
        self.timer -= 1
        return self.timer > 0

    def draw(self, surf, font_big, font_small, score_red, score_blue):
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        alpha = min(200, int(200 * self.timer / (FPS * 2)) + 40)
        overlay.fill((0, 0, 0, alpha))
        surf.blit(overlay, (0,0))

        col = C_RED if self.scorer == "red" else C_BLUE
        goal_txt = font_big.render("ГОЛ!", True, col)
        surf.blit(goal_txt, goal_txt.get_rect(center=(W//2, H//2 - 60)))

        score_str = f"{score_red}  :  {score_blue}"
        sc_txt = font_big.render(score_str, True, C_WHITE)
        surf.blit(sc_txt, sc_txt.get_rect(center=(W//2, H//2 + 10)))

        hint = font_small.render("Подготовьтесь...", True, C_GRAY)
        surf.blit(hint, hint.get_rect(center=(W//2, H//2 + 70)))


# ─── Win screen ───────────────────────────────────────────────────────────────

WIN_SCORE = 3   # first to this many goals wins

def screen_winner(surf, fonts, winner, score_red, score_blue, field_surf):
    """
    Displays the winner screen. Returns 'menu' or 'quit'.
    winner: 'red' | 'blue'
    """
    font_big   = fonts["big"]
    font_small = fonts["small"]
    font_btn   = fonts["btn"]

    btn_menu  = pygame.Rect(W//2 - 170, H//2 + 110, 150, 50)
    btn_again = pygame.Rect(W//2 + 20,  H//2 + 110, 150, 50)

    col    = C_RED  if winner == "red"  else C_BLUE
    name   = "КРАСНЫЙ" if winner == "red" else "СИНИЙ"
    star   = "⭐"

    clock  = pygame.time.Clock()
    t      = 0
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if btn_menu.collidepoint(event.pos):
                    return "menu"
                if btn_again.collidepoint(event.pos):
                    return "again"
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return "menu"

        surf.blit(field_surf, (0, 0))
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        surf.blit(overlay, (0, 0))

        # Pulsating winner text
        pulse = 1.0 + 0.05 * math.sin(t * 0.12)
        base_size = 72
        try:
            f_pulse = pygame.font.SysFont("dejavusans", int(base_size * pulse))
        except Exception:
            f_pulse = font_big

        win_txt = f_pulse.render(f"{star} ПОБЕДИТЕЛЬ {star}", True, C_YELLOW)
        surf.blit(win_txt, win_txt.get_rect(center=(W//2, H//2 - 110)))

        name_txt = font_big.render(name, True, col)
        surf.blit(name_txt, name_txt.get_rect(center=(W//2, H//2 - 30)))

        score_txt = font_big.render(f"{score_red}  :  {score_blue}", True, C_WHITE)
        surf.blit(score_txt, score_txt.get_rect(center=(W//2, H//2 + 55)))

        draw_button(surf, font_btn, "← Меню",      btn_menu,  hover=mouse_in(btn_menu))
        draw_button(surf, font_btn, "Ещё раз →",   btn_again, hover=mouse_in(btn_again))

        pygame.display.flip()
        clock.tick(FPS)
        t += 1


# ─── Bot AI ───────────────────────────────────────────────────────────────────

class Bot:
    def __init__(self, player, difficulty):
        self.player = player
        self.difficulty = difficulty  # "easy","medium","hard"
        self._react_timer = 0
        self._stuck_timer = 0
        self._last_x = None
        self._last_y = None

    def update(self, ball):
        p  = self.player
        bx, by = ball.x, ball.y

        if self.difficulty == "easy":
            if self._react_timer > 0:
                self._react_timer -= 1
                return False
            self._react_timer = random.randint(20, 40)
            threshold = 90
            noise = random.gauss(0, 35)
            shoot_threshold = 70
        elif self.difficulty == "medium":
            threshold = 60
            noise = random.gauss(0, 14)
            shoot_threshold = 50
        else:  # hard
            threshold = 40
            noise = random.gauss(0, 5)
            shoot_threshold = 35

        # ── Stuck / corner detection ──────────────────────────────────────────
        if self._last_x is not None:
            moved = math.hypot(p.x - self._last_x, p.y - self._last_y)
            if moved < 0.5:
                self._stuck_timer += 1
            else:
                self._stuck_timer = max(0, self._stuck_timer - 2)
        self._last_x, self._last_y = p.x, p.y

        # If stuck for too long, just dash to break free (rotate will do the rest)
        if self._stuck_timer > 30:
            self._stuck_timer = 0
            return True   # dash in whatever direction we're facing — breaks corner lock

        # ── Near a wall/corner: try to move away first ───────────────────────
        margin = PLAYER_R + 10
        near_wall = (p.x < FIELD_LEFT + margin or p.x > FIELD_RIGHT - margin or
                     p.y < FIELD_TOP  + margin or p.y > FIELD_BOTTOM - margin)
        if near_wall:
            # Desired direction: toward field centre
            cx = (FIELD_LEFT + FIELD_RIGHT) / 2
            cy = (FIELD_TOP  + FIELD_BOTTOM) / 2
            dx = cx - p.x
            dy = cy - p.y
            desired_angle = math.degrees(math.atan2(dy, dx)) % 360
            diff = (desired_angle - p.angle) % 360
            if diff > 180:
                diff -= 360
            if abs(diff) < threshold:
                return True
            return False

        # ── Main AI: approach ball then aim at goal ───────────────────────────
        dist_to_ball = math.hypot(bx - p.x, by - p.y)

        # Bot (blue, p2) attacks LEFT goal (x = FIELD_LEFT)
        goal_x = float(FIELD_LEFT)
        goal_y = float(GOAL_Y + GOAL_H / 2)

        if dist_to_ball > 80:
            # Phase 1: approach ball (with noise)
            target_x = bx + noise
            target_y = by + noise
        else:
            # Phase 2: position behind ball to shoot toward left goal
            # Ideal approach: stand on the far side of the ball from the goal
            # so dashing pushes ball toward goal
            to_goal_x = goal_x - bx
            to_goal_y = goal_y - by
            dg = math.hypot(to_goal_x, to_goal_y)
            if dg > 0:
                to_goal_x /= dg
                to_goal_y /= dg
            # Stand behind the ball (opposite to goal direction)
            offset = PLAYER_R + BALL_R + 12
            target_x = bx - to_goal_x * offset + noise * 0.3
            target_y = by - to_goal_y * offset + noise * 0.3

        dx = target_x - p.x
        dy = target_y - p.y
        desired_angle = math.degrees(math.atan2(dy, dx)) % 360

        diff = (desired_angle - p.angle) % 360
        if diff > 180:
            diff -= 360

        dist = math.hypot(dx, dy)

        # Shoot: if close to ball AND facing goal direction
        if dist_to_ball < PLAYER_R + BALL_R + 20:
            goal_dx = goal_x - p.x
            goal_dy = goal_y - p.y
            goal_angle = math.degrees(math.atan2(goal_dy, goal_dx)) % 360
            goal_diff = (goal_angle - p.angle) % 360
            if goal_diff > 180:
                goal_diff -= 360
            # Also check we're not accidentally aimed at our own (right) goal
            own_goal_x = float(FIELD_RIGHT)
            own_goal_y = float(GOAL_Y + GOAL_H / 2)
            own_dx = own_goal_x - p.x
            own_dy = own_goal_y - p.y
            own_angle = math.degrees(math.atan2(own_dy, own_dx)) % 360
            own_diff = (own_angle - p.angle) % 360
            if own_diff > 180:
                own_diff -= 360
            # Only shoot if aimed at enemy goal and NOT aimed at own goal
            if abs(goal_diff) < shoot_threshold and abs(own_diff) > 60:
                return True

        # Normal move toward target — no distance cap so bot always chases
        if abs(diff) < threshold:
            return True
        return False


# ─── Menu / UI helpers ────────────────────────────────────────────────────────

def draw_panel(surf, rect, radius=12):
    pygame.draw.rect(surf, C_PANEL, rect, border_radius=radius)
    pygame.draw.rect(surf, C_ACCENT, rect, 2, border_radius=radius)


def draw_button(surf, font, text, rect, hover=False):
    col = (60, 60, 100) if not hover else (80, 80, 140)
    pygame.draw.rect(surf, col, rect, border_radius=8)
    pygame.draw.rect(surf, C_ACCENT, rect, 2, border_radius=8)
    txt = font.render(text, True, C_WHITE)
    surf.blit(txt, txt.get_rect(center=rect.center))


def mouse_in(rect):
    return rect.collidepoint(pygame.mouse.get_pos())


# ─── Screens ──────────────────────────────────────────────────────────────────

def screen_main_menu(surf, font_title, font_btn, field_surf):
    """Returns: 'two_player', 'vs_bot', 'settings', 'quit'"""
    buttons = {
        "two_player": pygame.Rect(W//2 - 160, 350, 320, 55),
        "vs_bot":     pygame.Rect(W//2 - 160, 430, 320, 55),
        "settings":   pygame.Rect(W//2 - 160, 510, 320, 55),
        "quit":       pygame.Rect(W//2 - 160, 590, 320, 55),
    }
    labels = {
        "two_player": "Игра вдвоём",
        "vs_bot":     "Против бота",
        "settings":   "Настройки",
        "quit":       "Выход",
    }

    clock = pygame.time.Clock()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for k, r in buttons.items():
                    if r.collidepoint(event.pos):
                        return k

        # draw
        surf.blit(field_surf, (0, 0))
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surf.blit(overlay, (0,0))

        title = font_title.render("⚽  МИНИ-ФУТБОЛ  ⚽", True, C_WHITE)
        surf.blit(title, title.get_rect(center=(W//2, 220)))

        for k, r in buttons.items():
            draw_button(surf, font_btn, labels[k], r, hover=mouse_in(r))

        pygame.display.flip()
        clock.tick(FPS)


def screen_bot_difficulty(surf, font_title, font_btn, field_surf):
    """Returns: 'easy','medium','hard','back'"""
    buttons = {
        "easy":   pygame.Rect(W//2 - 160, 350, 320, 55),
        "medium": pygame.Rect(W//2 - 160, 430, 320, 55),
        "hard":   pygame.Rect(W//2 - 160, 510, 320, 55),
        "back":   pygame.Rect(W//2 - 160, 610, 320, 45),
    }
    labels = {
        "easy":   "Лёгкий",
        "medium": "Средний",
        "hard":   "Сложный",
        "back":   "← Назад",
    }
    clock = pygame.time.Clock()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "back"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for k, r in buttons.items():
                    if r.collidepoint(event.pos):
                        return k

        surf.blit(field_surf, (0,0))
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0,0,0,160))
        surf.blit(overlay, (0,0))
        title = font_title.render("Сложность бота", True, C_WHITE)
        surf.blit(title, title.get_rect(center=(W//2, 240)))
        for k, r in buttons.items():
            draw_button(surf, font_btn, labels[k], r, hover=mouse_in(r))
        pygame.display.flip()
        clock.tick(FPS)


def screen_settings(surf, font_title, font_btn, font_sm, settings, field_surf):
    clock = pygame.time.Clock()
    waiting_for = None   # None | 'p1' | 'p2'

    vol_rect  = pygame.Rect(W//2 - 160, 280, 320, 30)
    p1_rect   = pygame.Rect(W//2 - 160, 380, 320, 50)
    p2_rect   = pygame.Rect(W//2 - 160, 460, 320, 50)
    back_rect = pygame.Rect(W//2 - 160, 580, 320, 45)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                save_settings(settings)
                return

            if waiting_for:
                if event.type == pygame.KEYDOWN:
                    sc = event.scancode
                    # map scancode to our latin key name
                    key_name = SCANCODE_TO_KEY.get(event.key)
                    if key_name is None:
                        # try by scancode approach (map scancode to pygame key const)
                        # just use event.key as fallback
                        key_name = pygame.key.name(event.key)
                    if waiting_for == "p1":
                        settings["p1_key"] = key_name
                    else:
                        settings["p2_key"] = key_name
                    waiting_for = None
                continue

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if back_rect.collidepoint(event.pos):
                    save_settings(settings)
                    return
                if p1_rect.collidepoint(event.pos):
                    waiting_for = "p1"
                if p2_rect.collidepoint(event.pos):
                    waiting_for = "p2"
                # volume slider
                if vol_rect.collidepoint(event.pos):
                    rel = (event.pos[0] - vol_rect.x) / vol_rect.width
                    settings["volume"] = max(0.0, min(1.0, rel))

            if event.type == pygame.MOUSEMOTION and event.buttons[0]:
                if vol_rect.collidepoint(event.pos):
                    rel = (event.pos[0] - vol_rect.x) / vol_rect.width
                    settings["volume"] = max(0.0, min(1.0, rel))

        surf.blit(field_surf, (0,0))
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0,0,0,160))
        surf.blit(overlay, (0,0))

        title = font_title.render("Настройки", True, C_WHITE)
        surf.blit(title, title.get_rect(center=(W//2, 190)))

        # Volume
        vol_lbl = font_btn.render(f"Громкость: {int(settings['volume']*100)}%", True, C_WHITE)
        surf.blit(vol_lbl, vol_lbl.get_rect(midleft=(W//2 - 160, 255)))
        pygame.draw.rect(surf, C_DARKGRAY, vol_rect, border_radius=6)
        fill_w = int(settings["volume"] * vol_rect.width)
        pygame.draw.rect(surf, C_ACCENT,
                         pygame.Rect(vol_rect.x, vol_rect.y, fill_w, vol_rect.height),
                         border_radius=6)
        pygame.draw.rect(surf, C_WHITE, vol_rect, 2, border_radius=6)

        # P1 key
        p1_lbl = f"🔴 Красный: [{settings['p1_key']}]"
        if waiting_for == "p1":
            p1_lbl = "🔴 Красный: [нажмите клавишу...]"
        draw_button(surf, font_btn, p1_lbl, p1_rect, hover=(mouse_in(p1_rect) or waiting_for=="p1"))

        # P2 key
        p2_lbl = f"🔵 Синий: [{settings['p2_key']}]"
        if waiting_for == "p2":
            p2_lbl = "🔵 Синий: [нажмите клавишу...]"
        draw_button(surf, font_btn, p2_lbl, p2_rect, hover=(mouse_in(p2_rect) or waiting_for=="p2"))

        hint = font_sm.render("Работает с любой раскладкой (рус/eng)", True, C_GRAY)
        surf.blit(hint, hint.get_rect(center=(W//2, 525)))

        draw_button(surf, font_btn, "← Назад", back_rect, hover=mouse_in(back_rect))

        pygame.display.flip()
        clock.tick(FPS)


# ─── Key detection (layout-agnostic) ──────────────────────────────────────────

def key_is_pressed(pressed_keys, key_name):
    """
    Returns True if the physical key corresponding to key_name is pressed.
    Uses scancode mapping so Russian layout still works.
    """
    sc = KEY_TO_SCANCODE.get(key_name)
    if sc is not None:
        return pressed_keys[sc]
    # fallback: try pygame.key.name lookup
    for i, v in enumerate(pressed_keys):
        if v and pygame.key.name(i) == key_name:
            return True
    return False


# ─── Main game loop ───────────────────────────────────────────────────────────

def run_game(surf, fonts, settings, mode, bot_difficulty, sounds, music, field_surf):
    font_hud   = fonts["hud"]
    font_big   = fonts["big"]
    font_small = fonts["small"]

    goal_rects = get_goal_rects()

    # Spawn positions
    cx = (FIELD_LEFT + FIELD_RIGHT) // 2
    cy = (FIELD_TOP  + FIELD_BOTTOM) // 2
    p1_spawn = (cx - 100, cy)
    p2_spawn = (cx + 100, cy)

    p1 = Player(*p1_spawn, C_RED,  rot_dir=1)
    p2 = Player(*p2_spawn, C_BLUE, rot_dir=-1)
    p1.angle = 90.0
    p2.angle = 270.0

    ball = Ball()
    ball.vx = ball.vy = 0  # start still

    score = {"red": 0, "blue": 0}
    bot = Bot(p2, bot_difficulty) if mode == "vs_bot" else None

    goal_anim  = None
    pause_timer = 0

    clock = pygame.time.Clock()

    if music:
        music.set_volume(settings["volume"] * 0.3)
        music.play(-1)

    # Countdown before start
    for i in range(3, 0, -1):
        surf.blit(field_surf, (0,0))
        draw_hud(surf, font_hud, score["red"], score["blue"])
        p1.draw(surf)
        p2.draw(surf)
        ball.draw(surf)
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0,0,0,100))
        surf.blit(overlay, (0,0))
        cnt = font_big.render(str(i), True, C_WHITE)
        surf.blit(cnt, cnt.get_rect(center=(W//2, H//2)))
        pygame.display.flip()
        pygame.time.wait(900)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"

    running = True
    paused  = False

    while running:
        dt = clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if music: music.stop()
                return "quit"
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if music: music.stop()
                    return "menu"

        pressed = pygame.key.get_pressed()

        if not paused:
            p1_key = key_is_pressed(pressed, settings["p1_key"])
            p2_key = (key_is_pressed(pressed, settings["p2_key"])
                      if mode == "two_player"
                      else bot.update(ball))

            p1.update(p1_key, goal_rects)
            p2.update(p2_key, goal_rects)

            ball.update(goal_rects, sounds, settings["volume"])

            # Kick
            ball.kick(p1, sounds, settings["volume"])
            ball.kick(p2, sounds, settings["volume"])

            # Player-player collision
            dx = p2.x - p1.x
            dy = p2.y - p1.y
            dist = math.hypot(dx, dy)
            if dist < p1.r + p2.r and dist > 0:
                nx, ny = dx/dist, dy/dist
                overlap = p1.r + p2.r - dist
                p1.x -= nx * overlap/2
                p1.y -= ny * overlap/2
                p2.x += nx * overlap/2
                p2.y += ny * overlap/2
                # exchange velocities (simplified)
                p1.vx, p2.vx = p2.vx*0.6, p1.vx*0.6
                p1.vy, p2.vy = p2.vy*0.6, p1.vy*0.6

            # Goal check
            goal = ball.check_goal()
            if goal:
                if goal == "left":
                    score["blue"] += 1
                    scorer = "blue"
                else:
                    score["red"] += 1
                    scorer = "red"
                if sounds:
                    s = sounds.get("goal")
                    if s:
                        s.set_volume(settings["volume"])
                        s.play()
                # Check for winner
                if score["red"] >= WIN_SCORE or score["blue"] >= WIN_SCORE:
                    running = False
                    winner = "red" if score["red"] >= WIN_SCORE else "blue"
                else:
                    goal_anim = GoalAnim(scorer)
                    paused = True

        # ── Draw ──
        surf.blit(field_surf, (0, 0))
        draw_hud(surf, font_hud, score["red"], score["blue"])
        p1.draw(surf)
        p2.draw(surf)
        ball.draw(surf)

        if paused and goal_anim:
            still_going = goal_anim.update()
            goal_anim.draw(surf, font_big, font_small, score["red"], score["blue"])
            if not still_going:
                # Reset
                p1.spawn(*p1_spawn)
                p2.spawn(*p2_spawn)
                ball.spawn()
                ball.vx = ball.vy = 0
                goal_anim = None
                paused = False

        # ESC hint
        esc_txt = font_small.render("ESC — меню", True, C_GRAY)
        surf.blit(esc_txt, (FIELD_RIGHT - 110, FIELD_BOTTOM + 8))

        pygame.display.flip()

    if music: music.stop()

    # Show winner screen if game ended by score
    if score["red"] >= WIN_SCORE or score["blue"] >= WIN_SCORE:
        winner = "red" if score["red"] >= WIN_SCORE else "blue"
        result = screen_winner(surf, fonts, winner, score["red"], score["blue"], field_surf)
        if result == "again":
            return run_game(surf, fonts, settings, mode, bot_difficulty, sounds, music, field_surf)
        return result

    return "menu"


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    pygame.mixer.pre_init(44100, -16, 1, 512)
    pygame.init()
    pygame.mixer.init(44100, -16, 1, 512)

    surf = pygame.display.set_mode((W, H))
    pygame.display.set_caption("⚽ Мини-Футбол")

    # Fonts — try system fonts with Cyrillic support
    def get_font(size):
        for name in ["dejavusans", "freesans", "liberationsans", "arial", "segoeui", ""]:
            f = pygame.font.SysFont(name, size)
            if f:
                return f
        return pygame.font.Font(None, size)

    fonts = {
        "hud":   get_font(46),
        "big":   get_font(72),
        "small": get_font(26),
        "btn":   get_font(30),
        "title": get_font(54),
    }

    sounds = build_sounds()
    try:
        music = make_music_track()
    except Exception:
        music = None

    settings = load_settings()

    # Pre-render field surface
    field_surf = pygame.Surface((W, H))
    field_surf.fill(C_BG)
    draw_field(field_surf)

    state = "menu"
    bot_diff = "medium"

    while state != "quit":
        if state == "menu":
            state = screen_main_menu(surf, fonts["title"], fonts["btn"], field_surf)

        elif state == "settings":
            screen_settings(surf, fonts["title"], fonts["btn"], fonts["small"], settings, field_surf)
            state = "menu"

        elif state == "two_player":
            state = run_game(surf, fonts, settings, "two_player", None, sounds, music, field_surf)
            if state not in ("menu", "quit"):
                state = "menu"

        elif state == "vs_bot":
            diff = screen_bot_difficulty(surf, fonts["title"], fonts["btn"], field_surf)
            if diff == "back":
                state = "menu"
            else:
                bot_diff = diff
                state = run_game(surf, fonts, settings, "vs_bot", bot_diff, sounds, music, field_surf)
                if state not in ("menu", "quit"):
                    state = "menu"

        elif state == "quit":
            break
        else:
            state = "menu"

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
