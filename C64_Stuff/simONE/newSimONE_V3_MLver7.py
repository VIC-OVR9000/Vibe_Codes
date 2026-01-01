#!/usr/bin/env python3
# newSimONE.py
# TTY Metal-Slug-style simONE that can load PNG images as sprites
#
# Features:
# - Load planet and satellite sprites from PNG files (--planet-png, --sat-png).
# - PNGs are resized to the terminal-cell sprite dimensions using high-quality resampling
#   (Pillow LANCZOS). Alpha is respected and blended against the background so edges look smooth.
# - Falls back to procedurally generated smooth circles if Pillow isn't available or PNGs are missing.
# - Keeps previous features: 16/256/truecolor output modes, HUD, hold-timeout, CLI flags.
#
# Dependencies:
# - Pillow (optional, required only if you want PNG sprites)
#     pip3 install pillow
#
# Usage examples:
#   ./newSimONE.py --planet-png planet.png --sat-png sat.png --force-256 --smooth-level 4
#   ./newSimONE.py --planet-size 6 --sat-size 2 --planet-png assets/planet.png
#
# Controls:
#   W/A/S/D - thrust (hold)
#   Q       - quit
#   I       - toggle HUD/debug
#
# Notes:
# - This is intended for real TTYs / terminal emulators. For JupyterLab/browser terminals,
#   prefer the earlier ANSI-truecolor version.

import os
import sys
import time
import tty
import termios
import select
import signal
import shutil
import math
import argparse
import re


# Try to import Pillow (optional)
try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# -----------------------
# Command-line arguments
# -----------------------
def parse_args():
    p = argparse.ArgumentParser(description="TTY simONE with PNG sprite support")
    p.add_argument("--bg", type=str, default="#120854", help="Background color (#RRGGBB or r,g,b or name)")
    p.add_argument("--force-truecolor", action="store_true", help="Force truecolor output")
    p.add_argument("--force-256", action="store_true", help="Force 256-color output")
    p.add_argument("--force-16", action="store_true", help="Force 16-color output (TTY safe)")
    p.add_argument("--planet-size", type=int, default=None, help="Planet radius in terminal cells")
    p.add_argument("--sat-size", type=int, default=None, help="Satellite radius in terminal cells")
    p.add_argument("--planet-png", type=str, default=None, help="Path to planet PNG sprite")
    p.add_argument("--sat-png", type=str, default=None, help="Path to satellite PNG sprite")
    p.add_argument("--debug", action="store_true", help="Start with HUD/debug overlay enabled")
    p.add_argument("--hold-timeout", type=float, default=0.14, help="Key-hold timeout for thrust (s)")
    p.add_argument("--smooth-level", type=int, default=4, help="Supersample level (keeps for procedural fallback)")
    return p.parse_args()

args = parse_args()
SMOOTH_LEVEL = max(1, int(args.smooth_level))
HOLD_TIMEOUT = max(0.01, float(args.hold_timeout))

# -----------------------
# ANSI helpers & detection
# -----------------------
CSI = "\x1b["
HIDE_CURSOR = CSI + "?25l"
SHOW_CURSOR = CSI + "?25h"
CLEAR_SCREEN = CSI + "2J"
CURSOR_HOME = CSI + "H"
RESET = CSI + "0m"

FRAME_MS = 50  # ~20 FPS target

resized = False
def sigwinch(signum, frame):
    global resized
    resized = True

def get_term_size():
    ts = shutil.get_terminal_size(fallback=(80,24))
    return ts.lines, ts.columns

# parse RGB argument (hex, csv, small named)
def parse_rgb_arg(s):
    if not s:
        return None
    s = s.strip()
    m = re.match(r"^#?([0-9a-fA-F]{6})$", s)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i+2], 16) for i in (0,2,4))
    m = re.match(r"^(\d{1,3}),\s*(\d{1,3}),\s*(\d{1,3})$", s)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    names = {
        "darkpurple": (18,8,84),
        "dark_purple": (18,8,84),
        "purple": (80,24,120),
        "black": (0,0,0),
        "white": (255,255,255),
    }
    return names.get(s.lower(), None)

# color mode detection
def env_supports_truecolor():
    ct = os.environ.get("COLORTERM","").lower()
    return ("truecolor" in ct) or ("24bit" in ct)

def env_supports_256():
    term = os.environ.get("TERM","").lower()
    return "256color" in term

