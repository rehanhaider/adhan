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
NO_OFFSETS = dict.fromkeys(PRAYERS, 0)
ALL_ON = dict.fromkeys(PRAYERS, True)
DEFAULT_AUDIO = {'default': 'Adhan-Makkah1.mp3', 'fajr': 'Adhan-fajr.mp3'}
SETTINGS = app.Settings(lat=12.8369, lon=77.4089, method='Karachi',
                        default_azaan_vol=500, fajr_azaan_vol=-500,
                        surah_baqarah=False, surah_volume=300,
                        player='paplay', offsets=NO_OFFSETS, enabled=ALL_ON,
                        audio=DEFAULT_AUDIO, warnings=[])

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
REBOOT_JOB = app.Job(None, None, None, None,
                     f'python3 {ROOT}/updateAzaanTimers.py --wait-for-time-sync '
                     f'>> {ROOT}/adhan.log 2>&1', reboot=True)


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

    def test_offsets_move_each_time_by_its_minutes(self):
        """C1: an offset adds its minutes to its prayer only (#12), and the
        next calculation without offsets gives the times without them."""
        args = (12.8369, 77.4089, 'Karachi', datetime.date(2026, 1, 15), 5.5)
        base = app.prayerTimes(*args)
        offsets = {'fajr': 5, 'dhuhr': -3, 'asr': 0, 'maghrib': 6, 'isha': 15}
        moved = app.prayerTimes(*args, offsets=offsets)
        for prayer in PRAYERS:
            self.assertEqual(minutes(moved[prayer]), minutes(base[prayer]) + offsets[prayer],
                             prayer)
        self.assertEqual(app.prayerTimes(*args), base)
        self.assertEqual(app.prayerTimes(*args, offsets=NO_OFFSETS), base)

    def test_praytimes_tune_changes_its_own_times_only(self):
        """C1: PrayTimes.tune() adds the minutes. Before #12 it raised
        AttributeError, and all PrayTimes objects shared one set of offsets."""
        tuned, other = PrayTimes('Karachi'), PrayTimes('Karachi')
        tuned.tune({'fajr': 5})
        args = ((2026, 1, 15), (12.8369, 77.4089), 5.5)
        self.assertEqual(tuned.getTimes(*args)['fajr'], '05:36')
        self.assertEqual(other.getTimes(*args)['fajr'], '05:31')

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
                self.assertCountEqual(jobs, expected + [UPDATE_JOB, REBOOT_JOB])

    def test_a_prayer_that_is_off_has_no_job(self):
        """C2: a prayer that is off has no job, the others keep theirs (#13).
        With all five off, the jobs that renew the schedule stay."""
        settings = SETTINGS._replace(enabled=dict(ALL_ON, fajr=False, isha=False))
        jobs = app.buildJobs(TIMES, settings, ROOT)
        self.assertCountEqual(jobs, [
            app.Job(12, 30, None, None, play('Adhan-Makkah1.mp3', 500)),
            app.Job(15, 47, None, None, play('Adhan-Makkah1.mp3', 500)),
            app.Job(18, 13, None, None, play('Adhan-Makkah1.mp3', 500)),
            UPDATE_JOB, REBOOT_JOB])
        settings = SETTINGS._replace(enabled=dict.fromkeys(PRAYERS, False),
                                     surah_baqarah=True)
        jobs = app.buildJobs(TIMES, settings, ROOT)
        self.assertCountEqual(jobs, [
            app.Job(7, 0, None, 5, play('002-surah-baqarah-mishary.mp3', 300)),
            UPDATE_JOB, REBOOT_JOB])

    def test_each_prayer_plays_its_audio_file(self):
        """C2: a prayer plays its own file, else the default file. A name is
        in media/, an absolute path is used as it is, and a space is quoted
        for the shell of cron (#10)."""
        audio = dict(DEFAULT_AUDIO, default='Adhan-Madinah.mp3', fajr='/home/me/fajr.mp3',
                     isha='My Adhan.mp3')
        jobs = app.buildJobs(TIMES, SETTINGS._replace(audio=audio), ROOT)
        log = f'>> {ROOT}/adhan.log 2>&1'
        self.assertCountEqual(jobs, [
            app.Job(5, 31, None, None,
                    f'{ROOT}/playAzaan.sh /home/me/fajr.mp3 -500 paplay {log}'),
            app.Job(12, 30, None, None, play('Adhan-Madinah.mp3', 500)),
            app.Job(15, 47, None, None, play('Adhan-Madinah.mp3', 500)),
            app.Job(18, 13, None, None, play('Adhan-Madinah.mp3', 500)),
            app.Job(19, 28, None, None,
                    f"{ROOT}/playAzaan.sh '{ROOT}/media/My Adhan.mp3' 500 paplay {log}"),
            UPDATE_JOB, REBOOT_JOB])

    def test_edge_times_give_the_right_hour_and_minute(self):
        """C2: 00:05 and 23:59 become the right cron hour and minute."""
        times = dict(TIMES, fajr='00:05', isha='23:59')
        jobs = app.buildJobs(times, SETTINGS, ROOT)
        self.assertIn(app.Job(0, 5, None, None, play('Adhan-fajr.mp3', -500)), jobs)
        self.assertIn(app.Job(23, 59, None, None, play('Adhan-Makkah1.mp3', 500)), jobs)

    def test_schedule_renews_itself(self):
        """C3: a nightly update at 03:15, an update after each reboot that
        waits for the clock (#15), and no job that clears the log (#7)."""
        jobs = app.buildJobs(TIMES, SETTINGS, ROOT)
        self.assertIn(UPDATE_JOB, jobs)
        self.assertIn(REBOOT_JOB, jobs)
        self.assertEqual([job for job in jobs if 'truncate' in job.command], [])


