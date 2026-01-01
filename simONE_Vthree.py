#!/usr/bin/env python3
# ANSI-based spriteified rewrite of simONE/satellite.py for JupyterLab terminal
# - Replaces single-character planet/satellite with small ANSI "pixel" sprites (Metal Gear style)
# - Works in browser-based terminals (xterm.js / JupyterLab) by using 24-bit ANSI color blocks.
# - No external libs required.
#
# Notes:
# - JupyterLab's terminal is a browser terminal (xterm.js) and cannot display inline images/protocols
#   like Kitty's icat or SIXEL. The approach below renders small pixel-art sprites using colored
#   terminal cells (background color + space).
# - If your terminal does NOT support truecolor (24-bit), the result may look off. If needed,
#   run the script in a desktop terminal that supports truecolor or use the other recommended
#   approaches described below.
#
# Usage:
#   python3 newSimONE.py
#
# Controls:
#   W/A/S/D - thrust (satellite thruster flicker while thrusting)
#   Q       - quit
#
# Author: adapted for Sprite output by VIC-OVR9000 assistant
# Date: 2026-01-01

import os
import sys
import time
import tty
import termios
import select
import signal
import shutil
import math

# ANSI helpers
CSI = "\x1b["
HIDE_CURSOR = CSI + "?25l"
SHOW_CURSOR = CSI + "?25h"
CLEAR_SCREEN = CSI + "2J"
CURSOR_HOME = CSI + "H"
RESET = CSI + "0m"

FRAME_MS = 50  # 50 ms -> ~20 FPS

resized = False


def sigwinch(signum, frame):
    global resized
    resized = True


def get_term_size():
    ts = shutil.get_terminal_size(fallback=(80, 24))
    return ts.lines, ts.columns


def read_key_nonblocking():
    # returns a single character string or None
    dr, _, _ = select.select([sys.stdin], [], [], 0)
    if dr:
        try:
            c = sys.stdin.read(1)
            return c
        except (IOError, OSError):
            return None
    return None


# -----------------------
# Sprite generation utils
# -----------------------

def bg_color_block(r, g, b):
    """Return a string representing one terminal cell painted with background RGB color."""
    # Use a single space with background set; reset after to avoid bleeding.
    return f"\x1b[48;2;{r};{g};{b}m \x1b[0m"


def fg_color_char(r, g, b, ch="█"):
    """Return a string with foreground colored block (less used here)."""
    return f"\x1b[38;2;{r};{g};{b}m{ch}{RESET}"


def clamp(v, a=0, b=255):
    return max(a, min(b, int(v)))


def blend(c1, c2, t):
    """Linear blend between two RGB tuples"""
    return tuple(clamp(c1[i] * (1 - t) + c2[i] * t) for i in range(3))


# Metal Gear-ish palette (muted greens, olive, gray, metal)
PALETTE = {
    "olive": (96, 106, 41),
    "dark_olive": (66, 76, 33),
    "metal": (140, 140, 150),
    "shadow": (30, 30, 30),
    "highlight": (200, 200, 190),
    "thruster1": (255, 160, 30),
    "thruster2": (255, 80, 10),
    "black": (0, 0, 0),
    "white": (230, 230, 230),
}


def generate_planet_sprite(radius):
    """Generate a simple shaded circular planet sprite (2D array of RGB or None)."""
    size = radius * 2 + 1
    cx = cy = radius
    sprite = [[None for _ in range(size)] for _ in range(size)]
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= radius + 0.25:
                # shading based on angle / distance
                t = dist / (radius + 0.01)  # 0..1 (edge)
                # hue between olive and metal for a "camouflage/tech" look
                base = blend(PALETTE["olive"], PALETTE["metal"], 0.35)
                shade = blend(base, PALETTE["shadow"], t * 0.7)
                # rim highlight on upper-left to simulate light
                light = 0.25 * (1 - ((dx - radius * 0.3) ** 2 + (dy + radius * 0.3) ** 2) / (radius * radius + 1))
                light = max(0.0, light)
                final = blend(shade, PALETTE["highlight"], light)
                sprite[y][x] = tuple(int(c) for c in final)
            else:
                sprite[y][x] = None
    return sprite