MODE = "16"
if args.force_truecolor:
    MODE = "truecolor"
elif args.force_256:
    MODE = "256"
elif args.force_16:
    MODE = "16"
else:
    if env_supports_truecolor():
        MODE = "truecolor"
    elif env_supports_256():
        MODE = "256"
    else:
        MODE = "16"

# -----------------------
# Color output implementations
# -----------------------
def bg_color_block_true(r,g,b):
    return f"\x1b[48;2;{r};{g};{b}m \x1b[0m"
def fg_on_bg_char_true(fg,bg,ch=" "):
    fr,fgc,fb = fg; br,bg2,bb = bg
    return f"\x1b[48;2;{br};{bg2};{bb}m\x1b[38;2;{fr};{fgc};{fb}m{ch}{RESET}"

def rgb_to_ansi256(r,g,b):
    def clamp255(v): return max(0, min(255, int(v)))
    r,g,b = clamp255(r), clamp255(g), clamp255(b)
    def to_index(v): return int(round((v/255.0)*5))
    ri,gi,bi = to_index(r), to_index(g), to_index(b)
    cube_code = 16 + 36*ri + 6*gi + bi
    def from_index(i): return 0 if i==0 else 55 + 40*i
    cube_r, cube_g, cube_b = from_index(ri), from_index(gi), from_index(bi)
    gray_level = int(round(((r+g+b)/3.0)/255.0*23))
    gray_val = 8 + gray_level*10
    gray_r = gray_g = gray_b = gray_val
    dc = (r-cube_r)**2 + (g-cube_g)**2 + (b-cube_b)**2
    dg = (r-gray_r)**2 + (g-gray_g)**2 + (b-gray_b)**2
    return cube_code if dc <= dg else 232 + gray_level

_bg_cache = {}
_fg_on_bg_cache = {}
def bg_color_block_256(r,g,b):
    key=(r,g,b)
    if key in _bg_cache: return _bg_cache[key]
    code = rgb_to_ansi256(r,g,b)
    esc = f"\x1b[48;5;{code}m \x1b[0m"
    _bg_cache[key] = esc
    return esc
def fg_on_bg_char_256(fg,bg,ch=" "):
    key=(fg,bg,ch)
    if key in _fg_on_bg_cache: return _fg_on_bg_cache[key]
    fcode = rgb_to_ansi256(*fg); bcode = rgb_to_ansi256(*bg)
    esc = f"\x1b[48;5;{bcode}m\x1b[38;5;{fcode}m{ch}{RESET}"
    _fg_on_bg_cache[key] = esc
    return esc

ANSI16 = [
    ((0,0,0),30,40), ((128,0,0),31,41), ((0,128,0),32,42), ((128,128,0),33,43),
    ((0,0,128),34,44), ((128,0,128),35,45), ((0,128,128),36,46), ((192,192,192),37,47),
    ((128,128,128),90,100), ((255,0,0),91,101), ((0,255,0),92,102), ((255,255,0),93,103),
    ((0,0,255),94,104), ((255,0,255),95,105), ((0,255,255),96,106), ((255,255,255),97,107),
]
def nearest_ansi16_code(rgb):
    r,g,b = rgb
    best=None; best_d=None
    for acol, fg_code, bg_code in ANSI16:
        ar,ag,ab = acol
        d=(r-ar)**2+(g-ag)**2+(b-ab)**2
        if best_d is None or d<best_d:
            best_d=d; best=(fg_code,bg_code)
    return best
_bg_cache16 = {}
_fg_cache16 = {}
def bg_color_block_16(r,g,b):
    key=(r,g,b)
    if key in _bg_cache16: return _bg_cache16[key]
    _, bg_code = nearest_ansi16_code(key)
    esc = f"\x1b[{bg_code}m \x1b[0m"
    _bg_cache16[key] = esc
    return esc
def fg_on_bg_char_16(fg,bg,ch=" "):
    key=(fg,bg,ch)
    if key in _fg_cache16: return _fg_cache16[key]
    fg_code,_ = nearest_ansi16_code(fg); _, bg_code = nearest_ansi16_code(bg)
    esc = f"\x1b[{bg_code};{fg_code}m{ch}{RESET}"
    _fg_cache16[key] = esc
    return esc

# select final functions
if MODE == "truecolor":
    bg_color_block = bg_color_block_true
    fg_on_bg_char = fg_on_bg_char_true
