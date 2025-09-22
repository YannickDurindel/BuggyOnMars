#!/usr/bin/env python3
# moon_buggy_like.py — runner with wide spacing, pits, cones, big flies, and multi-level STEPS.
# Controls: ↑ jump, Space shoot, → turbo, P pause, Q quit.

import curses, time, random
from collections import deque

# ---------------- Tunables ---------------------------------------------------
FPS                = 30
GRAVITY            = 22.0
JUMP_VEL           = 10.0
GROUND_PAD         = 2
START_SPEED        = 1.0
SPEED_UP_EVERY     = 14
SPEED_STEP         = 0.05

# Hazards (all obey spacing)
PIT_RATE           = 0.010
CONE_RATE          = 0.014
ENEMY_RATE         = 0.010
STEP_RATE          = 0.012       # chance to attempt a step event
STEP_UP_BIAS       = 0.55        # >0.5 tends to climb; <0.5 tends to descend
MAX_ELEV           = 10          # maximum steps above base

PIT_MIN, PIT_MAX   = 3, 9
SAFE_START_SEC     = 2.0
CAR_X_FRACTION     = 0.14
EDGE_BUFFER        = 4
SPACING_FACTOR     = 1.2         # distance between hazards (in jump lengths)
BOOST_MULTIPLIER   = 2.0

# Shooting and enemies
BULLET_SPEED_COLS  = 3.0
BULLET_COOLDOWN    = 0.10
ENEMY_SCORE        = 25
ENEMY_SHIM_PER_FRAME = 0.35

# Glyphs
ROAD_CH   = "█"
CONE_CH   = "▲"
BULLET_CH = "•"   # use "-" if needed

# Big fly ASCII
ENEMY_ART = [
    r" //^\ \ ",
    r"<(o o o)>",
    r"  \_-_/ "
]
ENEMY_HEIGHT = len(ENEMY_ART)
ENEMY_WIDTH  = max(len(s) for s in ENEMY_ART)

CAR_ART = [
    r"  __",
    r"_/__\_",
    r"o    o"
]
CAR_H = len(CAR_ART)
CAR_W = max(len(s) for s in CAR_ART)

def clamp(v, lo, hi): return lo if v < lo else hi if v > hi else v

def max_jump_columns(speed_cols_per_frame: float) -> int:
    vx = speed_cols_per_frame * FPS
    t_air = 2.0 * (JUMP_VEL / GRAVITY)
    return max(3, int(vx * t_air * 0.9))

def min_spacing(speed_cols_per_frame: float) -> int:
    return int(max_jump_columns(speed_cols_per_frame) * SPACING_FACTOR)