def generate_satellite_frames():
    """
    Generate two small frames for the "satellite" (soldier/robot) sprite.
    Each frame is a list-of-lists of RGB or None (transparent).
    Size chosen small so terminal cells represent pixels.
    """
    frames = []

    # frame 0: idle
    # 5x5 sprite roughly:
    #  ..X..
    #  .XXX.
    #  XXXXX
    #  .X.X.
    #  X...X  (legs)
    idle = [
        [None, None, PALETTE["dark_olive"], None, None],
        [None, PALETTE["dark_olive"], PALETTE["dark_olive"], PALETTE["dark_olive"], None],
        [PALETTE["dark_olive"], PALETTE["metal"], PALETTE["metal"], PALETTE["metal"], PALETTE["dark_olive"]],
        [None, PALETTE["dark_olive"], None, PALETTE["dark_olive"], None],
        [PALETTE["dark_olive"], None, None, None, PALETTE["dark_olive"]],
    ]

    # frame 1: thrust firing to the left/back - add thruster pixels on right-bottom (when thrust applied)
    thrust = [
        [None, None, PALETTE["dark_olive"], None, None],
        [None, PALETTE["dark_olive"], PALETTE["dark_olive"], PALETTE["dark_olive"], None],
        [PALETTE["dark_olive"], PALETTE["metal"], PALETTE["metal"], PALETTE["metal"], PALETTE["dark_olive"]],
        [None, PALETTE["dark_olive"], PALETTE["thruster1"], PALETTE["dark_olive"], PALETTE["thruster2"]],
        [PALETTE["dark_olive"], None, PALETTE["thruster1"], None, PALETTE["dark_olive"]],
    ]

    frames.append(idle)
    frames.append(thrust)
    return frames


# -----------------------
# Drawing helpers
# -----------------------

def place_sprite_on_canvas(canvas, sprite, top, left):
    """
    canvas: 2D list of cell strings (already with ANSI if colored)
    sprite: 2D list of RGB triples or None
    top,left: where sprite[0][0] maps to canvas[top][left]
    """
    h = len(sprite)
    w = len(sprite[0]) if h else 0
    sh = len(canvas)
    sw = len(canvas[0]) if sh else 0
    for sy in range(h):
        cy = top + sy
        if cy < 0 or cy >= sh:
            continue
        for sx in range(w):
            cx = left + sx
            if cx < 0 or cx >= sw:
                continue
            pixel = sprite[sy][sx]
            if pixel is None:
                continue
            r, g, b = pixel
            canvas[cy][cx] = bg_color_block(r, g, b)


# -----------------------
# Main simulation code
# -----------------------

