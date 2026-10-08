"""Integration tests for main() with fakes (#16).

main() gets an adhan.toml and an adhan.log in a temporary folder, an
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
# The [prayers.fajr] table that the first run writes
FAJR = ('[prayers.fajr]\nfile = "Adhan-fajr.mp3"\nvolume = 0\noffset_minutes = 0\n'
        'enabled = true\n')
# The rule of the README for Surah Baqarah, and a rule after Maghrib (#43)
SURAH_BAQARAH = ('[[rule]]\nname = "Surah Baqarah"\ndays = ["fri"]\nat = "07:00"\n'
                 'file = "002-surah-baqarah-mishary.mp3"\nvolume = -100\n')
DUA = '[[rule]]\nname = "Evening dua"\nat = "maghrib + 10min"\nfile = "Adhan-Makkah1-Dua.mp3"\n'


class FakesTestCase(unittest.TestCase):
    """Helpers to run main() with fakes. It has no tests of its own."""

    def setUp(self):
        fakes.guardRealSettings(self)
        folder = fakes.tempDir(self)
        self.settings_path = pathjoin(folder, 'adhan.toml')
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

    def editSettings(self, old, new):
        """Change the text old in adhan.toml to new, as a user does by hand."""
        text = self.settings().decode()
        self.assertIn(old, text)
        self.writeSettings(text.replace(old, new, 1).encode())


class MainTest(FakesTestCase):

    def test_first_run_then_nightly_run_give_the_same_schedule(self):
        """C5: values saved on the first run give the same nightly schedule."""
        first = CronTab(tab='')
        self.assertEqual(self.runMain(*FIRST_RUN, cron=first), 0)
        self.assertIn(' 500 vlc ', first.render())
        self.assertIn(FAJR.encode(), self.settings())
        nightly = CronTab(tab='')
        self.assertEqual(self.runMain(cron=nightly), 0)
        self.assertEqual(nightly.render(), first.render())
        # An offset in adhan.toml moves its prayer only (#12)
        self.editSettings(FAJR, FAJR.replace('offset_minutes = 0', 'offset_minutes = 5'))
        offset = CronTab(tab='')
        self.assertEqual(self.runMain(cron=offset), 0)
        self.assertEqual(offset.render(), first.render().replace(
            '31 5 * * * ', '36 5 * * * '))
        self.assertIn('Fajr:    05:36 hrs (offset +5 minutes)', self.output.getvalue())
        # An offset on the command line is saved for the nightly update
        self.assertEqual(self.runMain('--fajr-offset', '0', cron=offset), 0)
        self.assertEqual(offset.render(), first.render())
        self.assertIn(FAJR.encode(), self.settings())
        # A prayer that is off in adhan.toml has no job (#13)
        self.editSettings(FAJR, FAJR.replace('enabled = true', 'enabled = false'))
        off = CronTab(tab='')
        self.assertEqual(self.runMain(cron=off), 0)
        self.assertEqual(off.render(), ''.join(
            line for line in first.render().splitlines(keepends=True)
            if not line.startswith('31 5 * * * ')))
        self.assertIn('Fajr:    05:31 hrs (not scheduled)', self.output.getvalue())
        # The audio file of a prayer in adhan.toml changes its job only (#10)
        self.editSettings(FAJR.replace('enabled = true', 'enabled = false'), FAJR)
        self.editSettings('[prayers.isha]\n', '[prayers.isha]\nfile = "Adhan-Madinah.mp3"\n')
        audio = CronTab(tab='')
        self.assertEqual(self.runMain(cron=audio), 0)
        self.assertEqual(audio.render(), ''.join(
            line.replace('Adhan-Makkah1.mp3', 'Adhan-Madinah.mp3') if line.startswith('28 19 ')
            else line for line in first.render().splitlines(keepends=True)))
        self.assertIn(b'[prayers.isha]\nfile = "Adhan-Madinah.mp3"\n', self.settings())
        # Hanafi in adhan.toml moves Asr only, and the log shows it (#11)
        self.editSettings('asr = "Standard"', 'asr = "hanafi"')
        hanafi = CronTab(tab='')
        self.assertEqual(self.runMain(cron=hanafi), 0)
        self.assertEqual(hanafi.render(), audio.render().replace('47 15 * * * ', '37 16 * * * '))
        self.assertIn('Asr school: Hanafi', self.output.getvalue())
        self.assertIn(b'asr = "Hanafi"', self.settings())
        # A lead-in in adhan.toml goes to each adhan job, and the log shows it (#14)
        self.editSettings('leadin_seconds = 0', 'leadin_seconds = 2')
        leadin = CronTab(tab='')
        self.assertEqual(self.runMain(cron=leadin), 0)
        self.assertEqual(leadin.render(), hanafi.render().replace(' vlc >> ', ' vlc 2 >> '))
        self.assertIn('Lead-in:    2 seconds', self.output.getvalue())
        # The volume of a prayer in adhan.toml changes its job only
        self.editSettings('[prayers.dhuhr]\n', '[prayers.dhuhr]\nvolume = -300\n')
        volume = CronTab(tab='')
        self.assertEqual(self.runMain(cron=volume), 0)
        self.assertEqual(volume.render(), ''.join(
            line.replace(' 500 vlc ', ' -300 vlc ') if line.startswith('30 12 ')
            else line for line in leadin.render().splitlines(keepends=True)))
        # A rule in adhan.toml adds one job on its days, with the lead-in, and
        # the nightly update keeps it (#43)
        self.writeSettings(self.settings() + b'\n' + SURAH_BAQARAH.encode())
        rule = CronTab(tab='')
        self.assertEqual(self.runMain(cron=rule), 0)
        friday = [line for line in rule.render().splitlines() if line.startswith('0 7 * * 5 ')]
        self.assertEqual(len(friday), 1)
        self.assertIn('/media/002-surah-baqarah-mishary.mp3 -100 vlc 2 >> ', friday[0])
        self.assertEqual(rule.render().replace(friday[0] + '\n', ''), volume.render())
        self.assertIn('Surah Baqarah: 07:00, on fri', self.output.getvalue())
        self.assertIn((SURAH_BAQARAH + 'enabled = true\n').encode(), self.settings())
        nightly = CronTab(tab='')
        self.assertEqual(self.runMain(cron=nightly), 0)
        self.assertEqual(nightly.render(), rule.render())

    def test_second_run_replaces_our_jobs_and_keeps_the_users(self):
        """C3: a second run does not add jobs, and other jobs stay. The old
        job that cleared the log goes (#7). There is one update at 03:15 and
        one after a reboot (#15)."""
        cron = CronTab(tab=f'{USER_JOB}\n{OLD_CLEAR_LOG_JOB}\n')
        self.assertEqual(self.runMain(*FIRST_RUN, cron=cron), 0)
        # With two rules, each run has 5 adhan jobs and 2 rule jobs (#43)
        self.writeSettings(self.settings() + f'\n{SURAH_BAQARAH}\n{DUA}'.encode())
        self.assertEqual(self.runMain(cron=cron), 0)
        self.assertEqual(self.runMain(cron=cron), 0)
        lines = cron.render().splitlines()
        self.assertIn(USER_JOB, lines)
        self.assertEqual(len([line for line in lines if 'playAzaan.sh' in line]), 7)
        self.assertEqual(len([line for line in lines if line.startswith('0 7 * * 5 ')]), 1)
        self.assertEqual(len([line for line in lines if line.startswith('23 18 * * * ')]), 1)
        updates = [line for line in lines if 'updateAzaanTimers.py' in line]
        self.assertEqual([line.split()[0] for line in updates], ['15', '@reboot'])
        for line in updates:
            self.assertTrue(line.endswith(' # rpiAdhanClockJob'), line)
        self.assertEqual(len([line for line in lines if 'truncate' in line]), 0)

    def test_bad_input_changes_nothing(self):
        """C4: exit with an error, and the crontab and adhan.toml stay."""
        cron = CronTab(tab=USER_JOB + '\n')
        self.assertEqual(self.runMain(*FIRST_RUN, cron=cron), 0)
        good = self.settings().decode()

        def fajr(old, new):
            return good.replace(FAJR, FAJR.replace(old, new))

        def rule(old, new):
            # good with the rule DUA, changed
            self.assertIn(old, DUA)
            return good + '\n' + DUA.replace(old, new)

        cases = [
            ('latitude nan', ('--lat', 'nan'), good),
            ('latitude inf', ('--lat', 'inf'), good),
            ('latitude 91', ('--lat', '91'), good),
            ('longitude 181', ('--lon', '181'), good),
            ('stored latitude nan', (), good.replace('lat = 12.8369', 'lat = nan')),
            ('unknown method Foo (#26)', (), good.replace('"Karachi"', '"Foo"')),
            ('unsupported player', (), good.replace('player = "vlc"', 'player = "winamp"')),
            ('latitude missing', (), good.replace('lat = 12.8369\n', '')),
            ('longitude missing', (), good.replace('lon = 77.4089\n', '')),
            ('method missing', (), good.replace('method = "Karachi"\n', '')),
            ('not TOML, a text with no quotes', (),
             good.replace('method = "Karachi"', 'method = Karachi')),
            ('not TOML, the old settings.ini', (), '[DEFAULT]\nlat = 12.8369\n'),
            ('not TOML, a table two times', (), good + '[location]\n'),
            ('not UTF-8', (), good.replace('"Karachi"', '"Karachi\udcff"')),
            ('unknown table', (), good + '[FRIDAY]\nplaysurahbaqarah = true\n'),
            ('unknown key, a typo', (), good.replace('lat = 12.8369', 'latt = 12.8369')),
            ('latitude as text', (), good.replace('lat = 12.8369', 'lat = "12.8369"')),
            ('volume not a whole number', (), good.replace('volume = 500', 'volume = 500.0')),
            ('the old [surah_baqarah] table (#43)', (),
             good + '\n[surah_baqarah]\nenabled = true\nvolume = 0\n'),
            ('[rule] as one table, not [[rule]] (#43)', (), rule('[[rule]]', '[rule]')),
            ('unknown key in a rule (#43)', (), rule('at =', 'time =')),
            ('a rule without at (#43)', (), rule('at = "maghrib + 10min"\n', '')),
            ('volume of a rule as text (#43)', (), rule('name =', 'volume = "0"\nname =')),
            ('days as text, not a list (#43)', (), rule('name =', 'days = "fri"\nname =')),
            ('at not a time (#43)', (), rule('"maghrib + 10min"', '"7 am"')),
            ('at an unknown prayer (#43)', (), rule('"maghrib + 10min"', '"magrib + 10min"')),
            ('an unknown day (#43)', (), rule('name =', 'days = ["friday"]\nname =')),
            ('two rules with the same name (#43)', (), rule('', '') + '\n' + DUA),
            ('the file of a rule not in media/ (#43)', (),
             rule('"Adhan-Makkah1-Dua.mp3"', '"dua.mp3"')),
            ('a rule after 23:59 (#43)', (), rule('"maghrib + 10min"', '"maghrib + 400min"')),
            ('a rule before 00:00 (#43)', (), rule('"maghrib + 10min"', '"fajr - 332min"')),
            ('offset not a whole number (#12)', (),
             fajr('offset_minutes = 0', 'offset_minutes = 5.5')),
            ('offset of an unknown prayer (#12)', (),
             good.replace('[prayers.fajr]', '[prayers.fjar]')),
            ('offset not a whole number on the command line (#12)',
             ('--fajr-offset', '5.5'), good),
            ('on or off as text (#13)', (), fajr('enabled = true', 'enabled = "true"')),
            ('unknown asr Maliki (#11)', (),
             good.replace('asr = "Standard"', 'asr = "Maliki"')),
            ('unknown asr on the command line (#11)', ('--asr', 'Maliki'), good),
            ('lead-in not a whole number (#14)', (),
             good.replace('leadin_seconds = 0', 'leadin_seconds = 1.5')),
            ('lead-in more than 10 seconds on the command line (#14)',
             ('--leadin-seconds', '11'), good),
            ('audio file not in media/ (#10)', (),
             fajr('"Adhan-fajr.mp3"', '"Adhan-fjar.mp3"')),
            ('audio file not in media/, on the command line (#10)',
             ('--audio', 'Adhan-Makka1.mp3'), good),
            ('audio file at an absolute path that is not there (#10)',
             ('--isha-audio', '/no/such/adhan.mp3'), good),
        ]
        for name, argv, text in cases:
            with self.subTest(name):
                data = text.encode(errors='surrogateescape')
                self.writeSettings(data)
                crontab = cron.render()
                self.assertNotEqual(self.runMain(*argv, cron=cron), 0)
                self.assertEqual(cron.render(), crontab)
                self.assertEqual(self.settings(), data)

    def test_a_missing_rule_file_stops_the_update(self):
        """C4: the file of a rule that is on must be there, as an adhan file
        must be (#10, #43), in media/ or at an absolute path. The file of a
        rule that is off is not checked."""
        rule = app.Rule('Surah Baqarah', app.At(None, 7 * 60), ('fri',),
                        '002-surah-baqarah-mishary.mp3', None, True)
        settings = app.Settings(lat=12.8369, lon=77.4089, method='Karachi', asr='Standard',
                                volume={'default': 0, 'fajr': 0}, player='vlc', leadin=0,
                                offsets=dict.fromkeys(app.PRAYERS, 0),
                                enabled=dict.fromkeys(app.PRAYERS, False),
                                audio={'default': 'Adhan-Makkah1.mp3'}, rules=(rule,))
        root = fakes.tempDir(self)
        os.mkdir(pathjoin(root, 'media'))
        with self.assertRaises(app.ConfigError) as error:
            app.checkAudio(settings, root)
        self.assertIn("the rule 'Surah Baqarah'", str(error.exception))
        app.checkAudio(settings._replace(rules=(rule._replace(enabled=False),)), root)
        open(pathjoin(root, 'media', '002-surah-baqarah-mishary.mp3'), 'w').close()
        app.checkAudio(settings, root)
        own = pathjoin(root, 'own.mp3')
        with self.assertRaises(app.ConfigError):
            app.checkAudio(settings._replace(rules=(rule._replace(file=own),)), root)
        open(own, 'w').close()
        app.checkAudio(settings._replace(rules=(rule._replace(file=own),)), root)

    def test_the_old_surah_baqarah_table_says_which_rule_to_add(self):
        """C4: the live adhan.toml of before #43 has [surah_baqarah] on.
        The update stops, the log gives the rule, and with that rule in place
        of the table the update gives the Friday job of before #43."""
        cron = CronTab(tab=USER_JOB + '\n')
        self.assertEqual(self.runMain(*FIRST_RUN, cron=cron), 0)
        good = self.settings().decode()
        self.writeSettings((good + '\n[surah_baqarah]\nenabled = true\nvolume = 0\n').encode())
        before = cron.render()
        self.assertNotEqual(self.runMain(cron=cron), 0)
        self.assertEqual(cron.render(), before)
        output = self.output.getvalue()
        self.assertIn('replace the [surah_baqarah] table with this rule', output)
        rule = ('[[rule]]\nname = "Surah Baqarah"\ndays = ["fri"]\nat = "07:00"\n'
                'file = "002-surah-baqarah-mishary.mp3"\nvolume = 0\n')
        self.assertIn(''.join(f' {line}\n' for line in rule.splitlines()),
                      ''.join(line[19:] + '\n' for line in output.splitlines()))
        self.writeSettings((good + '\n' + rule).encode())
        self.assertEqual(self.runMain(cron=cron), 0)
        friday = [line for line in cron.render().splitlines() if line.startswith('0 7 * * 5 ')]
        self.assertEqual(len(friday), 1)
        self.assertTrue(friday[0].endswith(
            '/media/002-surah-baqarah-mishary.mp3 0 vlc >> '
            f'{app.root_dir}/adhan.log 2>&1 # rpiAdhanClockJob'), friday[0])

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

    def test_log_lists_the_jobs_under_a_correct_heading(self):
        """C2: the log shows each job that the run added, under the heading
        'Cron jobs scheduled' (#8)."""
        cron = CronTab(tab='')
        self.assertEqual(self.runMain(*FIRST_RUN, cron=cron), 0)
        output = self.output.getvalue()
        self.assertIn(' Cron jobs scheduled\n', output)
        self.assertNotIn('Crob', output)
        for job in cron.render().splitlines():
            self.assertIn(job, output)

    def test_audio_file_at_an_absolute_path_is_played(self):
        """C2: an absolute path to a file that is there is played as it is,
        and the file of a prayer that is off is not checked (#10)."""
        own = pathjoin(self.bin, 'own adhan.mp3')
        open(own, 'w').close()
        cron = CronTab(tab='')
        self.assertEqual(self.runMain(*FIRST_RUN, '--fajr-audio', own,
                                      '--isha-audio', 'Missing.mp3', '--no-play-isha',
                                      cron=cron), 0)
        fajr = [line for line in cron.render().splitlines() if line.startswith('31 5 ')]
        self.assertEqual(len(fajr), 1)
        self.assertIn(f"playAzaan.sh '{own}' 0 vlc ", fajr[0])

    def test_player_not_on_path_saves_nothing(self):
        """C4: if the player is not installed, exit and save nothing (#20)."""
        self.setPath(self.empty_bin)
        cron = CronTab(tab=USER_JOB + '\n')
        self.assertNotEqual(self.runMain(*FIRST_RUN, cron=cron), 0)
        self.assertEqual(cron.render(), USER_JOB + '\n')
        self.assertIsNone(self.settings())


class TimeThatCannotBeCalculatedTest(FakesTestCase):
    """C4: a '-----' time is an error, and the crontab and adhan.toml stay.

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

    def test_keeps_adhan_toml(self):
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
        and adhan.toml stay."""
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