elif MODE == "256":
    bg_color_block = bg_color_block_256
    fg_on_bg_char = fg_on_bg_char_256
else:
    bg_color_block = bg_color_block_16
    fg_on_bg_char = fg_on_bg_char_16

# -----------------------
# Palette & helpers
# -----------------------
def clamp(v,a=0,b=255): return max(a, min(b, int(v)))
def blend(c1,c2,t): return tuple(clamp(c1[i]*(1-t)+c2[i]*t) for i in range(3))

PALETTE = {
    "planet": (200,120,80),
    "planet_edge": (120,60,30),
    "sat": (240,240,80),
    "sat_edge": (200,160,30),
}

bg_rgb = parse_rgb_arg(args.bg) or (18,8,84)
controls_fg = (245,245,245)

# -----------------------
# PNG loading + rasterization to terminal-cell sprite
# -----------------------
def load_png_sprite(path, target_cells, bg_rgb, use_supersample=True, supersample=4):
    """
    Load PNG and convert to a sprite sized target_cells x target_cells.
    Returns sprite as list-of-lists where each cell is either None (transparent) or an (r,g,b) tuple.
    - If PIL not available or load fails, returns None.
    - Uses PIL resize with LANCZOS which provides good antialiasing; respects alpha channel.
    - If use_supersample=False, simply resize to target size. If True and supersample>1, resize to
      target*supersample then downsample by averaging to improve quality (optional).
    """
    if not PIL_AVAILABLE:
        return None
    try:
        im = Image.open(path).convert("RGBA")
    except Exception:
        return None

    # Keep square output: target w/h = target_cells x target_cells
    cells = target_cells
    if cells <= 0:
        return None

    # If supersampling requested, resize to (cells*ss) then downsample by box averaging using PIL
    ss = max(1, int(supersample)) if use_supersample else 1
    hr = cells * ss
    # preserve aspect by fitting image into square and centering; create RGBA background transparent
    im_w, im_h = im.size
    # compute scale factor to cover square (we want to preserve content scale)
    scale = max(hr / im_w, hr / im_h)
    new_w = max(1, int(round(im_w * scale)))
    new_h = max(1, int(round(im_h * scale)))
    im_resized = im.resize((new_w, new_h), resample=Image.LANCZOS)
    # crop or pad to hr x hr centered
    if new_w != hr or new_h != hr:
        # create transparent canvas hr x hr, paste centered
        canvas = Image.new("RGBA", (hr, hr), (0,0,0,0))
        ox = (hr - new_w) // 2
        oy = (hr - new_h) // 2
        canvas.paste(im_resized, (ox, oy), im_resized)
        hr_img = canvas
    else:
        hr_img = im_resized

    # Now downsample by block averaging into cells x cells
    sprite = [[None for _ in range(cells)] for _ in range(cells)]
    hr_px = hr_img.load()
    for cy in range(cells):
        for cx in range(cells):
            # region in HR coords
            xs = cx * ss
            ys = cy * ss
            accum_r = accum_g = accum_b = 0.0
            accum_a = 0.0
            count = 0
            for oy in range(ss):
                for ox in range(ss):
                    x = xs + ox
                    y = ys + oy
                    r,g,b,a = hr_px[x,y]  # 0..255
                    accum_r += r * (a / 255.0)
                    accum_g += g * (a / 255.0)
                    accum_b += b * (a / 255.0)
                    accum_a += a
                    count += 1
            if count == 0:
                sprite[cy][cx] = None
                continue
            avg_a = accum_a / (count * 255.0)  # 0..1
            if avg_a < 0.01:
                # treat as fully transparent
                sprite[cy][cx] = None
                continue
            # average premultiplied color -> un-premultiply by alpha
            if avg_a > 0:
                avg_r = accum_r / (count * avg_a)
                avg_g = accum_g / (count * avg_a)
                avg_b = accum_b / (count * avg_a)
            else:
                avg_r = avg_g = avg_b = 0.0
            # blend with background by coverage fraction (avg_a) to produce final cell color
            final_r = int(round(avg_r * avg_a + bg_rgb[0] * (1 - avg_a)))
            final_g = int(round(avg_g * avg_a + bg_rgb[1] * (1 - avg_a)))
            final_b = int(round(avg_b * avg_a + bg_rgb[2] * (1 - avg_a)))
            sprite[cy][cx] = (final_r, final_g, final_b)
    return sprite

