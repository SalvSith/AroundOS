"""Run the desktop's 15-minute inactivity timer (also used at login)."""
import fcntl
import os
from pathlib import Path
import shlex
import signal
import subprocess


def main():
    lock = (Path(os.environ['XDG_RUNTIME_DIR']) / 'aroundos-screen-idle.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    command = shlex.join(['/usr/bin/python3', str(Path(__file__).with_name('round_sleep.py'))])
    timer = subprocess.Popen(['swayidle', 'timeout', '900', command])
    def stop(*args):
        timer.terminate()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        timer.wait()
    finally:
        if timer.poll() is None:
            timer.terminate()
            timer.wait()


if __name__ == '__main__':
    main()
