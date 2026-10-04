"""Characterization tests: what a full run of updateAzaanTimers.py does today.

Each test runs the script as a command, as cron does, in a temporary copy of
the app. The expected crontab and settings.ini were recorded from the script
before the refactor into a core and a shell (#16). They protect that refactor:
they must pass before and after it.
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

FIRST_RUN_SETTINGS = '''[DEFAULT]
lat = 12.8369
lon = 77.4089
method = Karachi

[VOLUME]
defaultazaanvolume = 500
fajrazaanvolume = -500

[FRIDAY]
playsurahbaqarah = False
surahvolume = 0

[PLAYER]
player = vlc

'''


def expectedCrontab(root, fajr_volume, volume, friday=None):
    play = f'{root}/playAzaan.sh {root}/media'
    log = f'>> {root}/adhan.log 2>&1 # rpiAdhanClockJob'
    lines = [USER_JOB]
    for (hour, minute), audio, vol in zip(
            PRAYER_TIMES, ['Adhan-fajr.mp3'] + ['Adhan-Makkah1.mp3'] * 4,
            [fajr_volume] + [volume] * 4):
        lines.append(f'{minute} {hour} * * * {play}/{audio} {vol} vlc {log}')
    if friday is not None:
        lines.append(f'0 7 * * 5 {play}/002-surah-baqarah-mishary.mp3 {friday} vlc {log}')
    lines.append(f'15 3 * * * python3 {root}/updateAzaanTimers.py {log}')
    lines.append(f'@monthly truncate -s 0 {root}/adhan.log 2>&1 # rpiAdhanClockJob')
    return '\n'.join(lines) + '\n'


class FullRunTest(unittest.TestCase):

    def setUp(self):
        fakes.guardRealSettings(self)
        self.app = fakes.App(self, crontab=USER_JOB)

    def run_app(self, *argv, **kwargs):
        return self.app.run(*argv, today=TODAY, **kwargs)

    def assertRunOk(self, *argv):
        result = self.run_app(*argv)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_first_run_installs_the_jobs_and_saves_the_settings(self):
        """C2, C3, C5: one job per prayer, the update and the log clear."""
        self.assertRunOk(*FIRST_RUN)
        self.assertEqual(self.app.crontab(),
                         expectedCrontab(self.app.root, -500, 500))
        self.assertEqual(self.app.settings().decode(), FIRST_RUN_SETTINGS)

    def test_nightly_run_without_arguments_gives_the_same_schedule(self):
        """C3, C5: the nightly run replaces our jobs from the saved settings."""
        self.assertRunOk(*FIRST_RUN)
        self.assertRunOk()
        self.assertEqual(self.app.crontab(),
                         expectedCrontab(self.app.root, -500, 500))
        self.assertEqual(self.app.settings().decode(), FIRST_RUN_SETTINGS)

    def test_hand_edited_settings_are_resolved_value_by_value(self):
        """C5: any case for the method and the player, a missing volume is 0."""
        self.app.writeSettings('[DEFAULT]\nlat = 12.8369\nlon = 77.4089\n'
                               'method = karachi\n\n[VOLUME]\n'
                               'fajrAzaanVolume = -500\n\n[PLAYER]\nplayer = VLC\n')
        self.assertRunOk()
        self.assertEqual(self.app.crontab(),
                         expectedCrontab(self.app.root, -500, 0))
        self.assertEqual(self.app.settings().decode(), '''[DEFAULT]
lat = 12.8369
lon = 77.4089
method = Karachi

[VOLUME]
defaultazaanvolume = 0
fajrazaanvolume = -500

[PLAYER]
player = vlc

[FRIDAY]
playsurahbaqarah = False
surahvolume = 0

''')

    def test_surah_baqarah_on_adds_the_friday_job(self):
        """C2: while Surah Baqarah exists (#9), it plays on Friday at 07:00."""
        settings = FIRST_RUN_SETTINGS.replace(
            'playsurahbaqarah = False\nsurahvolume = 0',
            'playsurahbaqarah = true\nsurahvolume = 300')
        self.app.writeSettings(settings)
        self.assertRunOk()
        self.assertEqual(self.app.crontab(),
                         expectedCrontab(self.app.root, -500, 500, friday=300))
        self.assertEqual(self.app.settings().decode(), settings)

    def test_bad_input_changes_nothing(self):
        """C4: exit 1, and the crontab and settings.ini stay as they were."""
        self.assertRunOk(*FIRST_RUN)
        cases = [
            ('latitude 91', ('--lat', '91'), FIRST_RUN_SETTINGS, True),
            ('latitude nan', ('--lat', 'nan'), FIRST_RUN_SETTINGS, True),
            ('longitude 181', ('--lon', '181'), FIRST_RUN_SETTINGS, True),
            ('unknown method in settings.ini', (),
             FIRST_RUN_SETTINGS.replace('Karachi', 'Foo'), True),
            ('unsupported player in settings.ini', (),
             FIRST_RUN_SETTINGS.replace('player = vlc', 'player = winamp'), True),
            ('latitude missing', (),
             FIRST_RUN_SETTINGS.replace('lat = 12.8369\n', ''), True),
            ('player not on PATH', (), FIRST_RUN_SETTINGS, False),
        ]
        for name, argv, settings, player_on_path in cases:
            with self.subTest(name):
                self.app.writeSettings(settings)
                crontab = self.app.crontab()
                result = self.run_app(*argv, player_on_path=player_on_path)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(self.app.crontab(), crontab)
                self.assertEqual(self.app.settings().decode(), settings)


if __name__ == '__main__':
    unittest.main()