# -----------------------
# Procedural fallback smooth circle (keeps older behavior)
# -----------------------
def generate_smooth_circle(radius_cells, color_rgb, edge_rgb=None, supersample=4, edge_width=0.28):
    # uses previous supersampling algorithm (kept as fallback if PNG not used)
    cells = radius_cells * 2 + 1
    ss = max(1, int(supersample))
    high = cells * ss
    center = (high - 1) / 2.0
    rad_hr = radius_cells * ss
    edge_thickness_hr = max(1.0, edge_width * rad_hr)
    hr_color = [None] * (high * high)
    for y in range(high):
        dy = y - center
        for x in range(high):
            dx = x - center
            dist = math.hypot(dx, dy)
            if dist <= rad_hr + 0.25 * ss:
                dn = dist / (rad_hr + 1e-9)
                t_edge = 0.0
                edge_start = max(0.0, (rad_hr - edge_thickness_hr) / (rad_hr + 1e-9))
                if dn >= edge_start:
                    if (1.0 - edge_start) > 1e-6:
                        t_edge = (dn - edge_start) / (1.0 - edge_start)
                        t_edge = max(0.0, min(1.0, t_edge))
                    else:
                        t_edge = 1.0
                if edge_rgb is not None:
                    local = blend(color_rgb, edge_rgb, t_edge)
                else:
                    local = color_rgb
                hr_color[y * high + x] = local
            else:
                hr_color[y * high + x] = None
    sprite = [[None for _ in range(cells)] for _ in range(cells)]
    for cy in range(cells):
        for cx in range(cells):
            ys = cy * ss; xs = cx * ss
            accum_r = accum_g = accum_b = 0.0
            covered = 0
            for oy in range(ss):
                for ox in range(ss):
                    idx = (ys + oy) * high + (xs + ox)
                    val = hr_color[idx]
                    if val is not None:
                        r,g,b = val
                        accum_r += r; accum_g += g; accum_b += b
                        covered += 1
            if covered == 0:
                sprite[cy][cx] = None
            else:
                avg_r = accum_r / covered; avg_g = accum_g / covered; avg_b = accum_b / covered
                cov = covered / (ss * ss)
                final_r = int(round(avg_r * cov + bg_rgb[0] * (1 - cov)))
                final_g = int(round(avg_g * cov + bg_rgb[1] * (1 - cov)))
                final_b = int(round(avg_b * cov + bg_rgb[2] * (1 - cov)))
                sprite[cy][cx] = (final_r, final_g, final_b)
    return sprite

# -----------------------
# Drawing helpers
# -----------------------
def place_sprite_on_canvas(canvas, sprite, top, left):
    h = len(sprite); w = len(sprite[0]) if h else 0
    sh = len(canvas); sw = len(canvas[0]) if sh else 0
    for sy in range(h):
        cy = top + sy
        if cy < 0 or cy >= sh: continue
        for sx in range(w):
            cx = left + sx
            if cx < 0 or cx >= sw: continue
            pixel = sprite[sy][sx]
            if pixel is None: continue
            r,g,b = pixel
            canvas[cy][cx] = bg_color_block(r,g,b)

# -----------------------
# Input smoothing / key-hold
# -----------------------
last_key_times = {}
def read_key_nonblocking_record():
    dr,_,_ = select.select([sys.stdin], [], [], 0)
    if dr:
        try:
            c = sys.stdin.read(1)
            if not c:
                return None
            t = time.time()
            kc = c.lower()
            if kc in ("w","a","s","d","q","i"):
                last_key_times[kc] = t
            return c
        except (IOError, OSError):
            return None
    return None

def key_recent(k):
    return last_key_times.get(k, 0) >= time.time() - HOLD_TIMEOUT

