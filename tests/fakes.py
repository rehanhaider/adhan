"""Shared fakes for the tests.

No test may read or write the real user crontab, the real settings.ini or the
speakers. The helpers here give each test a temporary copy of the app, a fake
crontab command, a fake cvlc and a fixed date.

Run the tests with: python3 -m unittest discover tests
"""

import os
import shutil
import subprocess
import sys
import tempfile
from os.path import dirname, abspath, join as pathjoin

ROOT = dirname(dirname(abspath(__file__)))
REAL_SETTINGS = pathjoin(ROOT, 'settings.ini')

# Runs updateAzaanTimers.py as cron does, with two system boundaries replaced:
# the vendored crontab library calls /usr/bin/crontab by its absolute path, so
# it is pointed at the fake crontab command, and the clock gives a fixed date.
DRIVER = r'''
import datetime, os, runpy, sys
script, crontab_dir, croncmd, today, *argv = sys.argv[1:]
# As with 'python3 updateAzaanTimers.py', the folder of the script is on sys.path
sys.path[0] = os.path.dirname(script)
sys.path.insert(0, crontab_dir)
import crontab
crontab.CRONCMD = croncmd
assert crontab.__file__.startswith(crontab_dir), crontab.__file__
year, month, day = map(int, today.split('-'))

class date(datetime.date):
    @classmethod
    def today(cls):
        return cls(year, month, day)

class datetime_(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(year, month, day, 12, 0)

datetime.date = date
datetime.datetime = datetime_
sys.argv = [script] + argv
runpy.run_path(script, run_name='__main__')
'''

FAKE_CRONTAB = '''#!{python}
# Fake crontab command: keeps the user crontab in a file of the test
import shutil, sys
tab = {tab!r}
if '-l' in sys.argv[1:]:
    try:
        with open(tab) as fh:
            sys.stdout.write(fh.read())
    except FileNotFoundError:
        sys.stderr.write('no crontab for user\\n')
        sys.exit(1)
else:
    shutil.copyfile(sys.argv[-1], tab)
'''

FAKE_CVLC = '''#!/bin/sh
# Fake cvlc: records its arguments, one per line, and plays nothing
for arg in "$@"; do echo "$arg"; done > "{log}"
'''


def readBytes(path):
    """The bytes of a file, or None if it does not exist."""
    try:
        with open(path, 'rb') as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def guardRealSettings(test):
    """Fail the test if the real settings.ini changes while it runs."""
    before = readBytes(REAL_SETTINGS)
    test.addCleanup(lambda: test.assertEqual(
        readBytes(REAL_SETTINGS), before,
        'a test changed the real settings.ini'))


def writeExecutable(path, text):
    with open(path, 'w') as fh:
        fh.write(text)
    os.chmod(path, 0o755)


def tempDir(test):
    path = tempfile.mkdtemp(prefix='adhan-test-')
    test.addCleanup(shutil.rmtree, path)
    return path


def fakeCvlc(bin_dir):
    """Put a fake cvlc in bin_dir. Returns the file it records its arguments in."""
    log = pathjoin(bin_dir, 'cvlc.args')
    writeExecutable(pathjoin(bin_dir, 'cvlc'), FAKE_CVLC.format(log=log))
    return log


class App:
    """A temporary copy of the app with a fake user crontab and a fake cvlc."""

    def __init__(self, test, crontab=''):
        self.root = tempDir(test)
        shutil.copy(pathjoin(ROOT, 'updateAzaanTimers.py'), self.root)
        shutil.copytree(pathjoin(ROOT, 'modules'), pathjoin(self.root, 'modules'),
                        ignore=shutil.ignore_patterns('__pycache__'))
        self.settings_path = pathjoin(self.root, 'settings.ini')
        self.tab = pathjoin(self.root, 'user.crontab')
        with open(self.tab, 'w') as fh:
            fh.write(crontab)
        self.croncmd = pathjoin(self.root, 'fake-crontab')
        writeExecutable(self.croncmd,
                        FAKE_CRONTAB.format(python=sys.executable, tab=self.tab))
        self.bin = pathjoin(self.root, 'bin')
        os.mkdir(self.bin)
        fakeCvlc(self.bin)
        self.empty_bin = pathjoin(self.root, 'empty-bin')
        os.mkdir(self.empty_bin)

    def run(self, *argv, today, player_on_path=True):
        """Run updateAzaanTimers.py on the given date in UTC +5:30."""
        env = dict(os.environ,
                   PATH=self.bin if player_on_path else self.empty_bin,
                   TZ='IST-5:30')
        return subprocess.run(
            [sys.executable, '-c', DRIVER,
             pathjoin(self.root, 'updateAzaanTimers.py'),
             pathjoin(ROOT, 'crontab'), self.croncmd, today.isoformat(), *argv],
            cwd=self.root, env=env, capture_output=True, text=True, timeout=60)

    def crontab(self):
        with open(self.tab) as fh:
            return fh.read()

    def settings(self):
        return readBytes(self.settings_path)

    def writeSettings(self, text):
        with open(self.settings_path, 'w') as fh:
            fh.write(text)