class PruneLogTest(unittest.TestCase):

    def test_keeps_the_last_30_days(self):
        """C3: the nightly update keeps the log small, so it keeps running (#7)."""
        today = datetime.date(2026, 3, 31)
        old = '2026-02-28 23:59:59 31 days ago\n'
        oldest_kept = '2026-03-01 00:00:00 30 days ago\n'
        now = '2026-03-31 03:15:00 today\n'
        no_stamp = 'Traceback (most recent call last):\n'
        cases = [
            ('a line from 31 days ago is deleted', [old, now], [now]),
            ('lines from 30 days ago and today stay', [oldest_kept, now], [oldest_kept, now]),
            ('a line with no timestamp stays with the line above it',
             [old, no_stamp, oldest_kept, no_stamp, now],
             [oldest_kept, no_stamp, now]),
            ('lines above the first timestamp go with it',
             [no_stamp, old, now], [now]),
            ('lines above the first timestamp stay with it',
             [no_stamp, now], [no_stamp, now]),
            ('a log with no timestamp stays, its age is unknown', [no_stamp], [no_stamp]),
            ('a bad date is not a timestamp', [old, '2026-13-45 00:00:00 bad\n', now], [now]),
            ('a line after today stays, the clock can be behind',
             [now, '2026-04-02 03:15:00 later\n'], [now, '2026-04-02 03:15:00 later\n']),
            ('an empty log stays empty', [], []),
        ]
        for name, lines, expected in cases:
            with self.subTest(name):
                self.assertEqual(app.pruneLog(lines, today), expected)


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
            ('the stored offsets are used, a missing one is 0 (#12)', (),
             STORED + '[OFFSETS]\nfajr = +5\nIsha = -2\n',
             dict(offsets=dict(NO_OFFSETS, fajr=5, isha=-2))),
            ('an offset on the command line wins, prayer by prayer (#12)',
             ('--fajr-offset', '7', '--maghrib-offset', '-1'),
             STORED + '[OFFSETS]\nfajr = 5\nisha = -2\n',
             dict(offsets=dict(NO_OFFSETS, fajr=7, maghrib=-1, isha=-2))),
            ('0 on the command line is an offset (#12)', ('--fajr-offset', '0'),
             STORED + '[OFFSETS]\nfajr = 5\n',
             dict(offsets=NO_OFFSETS)),
            ('the command line replaces a bad stored offset (#12)', ('--fajr-offset', '3'),
             STORED + '[OFFSETS]\nfajr = five\n',
             dict(offsets=dict(NO_OFFSETS, fajr=3))),
            ('the default offsets are 0 (#12)', (), only_location,
             dict(offsets=NO_OFFSETS)),
            ('the stored prayers that are on or off are used (#13)', (),
             STORED + '[ENABLED]\nfajr = false\nAsr = No\nisha = 1\n',
             dict(enabled=dict(ALL_ON, fajr=False, asr=False))),
            ('the command line turns a prayer on or off (#13)',
             ('--no-play-dhuhr', '--play-fajr'),
             STORED + '[ENABLED]\nfajr = false\nisha = false\n',
             dict(enabled=dict(ALL_ON, dhuhr=False, isha=False))),
            ('the command line replaces a bad stored value (#13)', ('--no-play-fajr',),
             STORED + '[ENABLED]\nfajr = maybe\n',
             dict(enabled=dict(ALL_ON, fajr=False))),
            ('all prayers are on by default (#13)', (), only_location,
             dict(enabled=ALL_ON)),
            ('the stored audio files are used (#10)', (),
             STORED + '[AUDIO]\ndefault = Adhan-Madinah.mp3\nIsha = /home/me/isha.mp3\n',
             dict(audio={'default': 'Adhan-Madinah.mp3', 'fajr': 'Adhan-fajr.mp3',
                         'isha': '/home/me/isha.mp3'})),
            ('an audio file on the command line wins (#10)',
             ('--audio', 'Adhan-Makkah2.mp3', '--fajr-audio', 'Adhan-Turkish.mp3',
              '--asr-audio', 'Adhan-Makkah1-Dua.mp3'),
             STORED + '[AUDIO]\ndefault = Adhan-Madinah.mp3\nfajr = x.mp3\nisha = y.mp3\n',
             dict(audio={'default': 'Adhan-Makkah2.mp3', 'fajr': 'Adhan-Turkish.mp3',
                         'asr': 'Adhan-Makkah1-Dua.mp3', 'isha': 'y.mp3'})),
            ('the default audio files are the files of today (#10)', (), only_location,
             dict(audio=DEFAULT_AUDIO)),
            ('a prayer in [DEFAULT] is not an audio file (#10)', (),
             STORED.replace('[DEFAULT]\n', '[DEFAULT]\nfajr = x.mp3\n') + '[AUDIO]\n',
             dict(audio=DEFAULT_AUDIO)),
            ('a prayer in [DEFAULT] is not on or off (#13)', (),
             STORED.replace('[DEFAULT]\n', '[DEFAULT]\nfajr = false\n') + '[ENABLED]\n',
             dict(enabled=ALL_ON)),
            ('a prayer in [DEFAULT] is not an offset (#12)', (),
             STORED.replace('[DEFAULT]\n', '[DEFAULT]\nfajr = 9\n') + '[OFFSETS]\nisha = 1\n',
             dict(offsets=dict(NO_OFFSETS, isha=1))),
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
            ('offset 5.5 is not a whole number (#12)', (), STORED + '[OFFSETS]\nfajr = 5.5\n'),
            ('offset five is not a number (#12)', (), STORED + '[OFFSETS]\nisha = five\n'),
            ('offset with no value (#12)', (), STORED + '[OFFSETS]\nasr =\n'),
            ('offset of an unknown prayer, a typo (#12)', (), STORED + '[OFFSETS]\nfjar = 5\n'),
            ('lat in [OFFSETS], also a key of [DEFAULT] (#12)', (), STORED + '[OFFSETS]\nlat = 5\n'),
            ('on or off is maybe (#13)', (), STORED + '[ENABLED]\nfajr = maybe\n'),
            ('on or off with no value (#13)', (), STORED + '[ENABLED]\nisha =\n'),
            ('on or off of an unknown prayer, a typo (#13)', (), STORED + '[ENABLED]\nfjar = false\n'),
            ('audio file of an unknown prayer, a typo (#10)', (), STORED + '[AUDIO]\nfjar = x.mp3\n'),
            ('audio file with no value (#10)', (), STORED + '[AUDIO]\nfajr =\n'),
            ('audio file with %, which cron changes (#10)', (), STORED + '[AUDIO]\nisha = 100%.mp3\n'),
            ('audio file with % on the command line (#10)', ('--audio', '100%.mp3'), STORED),
            ('audio file with #, which the crontab reads as a comment (#10)', (),
             STORED + '[AUDIO]\nisha = Adhan #2.mp3\n'),
            ('audio file with # and no space (#10)', ('--fajr-audio', 'Adhan#2.mp3'), STORED),
            ('audio file that starts with a space, settings.ini loses it (#10)',
             ('--isha-audio', ' Adhan-Madinah.mp3'), STORED),
            ('audio file that ends with a space (#10)', ('--audio', 'Adhan-Madinah.mp3 '), STORED),
        ]
        for name, argv, text in cases:
            with self.subTest(name):
                with self.assertRaises(app.ConfigError):
                    app.resolveSettings(args(*argv), stored(text))


if __name__ == '__main__':
    unittest.main()