# -----------------------
# Main simulation
# -----------------------
def main():
    global resized
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    AC, DE, TH = 0.05, 0.98, 0.42
    debug = bool(args.debug)
    try:
        tty.setcbreak(fd)
        os.write(1, (HIDE_CURSOR + CLEAR_SCREEN + CURSOR_HOME).encode())
        signal.signal(signal.SIGWINCH, sigwinch)

        sh, sw = get_term_size()
        y0, x0 = sh//2, sw//2
        y1, x1 = float(y0), float(x0 + 10)
        vy1, vx1 = 0.0, 0.0

        # sprite sizes (cells)
        if args.planet_size and args.planet_size >= 1:
            planet_radius_cells = args.planet_size
        else:
            planet_radius_cells = max(3, min(12, min(sh, sw)//8))
        if args.sat_size is not None and args.sat_size >= 0:
            sat_radius = args.sat_size
        else:
            sat_radius = 1 if min(sh, sw) < 40 else 2

        # Try to load PNG sprites if paths provided and PIL available
        use_png_planet = False
        use_png_sat = True
        planet_sprite = None
        sat_frames = None

        if args.planet_png and PIL_AVAILABLE and os.path.isfile(args.planet_png):
            ps = load_png_sprite(args.planet_png, planet_radius_cells * 2 + 1, bg_rgb,
                                 use_supersample=True, supersample=SMOOTH_LEVEL)
            if ps is not None:
                planet_sprite = ps
                use_png_planet = True

        if args.sat_png and PIL_AVAILABLE and os.path.isfile(args.sat_png):
            ssprite = load_png_sprite(args.sat_png, sat_radius * 2 + 1, bg_rgb,
                                      use_supersample=True, supersample=max(1,SMOOTH_LEVEL))
            if ssprite is not None:
                sat_frames = [ssprite, ssprite]  # single frame used for both idle/firing unless multiple PNGs provided
                use_png_sat = True

        # If no PNGs or failed load, fall back to procedural smoothed sprites
        if planet_sprite is None:
            planet_sprite = generate_smooth_circle(planet_radius_cells, PALETTE["planet"],
                                                   PALETTE["planet_edge"], supersample=SMOOTH_LEVEL,
                                                   edge_width=0.28)
        if sat_frames is None:
            sat_frames = []
            sat_frames.append(generate_smooth_circle(sat_radius, PALETTE["sat"], PALETTE["sat_edge"],
                                                     supersample=max(1,SMOOTH_LEVEL), edge_width=0.35))
            brighter = tuple(min(255, int(c+48)) for c in PALETTE["sat"])
            sat_frames.append(generate_smooth_circle(sat_radius, brighter, PALETTE["sat_edge"],
                                                     supersample=max(1,SMOOTH_LEVEL), edge_width=0.35))

        sat_h = len(sat_frames[0]); sat_w = len(sat_frames[0][0])

        # cache bg cell
        bg_cell = bg_color_block(*bg_rgb)

        # set terminal title (best-effort)
        try:
            title = f"newSimONE (mode={MODE})"
            os.write(1, (CSI + "]0;" + title + "\x07").encode())
        except Exception:
            pass

        last_frame_time = time.time()
        fps_smooth = 0.0

        while True:
            frame_start = time.time()
            if resized:
                sh, sw = get_term_size()
                y0, x0 = sh//2, sw//2
                x1 = x1 % sw; y1 = y1 % sh
                if not args.planet_size:
                    planet_radius_cells = max(3, min(12, min(sh, sw)//8))
                if not args.sat_size:
                    sat_radius = 1 if min(sh, sw) < 40 else 2
                # reload sprites if PNGs used, to adapt to new sizes
                if use_png_planet and args.planet_png and os.path.isfile(args.planet_png) and PIL_AVAILABLE:
                    tmp = load_png_sprite(args.planet_png, planet_radius_cells * 2 + 1, bg_rgb,
                                          use_supersample=True, supersample=SMOOTH_LEVEL)
                    if tmp is not None:
                        planet_sprite = tmp
                else:
                    planet_sprite = generate_smooth_circle(planet_radius_cells, PALETTE["planet"],
                                                           PALETTE["planet_edge"], supersample=SMOOTH_LEVEL,
                                                           edge_width=0.28)
                if use_png_sat and args.sat_png and os.path.isfile(args.sat_png) and PIL_AVAILABLE:
                    tmp = load_png_sprite(args.sat_png, sat_radius * 2 + 1, bg_rgb,
                                          use_supersample=True, supersample=max(1,SMOOTH_LEVEL))
                    if tmp is not None:
                        sat_frames = [tmp,tmp]
                else:
                    sat_frames = []
                    sat_frames.append(generate_smooth_circle(sat_radius, PALETTE["sat"], PALETTE["sat_edge"],
                                                             supersample=max(1,SMOOTH_LEVEL), edge_width=0.35))
                    brighter = tuple(min(255, int(c+48)) for c in PALETTE["sat"])
                    sat_frames.append(generate_smooth_circle(sat_radius, brighter, PALETTE["sat_edge"],
                                                             supersample=max(1,SMOOTH_LEVEL), edge_width=0.35))
                sat_h = len(sat_frames[0]); sat_w = len(sat_frames[0][0])
                resized = False

            # Input
            key = read_key_nonblocking_record()
            if key:
                k = key.lower()
                if k == "q":
                    break
                if k == "i":
                    debug = not debug

            # thrust via recent key timestamps (simulated hold)
            thrusting = False
            if key_recent("w"):
                vy1 -= TH; thrusting = True
            if key_recent("s"):
                vy1 += TH; thrusting = True
            if key_recent("a"):
                vx1 -= TH; thrusting = True
            if key_recent("d"):
                vx1 += TH; thrusting = True

            # gravity towards planet center
            if x1 < x0: vx1 += AC
            else: vx1 -= AC
            if y1 < y0: vy1 += AC
            else: vy1 -= AC

            # integrate
            x1 += vx1; y1 += vy1
            vx1 *= DE; vy1 *= DE

            if sw <= 0: sw = 1
            if sh <= 0: sh = 1
            x1 = x1 % sw; y1 = y1 % sh

            # build canvas filled with bg
            bg_cell = bg_color_block(*bg_rgb)
            canvas = [[bg_cell for _ in range(sw)] for _ in range(sh)]

            # controls line
            controls = "W A S D: THRUST | Q: QUIT | I: TOGGLE HUD"
            if len(controls) >= sw:
                controls = controls[:sw]
            for i,ch in enumerate(controls):
                canvas[-1][i] = fg_on_bg_char(controls_fg, bg_rgb, ch)

            # draw planet (center)
            pr = len(planet_sprite)
            top = int(round(y0)) - pr//2
            left = int(round(x0)) - pr//2
            place_sprite_on_canvas(canvas, planet_sprite, top, left)

            # draw satellite
            frame_index = 1 if thrusting else 0
            if thrusting and (time.time()*12) % 2 > 1:
                frame_index = 0
            sat_sprite = sat_frames[frame_index]
            top = int(round(y1)) - sat_h//2
            left = int(round(x1)) - sat_w//2
            place_sprite_on_canvas(canvas, sat_sprite, top, left)

            # HUD
            if debug:
                now = time.time()
                dt = now - last_frame_time if last_frame_time else 0.0
                last_frame_time = now
                if dt > 0:
                    fps = 1.0 / dt
                    fps_smooth = fps_smooth * 0.85 + fps * 0.15 if 'fps_smooth' in locals() else fps
                else:
                    fps = 0.0
                hud_lines = [
                    f"MODE: {MODE}   POS: ({x1:.1f},{y1:.1f})   V: ({vx1:.2f},{vy1:.2f})",
                    f"FPS: {fps_smooth:.1f}   PlanetR: {planet_radius_cells}   SatR: {sat_radius}",
                    f"SMOOTH: {SMOOTH_LEVEL}  HOLD_TIMEOUT: {HOLD_TIMEOUT:.3f}s",
                    f"PIL: {'yes' if PIL_AVAILABLE else 'no'}  PNG_planet: {'yes' if use_png_planet else 'no'}  PNG_sat: {'yes' if use_png_sat else 'no'}"
                ]
                hud_fg = (245,245,245)
                for hi, line in enumerate(hud_lines):
                    if hi >= sh-2: break
                    for ci, ch in enumerate(line):
                        if ci >= sw: break
                        canvas[hi][ci] = fg_on_bg_char(hud_fg, bg_rgb, ch)

            # output in single write
            out = CURSOR_HOME + "\n".join("".join(r) for r in canvas)
            os.write(1, out.encode("utf-8"))

            # frame pacing
            elapsed = time.time() - frame_start
            to_sleep = FRAME_MS/1000.0 - elapsed
            if to_sleep > 0:
                time.sleep(to_sleep)

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sh, sw = get_term_size()
        os.write(1, (CSI + f"{sh};1H" + SHOW_CURSOR + RESET + "\n").encode())

if __name__ == "__main__":
    # ensure real tty
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("This program needs a TTY (run on a Linux virtual console or terminal).", file=sys.stderr)
        sys.exit(1)
    if (args.planet_png or args.sat_png) and not PIL_AVAILABLE:
        print("Pillow (PIL) is required to use PNG sprites. Install with: pip3 install pillow", file=sys.stderr)
    try:
        main()
    except KeyboardInterrupt:
        os.write(1, (SHOW_CURSOR + RESET + "\n").encode())
        raise
