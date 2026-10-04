"""Unit tests for the pure core of updateAzaanTimers.py (#16).

Each test names the promise (C1-C6 in #16) that it protects.
"""

import datetime
import unittest
from configparser import ConfigParser

import fakes  # noqa: F401  (puts the app on sys.path)
import updateAzaanTimers as app
from modules.praytimes import PrayTimes

PRAYERS = ('fajr', 'dhuhr', 'asr', 'maghrib', 'isha')

# Expected times come from an independent source, not from this code: the
# Aladhan prayer times API, read on 2026-10-04 with school=0 (Standard Asr) and
# these queries to https://api.aladhan.com/v1/timings/<query>:
#   15-01-2026?latitude=12.8369&longitude=77.4089&method=1&timezonestring=Asia/Kolkata
#   21-06-2026?latitude=59.9139&longitude=10.7522&method=3&latitudeAdjustmentMethod=1&timezonestring=Europe/Oslo
#   01-07-2026?latitude=51.5074&longitude=-0.1278&method=3&latitudeAdjustmentMethod=1&timezonestring=Europe/London
#   15-01-2026?latitude=51.5074&longitude=-0.1278&method=3&latitudeAdjustmentMethod=1&timezonestring=Europe/London
# method=1 is Karachi, method=3 is MWL, latitudeAdjustmentMethod=1 is the
# middle of the night, the PrayTimes default. The original praytimes.org
# calculator (PrayTimes.js 2.5) gives the same times within 1 minute.
# Aladhan picked the UTC offset from the timezone, so the London rows also
# show the 1 hour of daylight saving time in summer.
FIXED_TIMES = [
    ('Bengaluru, Karachi, UTC +5:30', 12.8369, 77.4089, 'Karachi',
     datetime.date(2026, 1, 15), 5.5, ('05:31', '12:30', '15:47', '18:13', '19:28')),
    ('Oslo, MWL, midsummer, UTC +2', 59.9139, 10.7522, 'MWL',
     datetime.date(2026, 6, 21), 2, ('01:19', '13:19', '18:00', '22:44', '01:19')),
    ('London, MWL, summer (BST), UTC +1', 51.5074, -0.1278, 'MWL',
     datetime.date(2026, 7, 1), 1, ('01:04', '13:04', '17:27', '21:21', '01:04')),
    ('London, MWL, winter (GMT), UTC +0', 51.5074, -0.1278, 'MWL',
     datetime.date(2026, 1, 15), 0, ('05:59', '12:10', '14:00', '16:21', '18:15')),
]

TIMES = {'fajr': '05:31', 'dhuhr': '12:30', 'asr': '15:47',
         'maghrib': '18:13', 'isha': '19:28'}
ROOT = '/opt/adhan'
SETTINGS = app.Settings(lat=12.8369, lon=77.4089, method='Karachi',
                        default_azaan_vol=500, fajr_azaan_vol=-500,
                        surah_baqarah=False, surah_volume=300,
                        player='paplay', warnings=[])

STORED = '''[DEFAULT]
lat = 10
lon = 20
method = ISNA

[VOLUME]
defaultAzaanVolume = 700
fajrAzaanVolume = -700

[PLAYER]
player = paplay
'''


def minutes(hhmm):
    hour, minute = hhmm.split(':')
    return int(hour) * 60 + int(minute)


def play(audio, volume, player='paplay'):
    return (f'{ROOT}/playAzaan.sh {ROOT}/media/{audio} {volume} {player} '
            f'>> {ROOT}/adhan.log 2>&1')


UPDATE_JOB = app.Job(3, 15, None, None,
                     f'python3 {ROOT}/updateAzaanTimers.py >> {ROOT}/adhan.log 2>&1')
CLEAR_LOG_JOB = app.Job(0, 0, 1, None, f'truncate -s 0 {ROOT}/adhan.log 2>&1')


def args(*argv):
    return app.parseArgs().parse_args(argv)


def stored(text=STORED):
    config = ConfigParser()
    config.read_string(text)
    return config


class PrayerTimesTest(unittest.TestCase):

    def test_times_match_an_independent_source(self):
        """C1: the times are correct for the location, method, date and offset."""
        for name, lat, lon, method, date, offset, expected in FIXED_TIMES:
            with self.subTest(name):
                times = app.prayerTimes(lat, lon, method, date, offset)
                for prayer, want in zip(PRAYERS, expected):
                    self.assertRegex(times[prayer], r'^([01][0-9]|2[0-3]):[0-5][0-9]$')
                    diff = abs(minutes(times[prayer]) - minutes(want))
                    self.assertLessEqual(min(diff, 24 * 60 - diff), 1,
                                         f'{prayer} {times[prayer]}, expected {want}')

    def test_praytimes_starts_with_mwl(self):
        """C1: PrayTimes() without a method uses MWL, not Jafari (#26)."""
        self.assertEqual(PrayTimes().getMethod(), 'MWL')


