"""Tests for playAzaan.sh as a command (#16).

Each test runs a copy of playAzaan.sh in a temporary folder with its own hook
folders, so the user's real hooks do not run. PATH holds only the tools the
script needs and a fake cvlc, so the real player is never found and the
speakers stay silent. Each test names the promise (C1-C6 in #16) that it
protects.
"""

import os
import shutil
import subprocess
import unittest
from os.path import join as pathjoin

import fakes

TOOLS = ('bash', 'dirname', 'awk', 'id')


class PlayAzaanTest(unittest.TestCase):

    def setUp(self):
        fakes.guardRealSettings(self)
        self.root = fakes.tempDir(self)
        shutil.copy(pathjoin(fakes.ROOT, 'playAzaan.sh'), self.root)
        for hooks in ('before-hooks.d', 'after-hooks.d'):
            os.mkdir(pathjoin(self.root, hooks))
        self.bin = pathjoin(self.root, 'bin')
        os.mkdir(self.bin)
        for tool in TOOLS:
            os.symlink(shutil.which(tool), pathjoin(self.bin, tool))
        self.events = pathjoin(self.root, 'events')
        self.audio = pathjoin(self.root, 'adhan.mp3')
        open(self.audio, 'w').close()

    def fakeCvlc(self, exit_code=0):
        return fakes.fakeCvlc(self.bin, self.events, exit_code)

    def hook(self, folder, name, body, executable=True):
        path = pathjoin(self.root, folder, name)
        fakes.writeExecutable(path, f'#!/bin/sh\n{body}\n')
        if not executable:
            os.chmod(path, 0o644)

    def run_play(self, audio, *argv):
        return subprocess.run(
            [pathjoin(self.root, 'playAzaan.sh'), audio, *argv],
            env={'PATH': self.bin, 'XDG_RUNTIME_DIR': self.root},
            capture_output=True, text=True, timeout=60)

    def events_seen(self):
        data = fakes.readBytes(self.events)
        return data.decode().split() if data else []

    def test_vlc_plays_the_file_once_at_the_gain_of_the_volume(self):
        """C6: cvlc exits after the file (#4), at the gain of the millibels."""
        args_log = self.fakeCvlc()
        # 10 ** (millibels / 2000), with 4 decimals
        for volume, gain in (('0', '1.0000'), ('1500', '5.6234')):
            with self.subTest(volume=volume):
                result = self.run_play(self.audio, volume, 'vlc')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                with open(args_log) as fh:
                    self.assertEqual(fh.read().split('\n')[:-1],
                                     ['--play-and-exit', '--gain', gain,
                                      self.audio, 'vlc://quit'])

    def test_exit_code_is_the_exit_code_of_the_player(self):
        """C6: a failure of the player shows in the exit code."""
        self.fakeCvlc(exit_code=3)
        self.assertEqual(self.run_play(self.audio, '0', 'vlc').returncode, 3)

    def test_hooks_run_before_and_after_the_player(self):
        """C6: a hook that fails does not stop the adhan, a hook that is not
        executable is skipped."""
        self.fakeCvlc()
        self.hook('before-hooks.d', '10-first', f'echo before-1 >> {self.events}')
        self.hook('before-hooks.d', '20-fails', f'echo before-2 >> {self.events}; exit 1')
        self.hook('before-hooks.d', '30-off', f'echo off >> {self.events}', executable=False)
        self.hook('after-hooks.d', '10-after', f'echo after >> {self.events}')
        result = self.run_play(self.audio, '0', 'vlc')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.events_seen(), ['before-1', 'before-2', 'cvlc', 'after'])

    def test_missing_file_or_player_exits_before_any_hook(self):
        """C6: a missing audio file or player exits 1 and runs no hook."""
        self.hook('before-hooks.d', '10-hook', f'echo before >> {self.events}')
        self.hook('after-hooks.d', '10-hook', f'echo after >> {self.events}')
        cases = [
            ('audio file missing', pathjoin(self.root, 'missing.mp3'), True),
            ('player missing', self.audio, False),
        ]
        for name, audio, player_installed in cases:
            with self.subTest(name):
                cvlc = pathjoin(self.bin, 'cvlc')
                if player_installed:
                    self.fakeCvlc()
                elif os.path.exists(cvlc):
                    os.remove(cvlc)
                self.assertEqual(self.run_play(audio, '0', 'vlc').returncode, 1)
                self.assertEqual(self.events_seen(), [])


if __name__ == '__main__':
    unittest.main()
