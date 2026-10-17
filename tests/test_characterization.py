"""Characterization test: a full run of updateAzaanTimers.py as a command.

It runs the script as cron does, in a temporary copy of the app, with the
default values of main(): the command line, the adhan.toml next to the
script, the user crontab and the system timezone. The expected crontab was
recorded from the script before the refactor into a core and a shell (#16).
#7 removed the job that cleared the log every month. #15 added the update
after a reboot. #42 moved the settings from settings.ini to adhan.toml. #43
removed the [surah_baqarah] table, which is a rule now. #29 changed python3
in the update jobs to the Python of the virtual environment. The
tests in test_main.py cover the other cases through main() with fakes.
"""

import datetime
import unittest

import fakes

TODAY = datetime.date(2026, 1, 15)
USER_JOB = '@daily /home/user/backup.sh\n'
FIRST_RUN = ('--lat', '12.8369', '--lon', '77.4089', '--method', 'Karachi',
             '--azaan-volume', '500', '--fajr-azaan-volume', '-500')

# Bengaluru with Karachi on 2026-01-15 in UTC +5:30, as the script gave it
PRAYER_TIMES = (('5', '31'), ('12', '30'), ('15', '47'), ('18', '13'), ('19', '28'))

# The adhan.toml that the first run writes. Before #42 the settings were in
# settings.ini, with the same values.
FIRST_RUN_SETTINGS = '''# The settings of the adhan clock. See README.md.
# updateAzaanTimers.py writes this file again on each run, so comments are lost.

[location]
lat = 12.8369
lon = 77.4089
method = "Karachi"
asr = "Standard"

[audio]
player = "vlc"
leadin_seconds = 0
volume = 500
file = "Adhan-Makkah1.mp3"

[prayers.fajr]
file = "Adhan-fajr.mp3"
volume = -500
offset_minutes = 0
enabled = true

[prayers.dhuhr]
offset_minutes = 0
enabled = true

[prayers.asr]
offset_minutes = 0
enabled = true

[prayers.maghrib]
offset_minutes = 0
enabled = true

[prayers.isha]
offset_minutes = 0
enabled = true
'''

# A settings.ini of before #42. The app does not read it.
OLD_SETTINGS_INI = '''[DEFAULT]
lat = 12.8369
lon = 77.4089
method = Karachi
'''


def expectedCrontab(root, fajr_volume, volume):
    play = f'{root}/playAzaan.sh {root}/media'
    log = f'>> {root}/adhan.log 2>&1 # rpiAdhanClockJob'
    lines = [USER_JOB]
    for (hour, minute), audio, vol in zip(
            PRAYER_TIMES, ['Adhan-fajr.mp3'] + ['Adhan-Makkah1.mp3'] * 4,
            [fajr_volume] + [volume] * 4):
        lines.append(f'{minute} {hour} * * * {play}/{audio} {vol} vlc {log}')
    # The Python of the virtual environment that uv makes, not python3 (#29)
    python = f'{root}/.venv/bin/python'
    lines.append(f'15 3 * * * {python} {root}/updateAzaanTimers.py {log}')
    lines.append(f'@reboot {python} {root}/updateAzaanTimers.py --wait-for-time-sync {log}')
    return '\n'.join(lines) + '\n'


class FullRunTest(unittest.TestCase):

    def setUp(self):
        fakes.guardRealSettings(self)
        self.app = fakes.App(self, crontab=USER_JOB)

    def assertRunOk(self, *argv):
        result = self.app.run(*argv, today=TODAY)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # Each line for adhan.log starts with the time of the run (#7)
        for line in result.stdout.splitlines():
            self.assertTrue(line.startswith('2026-01-15 12:00:00'), line)

    def test_nightly_run_without_arguments_gives_the_same_schedule(self):
        """C3, C5: the nightly run replaces our jobs from the saved settings."""
        self.assertRunOk(*FIRST_RUN)
        self.assertRunOk()
        self.assertEqual(self.app.crontab(),
                         expectedCrontab(self.app.root, -500, 500))
        self.assertEqual(self.app.settings().decode(), FIRST_RUN_SETTINGS)

    def test_update_after_a_reboot_gives_the_same_schedule(self):
        """C3: the @reboot command waits for the clock, then replaces our
        jobs from the saved settings (#15)."""
        self.assertRunOk(*FIRST_RUN)
        fakes.fakeTimedatectl(self.app.bin, 'yes')
        self.assertRunOk('--wait-for-time-sync')
        self.assertEqual(self.app.crontab(),
                         expectedCrontab(self.app.root, -500, 500))
        self.assertEqual(self.app.settings().decode(), FIRST_RUN_SETTINGS)

    def test_an_error_is_in_the_log_after_the_start_of_its_run(self):
        """C4: an error that argparse writes has no timestamp. It comes after
        the first line of its own run, so the prune keeps it with that run (#7)."""
        log_path = f'{self.app.root}/adhan.log'
        with open(log_path, 'a') as log:
            result = self.app.run('--lat', 'north', today=TODAY, log=log)
        self.assertNotEqual(result.returncode, 0)
        with open(log_path) as fh:
            lines = fh.read().splitlines()
        self.assertTrue(lines[0].startswith('2026-01-15 12:00:00 '), lines)
        self.assertTrue(any('invalid float value' in line for line in lines[1:]), lines)

    def test_settings_ini_is_not_read(self):
        """C4: adhan.toml replaces settings.ini (#42). A settings.ini is not
        read and does not change, and the run without adhan.toml stops."""
        ini = f'{self.app.root}/settings.ini'
        with open(ini, 'w') as fh:
            fh.write(OLD_SETTINGS_INI)
        result = self.app.run(today=TODAY)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--lat', result.stdout)
        self.assertEqual(self.app.crontab(), USER_JOB)
        self.assertIsNone(self.app.settings())
        self.assertEqual(fakes.readBytes(ini), OLD_SETTINGS_INI.encode())

    def test_a_variable_with_spaces_around_the_equals_sign_stays(self):
        """C3: crontab(5) allows spaces around the = of a variable. python-crontab
        3.x deletes such a line when it reads the crontab, so the run writes it
        without the spaces (#29). Cron reads both lines the same."""
        self.app = fakes.App(self, crontab='PATH = /usr/bin:/bin\n' + USER_JOB)
        self.assertRunOk(*FIRST_RUN)
        self.assertTrue(self.app.crontab().startswith('PATH=/usr/bin:/bin\n' + USER_JOB),
                        self.app.crontab())

    def test_old_update_job_without_the_library_keeps_the_crontab(self):
        """C4: before #29, the update jobs ran the system python3 with a copy of
        python-crontab in the repo. After a git pull, the old job finds no
        python-crontab. It stops before it changes the crontab and adhan.toml,
        and the log says how to install the new jobs."""
        self.assertRunOk(*FIRST_RUN)
        crontab = self.app.crontab()
        settings = self.app.settings()
        log_path = f'{self.app.root}/adhan.log'
        with open(log_path, 'a') as log:
            result = self.app.run(today=TODAY, log=log, site_packages=False)
        self.assertNotEqual(result.returncode, 0)
        with open(log_path) as fh:
            text = fh.read()
        for line in text.splitlines():
            self.assertTrue(line.startswith('2026-01-15 12:00:00 '), text)
        self.assertIn('python-crontab', text)
        self.assertIn('uv sync', text)
        self.assertIn(f'{self.app.root}/.venv/bin/python {self.app.root}/updateAzaanTimers.py',
                      text)
        self.assertEqual(self.app.crontab(), crontab)
        self.assertEqual(self.app.settings(), settings)


if __name__ == '__main__':
    unittest.main()
