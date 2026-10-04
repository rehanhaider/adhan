"""Integration tests for main() with fakes (#16).

main() gets a settings.ini in a temporary folder, an in-memory crontab, a
fixed date and UTC offset, and a PATH with only a fake cvlc. Each test names
the promise (C1-C6 in #16) that it protects.
"""

import datetime
import io
import os
import unittest
from contextlib import redirect_stdout
from os.path import join as pathjoin

import fakes
import updateAzaanTimers as app

CronTab = app.CronTab  # the vendored library, as the app imports it

TODAY = datetime.date(2026, 1, 15)
UTC_OFFSET = 5.5
USER_JOB = '@daily /home/user/backup.sh'
FIRST_RUN = ('--lat', '12.8369', '--lon', '77.4089', '--method', 'Karachi',
             '--azaan-volume', '500')


class MainTest(unittest.TestCase):

    def setUp(self):
        fakes.guardRealSettings(self)
        folder = fakes.tempDir(self)
        self.settings_path = pathjoin(folder, 'settings.ini')
        self.bin = pathjoin(folder, 'bin')
        self.empty_bin = pathjoin(folder, 'empty-bin')
        os.mkdir(self.bin)
        os.mkdir(self.empty_bin)
        fakes.fakeCvlc(self.bin, pathjoin(folder, 'events'))
        self.setPath(self.bin)

    def setPath(self, path):
        # checkPlayer() looks for cvlc on PATH, so PATH holds only the fakes
        self.addCleanup(os.environ.__setitem__, 'PATH', os.environ['PATH'])
        os.environ['PATH'] = path

    def runMain(self, *argv, cron):
        """Run main() with fakes for every input. Returns the exit code."""
        with redirect_stdout(io.StringIO()):
            try:
                app.main(list(argv), self.settings_path, cron, TODAY, UTC_OFFSET)
            except SystemExit as exit:
                return exit.code
        return 0

    def settings(self):
        return fakes.readBytes(self.settings_path)

    def writeSettings(self, data):
        with open(self.settings_path, 'wb') as fh:
            fh.write(data)

    def test_first_run_then_nightly_run_give_the_same_schedule(self):
        """C5: values saved on the first run give the same nightly schedule."""
        first = CronTab(tab='')
        self.assertEqual(self.runMain(*FIRST_RUN, cron=first), 0)
        self.assertIn(' 500 vlc ', first.render())
        nightly = CronTab(tab='')
        self.assertEqual(self.runMain(cron=nightly), 0)
        self.assertEqual(nightly.render(), first.render())

    def test_second_run_replaces_our_jobs_and_keeps_the_users(self):
        """C3: a second run does not add jobs, and other jobs stay."""
        cron = CronTab(tab=USER_JOB + '\n')
        self.assertEqual(self.runMain(*FIRST_RUN, cron=cron), 0)
        self.assertEqual(self.runMain(cron=cron), 0)
        lines = cron.render().splitlines()
        self.assertIn(USER_JOB, lines)
        self.assertEqual(len([line for line in lines if 'playAzaan.sh' in line]), 5)
        self.assertEqual(len([line for line in lines if 'updateAzaanTimers.py' in line]), 1)
        self.assertEqual(len([line for line in lines if 'truncate' in line]), 1)

    def test_bad_input_changes_nothing(self):
        """C4: exit with an error, and the crontab and settings.ini stay."""
        cron = CronTab(tab=USER_JOB + '\n')
        self.assertEqual(self.runMain(*FIRST_RUN, cron=cron), 0)
        good = self.settings().decode()
        cases = [
            ('latitude nan', ('--lat', 'nan'), good),
            ('latitude inf', ('--lat', 'inf'), good),
            ('latitude 91', ('--lat', '91'), good),
            ('longitude 181', ('--lon', '181'), good),
            ('unknown method Foo (#26)', (), good.replace('Karachi', 'Foo')),
            ('unsupported player', (), good.replace('player = vlc', 'player = winamp')),
            ('latitude missing', (), good.replace('lat = 12.8369\n', '')),
            ('longitude missing', (), good.replace('lon = 77.4089\n', '')),
            ('method missing', (), good.replace('method = Karachi\n', '')),
        ]
        for name, argv, text in cases:
            with self.subTest(name):
                self.writeSettings(text.encode())
                crontab = cron.render()
                self.assertNotEqual(self.runMain(*argv, cron=cron), 0)
                self.assertEqual(cron.render(), crontab)
                self.assertEqual(self.settings(), text.encode())

    # Bug: settings.ini is saved before the times are calculated.
    # https://github.com/rehanhaider/adhan/issues/31
    @unittest.expectedFailure
    def test_time_that_cannot_be_calculated_changes_nothing(self):
        """C4: a '-----' time is an error, and the crontab and settings.ini stay."""
        cron = CronTab(tab=USER_JOB + '\n')
        self.assertEqual(self.runMain(*FIRST_RUN, cron=cron), 0)
        settings, crontab = self.settings(), cron.render()
        # In polar night at latitude 80 PrayTimes cannot calculate Maghrib
        self.assertNotEqual(self.runMain('--lat', '80', '--lon', '15', '--method', 'MWL',
                                         cron=cron), 0)
        self.assertEqual(cron.render(), crontab)
        self.assertEqual(self.settings(), settings)

    def test_player_not_on_path_saves_nothing(self):
        """C4: if the player is not installed, exit and save nothing (#20)."""
        self.setPath(self.empty_bin)
        cron = CronTab(tab=USER_JOB + '\n')
        self.assertNotEqual(self.runMain(*FIRST_RUN, cron=cron), 0)
        self.assertEqual(cron.render(), USER_JOB + '\n')
        self.assertIsNone(self.settings())


if __name__ == '__main__':
    unittest.main()