def main():
    global resized

    # Save tty state
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    # Physics constants (kept from original)
    AC, DE, TH = 0.05, 0.98, 0.4

    try:
        # Put terminal in raw mode so we can read single keypresses
        tty.setcbreak(fd)

        # Hide cursor, clear screen, move home
        os.write(1, (HIDE_CURSOR + CLEAR_SCREEN + CURSOR_HOME).encode())

        # Setup SIGWINCH handler to detect resizes
        signal.signal(signal.SIGWINCH, sigwinch)

        sh, sw = get_term_size()
        # initial planet center
        y0, x0 = sh // 2, sw // 2
        # satellite initial position
        y1, x1 = y0, x0 + 10
        vy1, vx1 = 0.0, 0.0

        # Pre-generate sprites
        planet_radius_cells = max(3, min(12, min(sh, sw) // 8))
        planet_sprite = generate_planet_sprite(planet_radius_cells)
        sat_frames = generate_satellite_frames()
        sat_w = len(sat_frames[0][0])
        sat_h = len(sat_frames[0])

        last_time = time.time()
        thrusting = False
        thrust_timer = 0.0

        while True:
            frame_start = time.time()
            # handle resize
            if resized:
                sh, sw = get_term_size()
                y0, x0 = sh // 2, sw // 2
                # ensure satellite stays in-bounds
                x1 = x1 % sw
                y1 = y1 % sh
                # regenerate planet if terminal got much larger/smaller
                planet_radius_cells = max(3, min(12, min(sh, sw) // 8))
                planet_sprite = generate_planet_sprite(planet_radius_cells)
                resized = False

            # Input (non-blocking)
            key = read_key_nonblocking()
            thrusting = False
            if key:
                k = key.lower()
                if k == 'w':
                    vy1 -= TH
                    thrusting = True
                elif k == 's':
                    vy1 += TH
                    thrusting = True
                elif k == 'a':
                    vx1 -= TH
                    thrusting = True
                elif k == 'd':
                    vx1 += TH
                    thrusting = True
                elif k == 'q':
                    break
                # ignore other keys

            # Gravity logic (same as original)
            if x1 < x0:
                vx1 += AC
            else:
                vx1 -= AC
            if y1 < y0:
                vy1 += AC
            else:
                vy1 -= AC

            # Apply velocity and damping
            x1 += vx1
            y1 += vy1
            vx1 *= DE
            vy1 *= DE

            # Wrap
            if sw <= 0:
                sw = 1
            if sh <= 0:
                sh = 1
            x1 = x1 % sw
            y1 = y1 % sh

            # Build canvas: 2D list of plain strings (one cell each)
            canvas = [[" " for _ in range(sw)] for _ in range(sh)]

            # Put controls on bottom row (overwrite)
            controls = "W-A-S-D: THRUST | Q: QUIT"
            if len(controls) >= sw:
                controls = controls[:sw]
            for i, ch in enumerate(controls):
                canvas[-1][i] = ch

            # Draw planet sprite centered at (y0, x0)
            # planet_sprite has size pr x pr
            pr = len(planet_sprite)
            top = int(y0) - pr // 2
            left = int(x0) - pr // 2
            place_sprite_on_canvas(canvas, planet_sprite, top, left)

            # Draw satellite sprite (choose frame)
            frame_index = 1 if thrusting else 0
            # simple flicker animation if thrusting
            if thrusting:
                # alternate between frame 0 and 1 based on time for flicker
                if (time.time() * 8) % 2 > 1:
                    frame_index = 0
            sat_sprite = sat_frames[frame_index]
            # compute top-left to place so that sprite center is at (y1,x1)
            top = int(y1) - sat_h // 2
            left = int(x1) - sat_w // 2
            place_sprite_on_canvas(canvas, sat_sprite, top, left)

            # Join and write to terminal in a single write for best performance.
            # Because cells may contain ANSI sequences, join each cell and append newline.
            buf_lines = []
            for row in canvas:
                buf_lines.append("".join(row))
            buf = CURSOR_HOME + "\n".join(buf_lines)
            os.write(1, buf.encode("utf-8"))

            # Frame pacing (keep ~FRAME_MS)
            elapsed = (time.time() - frame_start)
            to_sleep = FRAME_MS / 1000.0 - elapsed
            if to_sleep > 0:
                time.sleep(to_sleep)
            # else: behind schedule, immediately continue

    finally:
        # Restore terminal
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        # Show cursor and move to bottom so prompt isn't overdrawn
        sh, sw = get_term_size()
        os.write(1, (CSI + f"{sh};1H" + SHOW_CURSOR + RESET + "\n").encode())


if __name__ == "__main__":
    # Quick check: ensure we're running on a tty
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("This program needs a TTY (run in a real terminal).", file=sys.stderr)
        sys.exit(1)
    try:
        main()
    except KeyboardInterrupt:
        os.write(1, (SHOW_CURSOR + RESET + "\n").encode())
        raise
