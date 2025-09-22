# Buggy On Mars

Terminal runner written in Python `curses`. Drive, jump, shoot, and survive pits, cones, flies, and multi-level steps.

## Controls
- **↑** Jump
- **Space** Shoot
- **→** Turbo (hold)
- **P** Pause
- **R** Restart
- **Q / Esc** Quit

## Requirements
- Linux or macOS terminal with UTF-8.
- Python 3.8+ (includes `curses` on Linux/macOS).
  - On Windows, use WSL or a Linux VM.

## Quick start (one block of commands)

```bash
# Clone, run
git clone https://github.com/YannickDurindel/BuggyOnMars.git && \
cd BuggyOnMars && \
python3 --version && \
chmod +x moon_buggy_like.py 2>/dev/null || true && \
python3 moon_buggy_like.py
```
Notes
Best at ≥ 80×24 terminal size.

If ▲ or • render poorly, edit CONE_CH or BULLET_CH in the file.

Tweaks (open moon_buggy_like.py)
Difficulty spacing: SPACING_FACTOR

Safe start: SAFE_START_SEC

Max step height: MAX_ELEV

Turbo strength: BOOST_MULTIPLIER

Spawn rates: PIT_RATE, CONE_RATE, ENEMY_RATE, STEP_RATE

Jump feel: JUMP_VEL, GRAVITY, FPS