class BuildJobsTest(unittest.TestCase):

    def test_one_job_per_prayer_with_its_file_and_volume(self):
        """C2: Fajr has its own file and volume, Surah Baqarah only when on (#9)."""
        prayer_jobs = [
            app.Job(5, 31, None, None, play('Adhan-fajr.mp3', -500)),
            app.Job(12, 30, None, None, play('Adhan-Makkah1.mp3', 500)),
            app.Job(15, 47, None, None, play('Adhan-Makkah1.mp3', 500)),
            app.Job(18, 13, None, None, play('Adhan-Makkah1.mp3', 500)),
            app.Job(19, 28, None, None, play('Adhan-Makkah1.mp3', 500)),
        ]
        friday = app.Job(7, 0, None, 5, play('002-surah-baqarah-mishary.mp3', 300))
        for surah_baqarah, expected in ((False, prayer_jobs),
                                        (True, prayer_jobs + [friday])):
            with self.subTest(surah_baqarah=surah_baqarah):
                settings = SETTINGS._replace(surah_baqarah=surah_baqarah)
                jobs = app.buildJobs(TIMES, settings, ROOT)
                self.assertCountEqual(jobs, expected + [UPDATE_JOB, CLEAR_LOG_JOB])

    def test_edge_times_give_the_right_hour_and_minute(self):
        """C2: 00:05 and 23:59 become the right cron hour and minute."""
        times = dict(TIMES, fajr='00:05', isha='23:59')
        jobs = app.buildJobs(times, SETTINGS, ROOT)
        self.assertIn(app.Job(0, 5, None, None, play('Adhan-fajr.mp3', -500)), jobs)
        self.assertIn(app.Job(23, 59, None, None, play('Adhan-Makkah1.mp3', 500)), jobs)

    def test_schedule_renews_itself(self):
        """C3: a nightly update at 03:15 and a log clear on day 1 at 00:00."""
        jobs = app.buildJobs(TIMES, SETTINGS, ROOT)
        self.assertIn(UPDATE_JOB, jobs)
        self.assertIn(CLEAR_LOG_JOB, jobs)


class ResolveSettingsTest(unittest.TestCase):

    def test_each_value_comes_from_the_command_line_then_the_file_then_the_default(self):
        """C5: settings work as expected, value by value."""
        only_location = '[DEFAULT]\nlat = 10\nlon = 20\nmethod = ISNA\n'
        cases = [
            ('the command line wins',
             ('--lat', '12.8369', '--lon', '77.4089', '--method', 'Karachi',
              '--azaan-volume', '500', '--fajr-azaan-volume', '-500', '--player', 'vlc'),
             STORED,
             dict(lat=12.8369, lon=77.4089, method='Karachi', default_azaan_vol=500,
                  fajr_azaan_vol=-500, player='vlc')),
            ('the stored value is used', (), STORED,
             dict(lat=10, lon=20, method='ISNA', default_azaan_vol=700,
                  fajr_azaan_vol=-700, player='paplay')),
            ('the default is used', (), only_location,
             dict(default_azaan_vol=0, fajr_azaan_vol=0, player='vlc')),
            ('0 from the command line is a value (#6)',
             ('--lat', '0', '--lon', '0', '--azaan-volume', '0', '--fajr-azaan-volume', '0'),
             STORED,
             dict(lat=0, lon=0, default_azaan_vol=0, fajr_azaan_vol=0)),
            ('one volume missing, the other given (#23)', (),
             STORED.replace('defaultAzaanVolume = 700\n', ''),
             dict(default_azaan_vol=0, fajr_azaan_vol=-700)),
            ('karachi is accepted as Karachi (#26)', (),
             STORED.replace('ISNA', 'karachi'),
             dict(method='Karachi')),
        ]
        for name, argv, text, expected in cases:
            with self.subTest(name):
                settings = app.resolveSettings(args(*argv), stored(text))
                self.assertEqual({key: getattr(settings, key) for key in expected},
                                 expected)

    def test_bad_input_raises_config_error(self):
        """C4: bad or missing input is an error, not a schedule."""
        cases = [
            ('latitude nan', ('--lat', 'nan'), STORED),
            ('latitude inf', ('--lat', 'inf'), STORED),
            ('latitude 91', ('--lat', '91'), STORED),
            ('longitude 181', ('--lon', '181'), STORED),
            ('unknown method Foo (#26)', (), STORED.replace('ISNA', 'Foo')),
            ('unsupported player', (), STORED.replace('paplay', 'winamp')),
            ('latitude missing', (), STORED.replace('lat = 10\n', '')),
            ('longitude missing', (), STORED.replace('lon = 20\n', '')),
            ('method missing', (), STORED.replace('method = ISNA\n', '')),
        ]
        for name, argv, text in cases:
            with self.subTest(name):
                with self.assertRaises(app.ConfigError):
                    app.resolveSettings(args(*argv), stored(text))


if __name__ == '__main__':
    unittest.main()
