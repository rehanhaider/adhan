"""Shared fakes for the tests.

No test may read or write the real user crontab, the real settings.ini, the
real adhan.log or the speakers. The helpers here give the tests temporary
folders, a fake crontab command, a fake cvlc and a fixed date.

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
REAL_LOG = pathjoin(ROOT, 'adhan.log')

# So that the tests can import updateAzaanTimers from any folder
sys.path.insert(0, ROOT)

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

FAKE_TIMEDATECTL = '''#!{python}
# Fake timedatectl: records its arguments, one call per line, and prints the
# next answer. After the last answer, it prints the last answer again.
import sys
answers = {answers!r}
with open({calls!r}, 'a') as fh:
    fh.write(' '.join(sys.argv[1:]) + '\\n')
with open({calls!r}) as fh:
    count = len(fh.readlines())
print(answers[min(count, len(answers)) - 1])
'''

FAKE_PLAYER = '''#!/bin/sh
# Fake {name}: records its arguments, one per line, and plays nothing
for arg in "$@"; do echo "$arg"; done > "{log}"
echo {name} >> "{events}"
exit {exit_code}
'''


def readBytes(path):
    """The bytes of a file, or None if it does not exist."""
    try:
        with open(path, 'rb') as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def fileState(path):
    """Values that change when a file is written, or None if it does not exist.

    It does not open the file, so the guard never reads the real settings.
    """
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    return (st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def guardRealSettings(test):
    """Fail the test if the real settings.ini or adhan.log changes while it runs."""
    for path in (REAL_SETTINGS, REAL_LOG):
        before = fileState(path)
        test.addCleanup(lambda path=path, before=before: test.assertEqual(
            fileState(path), before, f'a test changed the real {path}'))


def writeExecutable(path, text):
    with open(path, 'w') as fh:
        fh.write(text)
    os.chmod(path, 0o755)


def tempDir(test):
    path = tempfile.mkdtemp(prefix='adhan-test-')
    test.addCleanup(shutil.rmtree, path)
    return path


def fakePlayer(bin_dir, name, events, exit_code=0):
    """Put a fake player in bin_dir that adds its name to the events file.

    Returns the file that it records its arguments in.
    """
    log = pathjoin(bin_dir, f'{name}.args')
    writeExecutable(pathjoin(bin_dir, name),
                    FAKE_PLAYER.format(name=name, log=log, events=events,
                                       exit_code=exit_code))
    return log


def fakeCvlc(bin_dir, events, exit_code=0):
    return fakePlayer(bin_dir, 'cvlc', events, exit_code)


def fakeTimedatectl(bin_dir, *answers):
    """Put a fake timedatectl in bin_dir that answers NTPSynchronized with
    each answer in turn, for example 'no', 'yes'.

    Returns the file that it records its calls in.
    """
    calls = pathjoin(bin_dir, 'timedatectl.calls')
    writeExecutable(pathjoin(bin_dir, 'timedatectl'),
                    FAKE_TIMEDATECTL.format(python=sys.executable,
                                            answers=list(answers), calls=calls))
    return calls


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
        fakeCvlc(self.bin, pathjoin(self.root, 'events'))

    def run(self, *argv, today, log=None):
        """Run updateAzaanTimers.py on the given date in UTC +5:30.

        With log, stdout and stderr go to that open file, as with
        >> adhan.log 2>&1 in the cron job.
        """
        env = dict(os.environ, PATH=self.bin, TZ='IST-5:30')
        output = (dict(stdout=log, stderr=subprocess.STDOUT) if log
                  else dict(capture_output=True))
        return subprocess.run(
            [sys.executable, '-c', DRIVER,
             pathjoin(self.root, 'updateAzaanTimers.py'),
             pathjoin(ROOT, 'crontab'), self.croncmd, today.isoformat(), *argv],
            cwd=self.root, env=env, text=True, timeout=60, **output)

    def crontab(self):
        with open(self.tab) as fh:
            return fh.read()

    def settings(self):
        return readBytes(self.settings_path)
