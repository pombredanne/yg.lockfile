import os
import subprocess
import itertools
import time
import sys
import textwrap
import datetime

import pytest
import tempora.timing

from yg.lockfile import FileLock, FileLockTimeout


def test_FileLock_basic(tmpdir):
    filename = str(tmpdir / 'lock')
    l1 = FileLock(filename)
    l2 = FileLock(filename, timeout=0.2)
    assert not l1.is_locked()
    l1.acquire()
    assert l1.is_locked()
    l1.release()
    assert not l1.is_locked()
    with l1:
        assert os.path.isfile(filename)
        with pytest.raises(FileLockTimeout):
            l2.acquire()
    assert not l1.is_locked()
    l2.acquire()
    assert l2.is_locked()
    l2.release()


def lines(stream):
    """
    Buffer subprocess output byte-by-byte and assemble into lines.
    """
    buf = b''
    while True:
        dat = stream.read(1)
        if dat:
            buf += dat
            if dat == b'\n':
                yield buf
                buf = b''
        if not dat and buf:
            yield buf
        if not dat:
            break


def decoded_lines(stream):
    return (line.decode('utf-8-sig') for line in lines(stream))


def test_FileLock_process_killed(tmpdir):
    """
    If a subprocess fails to release the lock, it should be released
    and available for another process to take it.
    """
    filename = str(tmpdir / 'lock')
    script = textwrap.dedent("""
        from __future__ import print_function
        from yg.lockfile import FileLock
        import time
        l = FileLock({filename!r})
        l.acquire()
        print("acquired", l.lockfile)
        [time.sleep(1) for x in range(10)]
        """).format(**locals())
    script_lines = script.strip().split('\n')
    script_cmd = '; '.join(script_lines)
    cmd = [sys.executable, '-u', '-c', script_cmd]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    lines = decoded_lines(proc.stdout)
    out = itertools.takewhile(lambda line: 'acquired' not in line, lines)
    tuple(out)  # wait for 'acquired' to be printed by subprocess

    lock = FileLock(filename, timeout=0.2)
    with pytest.raises(FileLockTimeout):
        lock.acquire()
    proc.kill()
    time.sleep(.5)
    lock.acquire()
    lock.release()


def test_FileLock_timeout_immediate(tmpdir):
    """
    FileLock with timeout of 0 should not block and raise
    a timeout immediately.
    """
    filename = str(tmpdir / 'lock')
    lock = FileLock(filename, timeout=0)
    held = FileLock(filename)
    held.acquire()
    with tempora.timing.Stopwatch() as watch:
        with pytest.raises(FileLockTimeout):
            lock.acquire()
    assert watch.elapsed < datetime.timedelta(milliseconds=10)
