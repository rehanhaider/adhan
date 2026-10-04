"""Integration tests for main() with fakes (#16).

main() gets a settings.ini and an adhan.log in a temporary folder, an
in-memory crontab, a fixed date and UTC offset, and a PATH with only a fake
cvlc. Each test names
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
# The job that cleared the log before #7
OLD_CLEAR_LOG_JOB = '@monthly truncate -s 0 /home/pi/adhan/adhan.log 2>&1 # rpiAdhanClockJob'
FIRST_RUN = ('--lat', '12.8369', '--lon', '77.4089', '--method', 'Karachi',
             '--azaan-volume', '500')


class FakesTestCase(unittest.TestCase):
    """Helpers to run main() with fakes. It has no tests of its own."""

    def setUp(self):
        fakes.guardRealSettings(self)
        folder = fakes.tempDir(self)
        self.settings_path = pathjoin(folder, 'settings.ini')
        self.log_path = pathjoin(folder, 'adhan.log')
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

    def runMain(self, *argv, cron, sync_timeout=0):
        """Run main() with fakes for every input. Returns the exit code.

        The output of main() for adhan.log is in self.output.
        """
        output = io.StringIO()
        self.addCleanup(output.close)
        self.output = output
        with redirect_stdout(output):
            try:
                app.main(list(argv), self.settings_path, cron, TODAY, UTC_OFFSET,
                         self.log_path, sync_timeout)
            except SystemExit as exit:
                return exit.code
        return 0

    def settings(self):
        return fakes.readBytes(self.settings_path)

    def writeSettings(self, data):
        with open(self.settings_path, 'wb') as fh:
            fh.write(data)


class MainTest(FakesTestCase):

    def test_first_run_then_nightly_run_give_the_same_schedule(self):
        """C5: values saved on the first run give the same nightly schedule."""
        first = CronTab(tab='')
        self.assertEqual(self.runMain(*FIRST_RUN, cron=first), 0)
        self.assertIn(' 500 vlc ', first.render())
        nightly = CronTab(tab='')
        self.assertEqual(self.runMain(cron=nightly), 0)
        self.assertEqual(nightly.render(), first.render())
        # An offset in settings.ini moves its prayer only (#12)
        self.writeSettings(self.settings().replace(b'\nfajr = 0\n', b'\nfajr = 5\n'))
        offset = CronTab(tab='')
        self.assertEqual(self.runMain(cron=offset), 0)
        self.assertEqual(offset.render(), first.render().replace(
            '31 5 * * * ', '36 5 * * * '))
        self.assertIn('Fajr:    05:36 hrs (offset +5 minutes)', self.output.getvalue())
        # An offset on the command line is saved for the nightly update
        self.assertEqual(self.runMain('--fajr-offset', '0', cron=offset), 0)
        self.assertEqual(offset.render(), first.render())
        self.assertIn(b'\nfajr = 0\n', self.settings())
        # A prayer that is off in settings.ini has no job (#13)
        self.writeSettings(self.settings().replace(b'\nfajr = true\n', b'\nfajr = false\n'))
        off = CronTab(tab='')
        self.assertEqual(self.runMain(cron=off), 0)
        self.assertEqual(off.render(), ''.join(
            line for line in first.render().splitlines(keepends=True)
            if not line.startswith('31 5 * * * ')))
        self.assertIn('Fajr:    05:31 hrs (not scheduled)', self.output.getvalue())

    def test_second_run_replaces_our_jobs_and_keeps_the_users(self):
        """C3: a second run does not add jobs, and other jobs stay. The old
        job that cleared the log goes (#7). There is one update at 03:15 and
        one after a reboot (#15)."""
        cron = CronTab(tab=f'{USER_JOB}\n{OLD_CLEAR_LOG_JOB}\n')
        self.assertEqual(self.runMain(*FIRST_RUN, cron=cron), 0)
        self.assertEqual(self.runMain(cron=cron), 0)
        lines = cron.render().splitlines()
        self.assertIn(USER_JOB, lines)
        self.assertEqual(len([line for line in lines if 'playAzaan.sh' in line]), 5)
        updates = [line for line in lines if 'updateAzaanTimers.py' in line]
        self.assertEqual([line.split()[0] for line in updates], ['15', '@reboot'])
        for line in updates:
            self.assertTrue(line.endswith(' # rpiAdhanClockJob'), line)
        self.assertEqual(len([line for line in lines if 'truncate' in line]), 0)

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
            ('offset not a whole number (#12)', (),
             good.replace('\nfajr = 0\n', '\nfajr = 5.5\n')),
            ('offset of an unknown prayer (#12)', (),
             good.replace('\nfajr = 0\n', '\nfjar = 5\n')),
            ('offset not a whole number on the command line (#12)',
             ('--fajr-offset', '5.5'), good),
            ('on or off is maybe (#13)', (),
             good.replace('\nfajr = true\n', '\nfajr = maybe\n')),
            ('on or off of an unknown prayer (#13)', (),
             good.replace('\nfajr = true\n', '\nfjar = false\n')),
        ]
        for name, argv, text in cases:
            with self.subTest(name):
                self.writeSettings(text.encode())
                crontab = cron.render()
                self.assertNotEqual(self.runMain(*argv, cron=cron), 0)
                self.assertEqual(cron.render(), crontab)
                self.assertEqual(self.settings(), text.encode())

    def test_all_prayers_off_is_allowed_and_logged(self):
        """C2, C3: with all five prayers off, no adhan job stays, the jobs that
        renew the schedule stay, and the log says why (#13)."""
        cron = CronTab(tab=USER_JOB + '\n')
        self.assertEqual(self.runMain(*FIRST_RUN, *[f'--no-play-{name}' for name in app.PRAYERS],
                                      cron=cron), 0)
        lines = cron.render().splitlines()
        self.assertEqual([line for line in lines if 'playAzaan.sh' in line], [])
        self.assertEqual(len([line for line in lines if 'updateAzaanTimers.py' in line]), 2)
        self.assertIn('All five prayers are off', self.output.getvalue())
        # The nightly update keeps them off
        self.assertEqual(self.runMain(cron=cron), 0)
        self.assertEqual([line for line in cron.render().splitlines() if 'playAzaan.sh' in line], [])

    def test_player_not_on_path_saves_nothing(self):
        """C4: if the player is not installed, exit and save nothing (#20)."""
        self.setPath(self.empty_bin)
        cron = CronTab(tab=USER_JOB + '\n')
        self.assertNotEqual(self.runMain(*FIRST_RUN, cron=cron), 0)
        self.assertEqual(cron.render(), USER_JOB + '\n')
        self.assertIsNone(self.settings())


class TimeThatCannotBeCalculatedTest(FakesTestCase):
    """C4: a '-----' time is an error, and the crontab and settings.ini stay.

    setUp does a good first run, then a run at latitude 80 in polar night,
    where PrayTimes cannot calculate Maghrib.
    """

    def setUp(self):
        super().setUp()
        self.cron = CronTab(tab=USER_JOB + '\n')
        self.assertEqual(self.runMain(*FIRST_RUN, cron=self.cron), 0)
        self.settings_before = self.settings()
        self.crontab_before = self.cron.render()
        self.exit_code = self.runMain('--lat', '80', '--lon', '15', '--method', 'MWL',
                                      cron=self.cron)

    def test_exits_with_an_error_and_keeps_the_crontab(self):
        """C4: the run fails, and yesterday's jobs stay."""
        self.assertNotEqual(self.exit_code, 0)
        self.assertEqual(self.cron.render(), self.crontab_before)

    def test_keeps_settings_ini(self):
        """C4: the run does not save the location it could not use (#31)."""
        self.assertEqual(self.settings(), self.settings_before)


class TimeSyncTest(FakesTestCase):
    """The update after a reboot waits until the clock is synchronized (#15).

    A Pi has no clock battery. Until NTP synchronizes the clock, the date can
    be days too early, and the times for that date are wrong.
    """

    SYNC_ARGS = ['show -p NTPSynchronized --value']

    def setUp(self):
        super().setUp()
        self.cron = CronTab(tab=USER_JOB + '\n')
        self.assertEqual(self.runMain(*FIRST_RUN, cron=self.cron), 0)
        self.settings_before = self.settings()
        self.crontab_before = self.cron.render()

    def calls(self, path):
        data = fakes.readBytes(path)
        return data.decode().splitlines() if data else []

    def test_synchronized_clock_updates_the_times(self):
        """C3: when the clock is synchronized, the update after a reboot
        gives the same schedule as the nightly update."""
        calls = fakes.fakeTimedatectl(self.bin, 'yes')
        cron = CronTab(tab=USER_JOB + '\n')
        self.assertEqual(self.runMain('--wait-for-time-sync', cron=cron), 0)
        self.assertEqual(self.calls(calls), self.SYNC_ARGS)
        self.assertEqual(cron.render(), self.crontab_before)

    def test_waits_until_the_clock_is_synchronized(self):
        """C3: the wait asks again until the clock is synchronized."""
        calls = fakes.fakeTimedatectl(self.bin, 'no', 'no', 'yes')
        with redirect_stdout(io.StringIO()):
            self.assertTrue(app.waitForTimeSync(60, interval=0.01))
        self.assertEqual(self.calls(calls), self.SYNC_ARGS * 3)

    def test_clock_that_does_not_synchronize_changes_nothing(self):
        """C4: if the clock is not synchronized before the timeout, or
        timedatectl is not there, write it to the log and exit. The crontab
        and settings.ini stay."""
        cases = [
            ('not synchronized', lambda: fakes.fakeTimedatectl(self.bin, 'no')),
            ('timedatectl not found', lambda: self.setPath(self.empty_bin)),
        ]
        for name, make in cases:
            with self.subTest(name):
                make()
                self.assertNotEqual(self.runMain('--wait-for-time-sync', cron=self.cron), 0)
                self.assertIn('The prayer times were not updated', self.output.getvalue())
                self.assertEqual(self.cron.render(), self.crontab_before)
                self.assertEqual(self.settings(), self.settings_before)

    def test_nightly_update_does_not_wait(self):
        """C3: the 03:15 update and a first run do not ask for the clock."""
        calls = fakes.fakeTimedatectl(self.bin, 'no')
        self.assertEqual(self.runMain(cron=self.cron), 0)
        self.assertEqual(self.runMain(*FIRST_RUN, cron=self.cron), 0)
        self.assertEqual(self.calls(calls), [])


class LogTest(FakesTestCase):
    """C3: the update keeps the last 30 days of adhan.log (#7)."""

    OLD = '2025-12-01 03:15:00 older than 30 days\n'
    NEW = '2026-01-14 03:15:00 yesterday\n'

    def writeLog(self, text):
        with open(self.log_path, 'w') as fh:
            fh.write(text)

    def readLog(self):
        with open(self.log_path) as fh:
            return fh.read()

    def test_prune_keeps_text_that_is_written_after_it(self):
        """C3: the nightly job writes to adhan.log with >> (O_APPEND). The
        prune changes the same file, so the text after it is at the end."""
        self.writeLog(self.OLD + self.NEW)
        fd = os.open(self.log_path, os.O_WRONLY | os.O_APPEND)
        self.addCleanup(os.close, fd)
        app.pruneLogFile(self.log_path, TODAY)
        os.write(fd, b'after the prune\n')
        self.assertEqual(self.readLog(), self.NEW + 'after the prune\n')

    def test_update_prunes_the_log(self):
        """C3: the update deletes the old lines, then does the schedule."""
        self.writeLog(self.OLD + self.NEW)
        cron = CronTab(tab='')
        self.assertEqual(self.runMain(*FIRST_RUN, cron=cron), 0)
        self.assertEqual(self.readLog(), self.NEW)
        self.assertEqual(len([line for line in cron.render().splitlines()
                              if 'playAzaan.sh' in line]), 5)

    def test_a_log_with_a_problem_does_not_stop_the_update(self):
        """C3: a log that is missing or cannot be read does not stop the
        schedule. Cron can still add to a log that it cannot read (>> needs
        only write), so the update runs and must not fail on the prune."""
        def missing():
            pass

        def write_only():
            self.writeLog(self.OLD + self.NEW)
            os.chmod(self.log_path, 0o200)
            if os.access(self.log_path, os.R_OK):
                self.skipTest('root can read a write-only file')

        for name, make in (('missing', missing), ('cannot be read', write_only)):
            with self.subTest(name):
                make()
                cron = CronTab(tab='')
                self.assertEqual(self.runMain(*FIRST_RUN, cron=cron), 0)
                self.assertEqual(len([line for line in cron.render().splitlines()
                                      if 'playAzaan.sh' in line]), 5)


if __name__ == '__main__':
    unittest.main()