# Each column = (cell, elev)
#   cell: 'G' ground, 'C' cone-on-surface, ' ' pit-at-surface
#   elev: integer 0..N (surface row = base_row - elev)
class TrackGen:
    def __init__(self, width, warmup_cols, max_elev):
        self.warmup_cols = warmup_cols
        self.cooldown = 0
        self.pit_left = 0
        self.edge_protect = 0
        self.elev = 0
        self.max_elev = max_elev
        self.rng = random.Random(); self.rng.seed()

    def _step_event(self):
        # choose up or down within bounds
        if self.elev == 0:
            up = True
        elif self.elev >= self.max_elev:
            up = False
        else:
            up = (self.rng.random() < STEP_UP_BIAS)
        self.elev += 1 if up else -1

    def next_cell(self, speed_cols_per_frame: float):
        if self.warmup_cols > 0:
            self.warmup_cols -= 1
            return ('G', self.elev), None

        if self.pit_left > 0:
            self.pit_left -= 1
            if self.pit_left == 0:
                self.cooldown = min_spacing(speed_cols_per_frame)
                self.edge_protect = EDGE_BUFFER
            return (' ', self.elev), None

        if self.cooldown > 0:
            self.cooldown -= 1
            if self.edge_protect > 0: self.edge_protect -= 1
            return ('G', self.elev), None

        # physics limits
        J = max_jump_columns(speed_cols_per_frame)
        pit_cap = max(PIT_MIN, min(PIT_MAX, J - 2))
        can_pit = (pit_cap >= PIT_MIN)
        can_cone = (self.edge_protect == 0)

        r = self.rng.random()
        # Steps
        if r < STEP_RATE:
            self._step_event()
            self.cooldown = min_spacing(speed_cols_per_frame)
            self.edge_protect = EDGE_BUFFER   # keep edges clean
            return ('G', self.elev), None

        r = self.rng.random()
        if can_pit and r < PIT_RATE:
            w = self.rng.randint(PIT_MIN, pit_cap)
            self.pit_left = w - 1
            return (' ', self.elev), None

        r = self.rng.random()
        if can_cone and r < CONE_RATE:
            self.cooldown = min_spacing(speed_cols_per_frame)
            return ('C', self.elev), None

        r = self.rng.random()
        if r < ENEMY_RATE:
            self.cooldown = min_spacing(speed_cols_per_frame)
            return ('G', self.elev), {'type':'fly'}

        if self.edge_protect > 0: self.edge_protect -= 1
        return ('G', self.elev), None

    def advance(self, n, speed_cols_per_frame):
        cells, enemies = [], []
        for _ in range(n):
            (cell, elev), enemy = self.next_cell(speed_cols_per_frame)
            cells.append((cell, elev))
            if enemy: enemies.append(enemy)
        return cells, enemies

class Player:
    def __init__(self, surface_row, x):
        self.x = x
        self.y = float(surface_row)
        self.vy = 0.0
        self.on_ground = True
        self.jump_buffer = False
    def request_jump(self): self.jump_buffer = True
    def update(self, surface_row, dt):
        if self.jump_buffer and self.on_ground:
            self.vy = JUMP_VEL
            self.on_ground = False
            self.jump_buffer = False
        if not self.on_ground:
            self.y -= self.vy * dt
            self.vy -= GRAVITY * dt
            if self.y >= surface_row:
                self.y = float(surface_row)
                self.vy = 0.0
                self.on_ground = True
        else:
            self.y = float(surface_row)

