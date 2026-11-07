"""Linux process snapshots and identity-safe signalling; no extra dependencies."""
from __future__ import annotations
from dataclasses import dataclass, replace
import os
from pathlib import Path
import pwd
import signal
import time


@dataclass(frozen=True)
class Process:
    pid: int
    start: int
    name: str
    state: str
    uid: int
    user: str
    ticks: int
    memory: int
    cpu: float | None = None

    @property
    def identity(self):
        return self.pid, self.start


@dataclass(frozen=True)
class Snapshot:
    processes: tuple
    cpu: float | None
    used: int
    total: int
    timestamp: float


def read_process(pid, root=Path('/proc')):
    directory = root / str(pid)
    raw = (directory / 'stat').read_text()
    # comm can contain spaces, newlines, and parentheses.
    end = raw.rindex(')')
    name = raw[raw.index('(') + 1:end]
    fields = raw[end + 2:].split()  # starts at stat field 3 (state)
    uid = directory.stat().st_uid
    try:
        user = pwd.getpwuid(uid).pw_name
    except KeyError:
        user = str(uid)
    return Process(int(pid), int(fields[19]), name, fields[0], uid, user,
                   int(fields[11]) + int(fields[12]),
                   max(0, int(fields[21])) * os.sysconf('SC_PAGE_SIZE'))


class Sampler:
    def __init__(self, root=Path('/proc')):
        self.root = root
        self.previous = {}
        self.last_time = None
        self.last_cpu = None
        self.hz = os.sysconf('SC_CLK_TCK')

    def sample(self):
        now = time.monotonic()
        fields = (self.root / 'stat').read_text().splitlines()[0].split()
        if fields[0] != 'cpu':
            raise ValueError('CPU counters are unavailable')
        counters = list(map(int, fields[1:9]))  # excludes guest (already in user/nice)
        total, idle = sum(counters), counters[3] + counters[4]
        cpu = None
        if self.last_cpu and total > self.last_cpu[0]:
            cpu = max(0, min(100, 100 * (1 - (idle - self.last_cpu[1]) / (total - self.last_cpu[0]))))
        memory = {}
        for line in (self.root / 'meminfo').read_text().splitlines():
            key, value = line.split(':', 1)
            memory[key] = int(value.split()[0]) * 1024
        mem_total = memory['MemTotal']
        available = memory['MemAvailable']
        elapsed = now - self.last_time if self.last_time is not None else 0
        processes = []
        for path in self.root.iterdir():
            if not path.name.isdecimal():
                continue
            try:
                process = read_process(int(path.name), self.root)
                old = self.previous.get(process.identity)
                if old is not None and elapsed > 0:
                    process = replace(process, cpu=max(0, 100 * (process.ticks - old) / self.hz / elapsed))
                processes.append(process)
            except (OSError, ValueError, IndexError):
                continue  # exited, inaccessible, or changed during enumeration
        self.previous = {p.identity: p.ticks for p in processes}
        self.last_time, self.last_cpu = now, (total, idle)
        return Snapshot(tuple(processes), cpu, max(0, mem_total - available), mem_total, now)


def filter_processes(processes, query='', sort='cpu'):
    query = query.strip().casefold()
    result = [p for p in processes if query in f'{p.name} {p.pid} {p.user}'.casefold()]
    if sort == 'name':
        return sorted(result, key=lambda p: (p.name.casefold(), p.pid))
    return sorted(result, key=lambda p: (-(p.memory if sort == 'memory' else (p.cpu or 0)), p.pid))


def can_end(process):
    return process.uid == os.getuid() and process.pid not in (1, os.getpid()) and process.state not in ('Z', 'X')


def end_process(process, force=False):
    """Pin a kernel process handle before rechecking identity; never signal by PID."""
    if not can_end(process):
        raise PermissionError('Only your own running processes can be ended.')
    fd = os.pidfd_open(process.pid)
    try:
        current = read_process(process.pid)
        if current.identity != process.identity:
            raise ProcessLookupError('This process has exited. Refresh the list.')
        if not can_end(current):
            raise PermissionError('This process cannot be ended from Task Manager.')
        signal.pidfd_send_signal(fd, signal.SIGKILL if force else signal.SIGTERM)
    finally:
        os.close(fd)


def readable_memory(value):
    return f'{value / 1024 ** 3:.1f} GB' if value >= 1024 ** 3 else f'{value / 1024 ** 2:.1f} MB'
