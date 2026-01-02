import sys, os, time, tty, termios, select

# --- Retro Palette Configuration ---
T_LG = "\033[48;2;120;220;120m" # Light Green (Head/Highlights)
T_DG = "\033[48;2;40;140;40m"   # Dark Green (Body/Shadows)
S_LB = "\033[48;2;160;110;40m"  # Light Brown (Shell Pattern)
S_DB = "\033[48;2;90;60;20m"    # Dark Brown (Shell Base)
BG   = "\033[48;2;20;40;20m"    # Dark Moss Background
RESET = "\033[0m"

# Bitmap Legend: 0: BG, 1: Head, 2: Dark Body, 3: Shell Base, 4: Shell Pattern, 5: Eye
SPRITE_FRAME_A = [
    [0,1,1,1,0,0,0,0],
    [1,1,5,1,0,3,3,3],
    [2,0,1,3,3,4,3,3],
    [0,0,3,3,4,3,4,3],
    [2,0,2,3,3,4,3,3],
    [0,0,0,3,3,3,3,0],
    [0,0,2,0,0,2,0,0]
]

SPRITE_FRAME_B = [
    [0,1,1,1,0,0,0,0],
    [1,1,5,1,0,3,3,3],
    [0,2,1,3,3,4,3,3],
    [0,0,3,3,4,3,4,3],
    [0,2,0,3,3,4,3,3],
    [0,0,0,3,3,3,3,0],
    [2,0,0,0,2,0,0,0]
]

COLOR_MAP = {
    0: f"{BG} {RESET}",
    1: f"{T_LG} {RESET}",
    2: f"{T_DG} {RESET}",
    3: f"{S_DB} {RESET}",
    4: f"{S_LB} {RESET}",
    5: "\033[48;2;255;255;255m\033[38;2;0;0;0m.\033[0m" # White eye with black pupil
}

class AdvancedRetroTurtle:
    def __init__(self):
        self.rows, self.cols = os.get_terminal_size().lines - 1, os.get_terminal_size().columns
        self.tx, self.ty = self.cols // 2, self.rows // 2
        self.frame = 0
        self.moving = False

    def draw(self):
        buffer = [[COLOR_MAP[0] for _ in range(self.cols)] for _ in range(self.rows)]
        sprite = SPRITE_FRAME_B if (self.frame % 2 == 0 and self.moving) else SPRITE_FRAME_A

        for r, row_data in enumerate(sprite):
            for c, val in enumerate(row_data):
                py, px = self.ty + r - 3, self.tx + c - 4
                if 0 <= py < self.rows and 0 <= px < self.cols:
                    if val != 0: buffer[py][px] = COLOR_MAP[val]

        sys.stdout.write("\033[H" + "\n".join("".join(row) for row in buffer))
        sys.stdout.flush()

def main():
    sim = AdvancedRetroTurtle()
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\033[2J\033[?25l")
        while True:
            sim.draw()
            sim.moving = False
            if select.select([sys.stdin], [], [], 0.05)[0]:
                key = sys.stdin.read(3)
                sim.moving = True
                sim.frame += 1
                if key == '\x1b[A': sim.ty -= 1
                elif key == '\x1b[B': sim.ty += 1
                elif key == '\x1b[C': sim.tx += 1
                elif key == '\x1b[D': sim.tx -= 1
                elif 'q' in key.lower(): break
            time.sleep(0.02)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sys.stdout.write("\033[?25h\n")

if __name__ == "__main__":
    main()
