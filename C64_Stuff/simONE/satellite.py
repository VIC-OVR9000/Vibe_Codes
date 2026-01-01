import curses
import time

def main(stdscr):
    # 10-15: Setup Screen (Black bg, White text, No cursor)
    curses.curs_set(0)
    stdscr.nodelay(True)  # Non-blocking input (like GET A$)
    stdscr.timeout(50)    # 50ms frame rate

    # 60: Initial Variables (Scaled for terminal rows/cols)
    sh, sw = stdscr.getmaxyx()
    y0, x0 = sh // 2, sw // 2    # Planet Position (Center)
    y1, x1 = y0, x0 + 10         # Sat Position
    vy1, vx1 = 0.0, 0.0          # Velocities

    # 65: Physics Constants
    AC, DE, TH = 0.05, 0.98, 0.4

    while True:
        stdscr.erase() # 10: Clear Screen

        # 18: Display Controls
        stdscr.addstr(sh-1, 0, "W-A-S-D: THRUST | Q: QUIT")

        # 70: Draw Planet (Blue) and Satellite (White)
        stdscr.addstr(y0, x0, "O", curses.A_BOLD)

        # 74: Handle "Sprite" change (Thrust vs Box)
        key = stdscr.getch()
        char = "■"

        # 82-105: Input Handling
        if key in [ord('w'), ord('W')]: vy1 -= TH; char = "*"
        if key in [ord('s'), ord('S')]: vy1 += TH; char = "*"
        if key in [ord('a'), ord('A')]: vx1 -= TH; char = "*"
        if key in [ord('d'), ord('D')]: vx1 += TH; char = "*"
        if key in [ord('q'), ord('Q')]: break

        # 115-135: Gravity Logic
        if x1 < x0: vx1 += AC
        else: vx1 -= AC
        if y1 < y0: vy1 += AC
        else: vy1 -= AC

        # 75: Apply Velocity and Damping
        x1 += vx1
        y1 += vy1
        vx1 *= DE
        vy1 *= DE

        # 78-81: Screen Wrap
        x1 %= sw
        y1 %= sh

        # Draw Satellite
        try:
            stdscr.addstr(int(y1), int(x1), char)
        except:
            pass # Ignore edge-of-screen drawing errors

        stdscr.refresh()

# Start the curses application
curses.wrapper(main)