def draw_centered(stdscr, msg, row):
    h, w = stdscr.getmaxyx()
    x = max(0, (w - len(msg)) // 2)
    try: stdscr.addstr(row, x, msg)
    except curses.error: pass

def rects_overlap(ax, ay, aw, ah, bx, by, bw, bh):
    return (ax < bx + bw) and (bx < ax + aw) and (ay < by + bh) and (by < ay + ah)

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(0)
    curses.use_default_colors()

    start_time = time.time()
    last_speed_up = start_time
    last_shot_time = -1e9
    score = 0
    best = 0
    boost = False

    def layout():
        h, w = stdscr.getmaxyx()
        ground_row = h - 1 - GROUND_PAD
        # ensure vertical room for MAX_ELEV
        eff_max_elev = max(0, min(MAX_ELEV, ground_row - 3))
        base_row = ground_row - 1
        car_x = int(w * CAR_X_FRACTION)
        return h, w, ground_row, base_row, eff_max_elev, car_x

    h, w, ground_row, base_row, eff_max_elev, car_x = layout()

    warmup_cols = int(SAFE_START_SEC * START_SPEED * FPS) + w
    track = TrackGen(w, warmup_cols, eff_max_elev)
    speed = START_SPEED

    visible = deque(maxlen=w)   # (cell, elev)
    cells, _ = track.advance(w, speed)
    visible.extend(cells)

    scroll_acc = 0.0
    init_surface_row = base_row - (visible[0][1] if visible else 0)
    player = Player(init_surface_row, car_x)
    bullets = []   # {'x':float,'y':int}
    enemies = []   # {'x':float,'y':int,'shim':int}

    running, paused, game_over = True, False, False
    frame_time = 1.0 / FPS

    while running:
        t0 = time.time()
        nh, nw, ng, nb, ne, nx = layout()
        if (nh, nw) != (h, w) or ne != eff_max_elev:
            h, w, ground_row, base_row, eff_max_elev, car_x = nh, nw, ng, nb, ne, nx
            track.max_elev = eff_max_elev
            player.x = clamp(nx, 0, max(0, w - 1))
            visible = deque(list(visible)[-w:], maxlen=w)

        key = stdscr.getch()
        if key != -1:
            if key in (ord('q'), 27): running = False
            elif key in (ord('p'), ord('P')): paused = not paused
            elif key == curses.KEY_UP:
                if not game_over and not paused: player.request_jump()
            elif key == curses.KEY_RIGHT:
                boost = True
            elif key == ord(' '):
                now = time.time()
                if now - last_shot_time >= BULLET_COOLDOWN and not game_over and not paused:
                    last_shot_time = now
                    bullets.append({'x': float(player.x + CAR_W), 'y': int(round(player.y)) - 2})
            elif key in (ord('r'), ord('R')) and game_over:
                best = max(best, score)
                score = 0; game_over = False; speed = START_SPEED
                last_speed_up = time.time()
                warmup_cols = int(SAFE_START_SEC * START_SPEED * FPS) + w
                track = TrackGen(w, warmup_cols, eff_max_elev)
                visible.clear()
                cells, _ = track.advance(w, speed)
                visible.extend(cells)
                init_surface_row = base_row - (visible[0][1] if visible else 0)
                player = Player(init_surface_row, car_x)
                bullets.clear(); enemies.clear()

        if key == -1:
            boost = False

        if paused:
            stdscr.erase()
            draw_centered(stdscr, "PAUSED  [↑] jump  [Space] shoot  [→] turbo  [Q] quit", h // 2)
            stdscr.refresh(); time.sleep(frame_time); continue

        if not game_over:
            now = time.time()
            if now - last_speed_up >= SPEED_UP_EVERY:
                speed += SPEED_STEP
                last_speed_up = now

            current_speed = speed * (BOOST_MULTIPLIER if boost else 1.0)

            # world scroll
            scroll_acc += current_speed
            cols = int(scroll_acc)
            if cols > 0:
                scroll_acc -= cols
                for _ in range(cols):
                    if visible: visible.popleft()
                cells, sp_enemies = track.advance(cols, current_speed)
                visible.extend(cells)

                # spawn enemies at right side aligned to current surface
                right_elev = visible[-1][1] if visible else 0
                surface_row_right = base_row - right_elev
                enemy_top = max(0, surface_row_right - ENEMY_HEIGHT)
                for _ in sp_enemies:
                    enemies.append({'x': float(w - ENEMY_WIDTH), 'y': enemy_top, 'shim': 1})

                # shift existing enemies with world
                for e in enemies:
                    e['x'] -= cols

            # bullets
            for b in bullets:
                b['x'] += BULLET_SPEED_COLS
            bullets = [b for b in bullets if b['x'] < w]

            # enemy shimmy
            for e in enemies:
                e['x'] += ENEMY_SHIM_PER_FRAME * e['shim']
                e['shim'] *= -1
            enemies = [e for e in enemies if e['x'] + ENEMY_WIDTH > 0]

            # bullet vs enemy
            kept = []
            for e in enemies:
                ex, ey = int(round(e['x'])), int(round(e['y']))
                hit = False
                for b in bullets:
                    bx, by = int(round(b['x'])), int(round(b['y']))
                    if rects_overlap(bx, by, 1, 1, ex, ey, ENEMY_WIDTH, ENEMY_HEIGHT):
                        hit = True
                        score += ENEMY_SCORE
                        b['x'] = w + 999
                        break
                if not hit: kept.append(e)
            enemies = kept
            bullets = [b for b in bullets if b['x'] < w]

            # local surface at car column
            car_col = clamp(int(player.x), 0, w - 1)
            elev_here = visible[car_col][1] if visible else 0
            surface_row = base_row - elev_here

            # player physics
            player.update(surface_row, frame_time)

            # lethal collisions
            cell_here = visible[car_col][0] if visible else 'G'
            on_ground = abs(player.y - surface_row) < 0.51
            if on_ground and (cell_here == ' ' or cell_here == 'C'):
                game_over = True

            # step-up wall: only if wheels are BELOW the next surface
            next_col = clamp(car_col + 1, 0, w - 1)
            elev_next = visible[next_col][1] if visible else elev_here
            next_surface_row = base_row - elev_next
            # crash only when grounded and not already higher than (or equal to) the next surface
            if on_ground and elev_next > elev_here and player.y > next_surface_row - 0.01:
                game_over = True

            # enemy vs car AABB
            cx = int(player.x)
            car_bottom = int(round(player.y))
            car_top = car_bottom - (CAR_H - 1)
            for e in enemies:
                ex, ey = int(round(e['x'])), int(round(e['y']))
                if rects_overlap(cx, car_top, CAR_W, CAR_H, ex, ey, ENEMY_WIDTH, ENEMY_HEIGHT):
                    game_over = True
                    break

            if not game_over: score += cols

        # ---------------- Draw ----------------
        stdscr.erase()
        # draw stacked road plus visible risers at step-ups
        for x, (cell, elev) in enumerate(visible):
            # base thickness column
            try: stdscr.addch(ground_row, x, ROAD_CH)
            except curses.error: pass
            # fill interior up to surface
            for k in range(1, elev):
                ry = ground_row - k
                if 0 <= ry < h:
                    try: stdscr.addch(ry, x, ROAD_CH)
                    except curses.error: pass
            # surface row
            surf_y = ground_row - elev
            if cell != ' ':
                if 0 <= surf_y < h:
                    try: stdscr.addch(surf_y, x, ROAD_CH)
                    except curses.error: pass
            # riser visualization: if this column is higher than the previous, draw a vertical wall
            if x > 0:
                prev_elev = visible[x-1][1]
                if elev > prev_elev:
                    for ry in range(ground_row - elev + 1, ground_row - prev_elev + 1):
                        if 0 <= ry < h:
                            try: stdscr.addch(ry, x, ROAD_CH)
                            except curses.error: pass
            # cones exactly on surface
            if cell == 'C':
                cone_y = surf_y - 1
                if 0 <= cone_y < h:
                    try: stdscr.addch(cone_y, x, CONE_CH)
                    except curses.error: pass

        # enemies
        for e in enemies:
            ex, ey = int(round(e['x'])), int(round(e['y']))
            for i, line in enumerate(ENEMY_ART):
                ry = ey + i
                if 0 <= ry < h:
                    try: stdscr.addstr(ry, ex, line[: max(0, w - ex)])
                    except curses.error: pass

        # bullets
        for b in bullets:
            bx = int(round(b['x'])); by = int(round(b['y']))
            if 0 <= by < h and 0 <= bx < w:
                try: stdscr.addch(by, bx, BULLET_CH)
                except curses.error: pass

        # car
        cx = int(player.x)
        car_bottom = int(round(player.y))
        car_top = car_bottom - (CAR_H - 1)
        for i, line in enumerate(CAR_ART):
            ry = car_top + i
            if 0 <= ry < h:
                try: stdscr.addstr(ry, max(0, cx), line[: max(0, w - cx)])
                except curses.error: pass

        hud = f"Score {score}  Speed {speed:.2f}{' BOOST' if boost else ''}  [↑] Jump  [Space] Shoot  [→] Turbo  [P] Pause  [Q] Quit"
        try: stdscr.addstr(h - 1, 0, hud[:w])
        except curses.error: pass

        if game_over:
            best = max(best, score)
            draw_centered(stdscr, "GAME OVER  [R]estart  [Q]uit", max(1, h // 2))

        stdscr.refresh()
        elapsed = time.time() - t0
        if (sleep := frame_time - elapsed) > 0: time.sleep(sleep)

if __name__ == "__main__":
    try: curses.wrapper(main)
    except KeyboardInterrupt: pass
