"""Unit tests for the pure core of updateAzaanTimers.py (#16).

Each test names the promise (C1-C6 in #16) that it protects.
"""

import copy
import datetime
import math
import tomllib
import unittest

import fakes  # noqa: F401  (puts the app on sys.path)
import updateAzaanTimers as app
from modules.praytimes import PrayTimes

PRAYERS = ('fajr', 'dhuhr', 'asr', 'maghrib', 'isha')

# Expected times come from an independent source, not from this code: the
# Aladhan prayer times API, read on 2026-10-04 with school=0 (Standard Asr) and
# these queries to https://api.aladhan.com/v1/timings/<query>. HANAFI_ASR is
# the first query with school=1 (Hanafi Asr).
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
DEFAULT_VOLUME = {'default': 0, 'fajr': 0}
HANAFI_ASR = '16:37'
SETTINGS = app.Settings(lat=12.8369, lon=77.4089, method='Karachi', asr='Standard',
                        volume={'default': 500, 'fajr': -500},
                        surah_baqarah=False, surah_volume=300,
                        player='paplay', leadin=0, offsets=NO_OFFSETS, enabled=ALL_ON,
                        audio=DEFAULT_AUDIO)

# adhan.toml as tomllib reads it
STORED = {
    'location': {'lat': 10, 'lon': 20, 'method': 'ISNA'},
    'audio': {'volume': 700, 'player': 'paplay'},
    'prayers': {'fajr': {'volume': -700}},
}
ONLY_LOCATION = {'location': STORED['location']}


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


def merge(base, change):
    """A copy of base with the tables and keys of change in it. A key with
    the value None is removed."""
    result = copy.deepcopy(base)
    for key, value in change.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


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

    def test_hanafi_asr_matches_an_independent_source(self):
        """C1: Hanafi moves Asr only (#11). A Hanafi calculation does not
        change the next Standard one: PrayTimes keeps its settings in the class."""
        args = (12.8369, 77.4089, 'Karachi', datetime.date(2026, 1, 15), 5.5)
        standard = app.prayerTimes(*args)
        hanafi = app.prayerTimes(*args, asr='Hanafi')
        diff = abs(minutes(hanafi['asr']) - minutes(HANAFI_ASR))
        self.assertLessEqual(diff, 1, f"asr {hanafi['asr']}, expected {HANAFI_ASR}")
        self.assertEqual(dict(hanafi, asr=standard['asr']), standard)
        self.assertEqual(app.prayerTimes(*args), standard)
        self.assertEqual(app.prayerTimes(*args, asr='Standard'), standard)

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

    def test_each_prayer_plays_at_its_volume(self):
        """C2: a prayer plays at its own volume, else at the default volume.
        Fajr has its own default volume, so it does not change with the
        default volume."""
        volume = {'default': 500, 'fajr': -500, 'asr': -1000}
        jobs = app.buildJobs(TIMES, SETTINGS._replace(volume=volume), ROOT)
        self.assertCountEqual(jobs, [
            app.Job(5, 31, None, None, play('Adhan-fajr.mp3', -500)),
            app.Job(12, 30, None, None, play('Adhan-Makkah1.mp3', 500)),
            app.Job(15, 47, None, None, play('Adhan-Makkah1.mp3', -1000)),
            app.Job(18, 13, None, None, play('Adhan-Makkah1.mp3', 500)),
            app.Job(19, 28, None, None, play('Adhan-Makkah1.mp3', 500)),
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

    def test_a_leadin_is_given_to_each_adhan_job(self):
        """C2: a lead-in of more than 0 seconds is the last argument of each
        job that plays, and the other jobs do not change. 0 gives the job of
        before (#14)."""
        log = f'>> {ROOT}/adhan.log 2>&1'
        settings = SETTINGS._replace(leadin=2, surah_baqarah=True)
        jobs = app.buildJobs(TIMES, settings, ROOT)
        self.assertCountEqual(jobs, [
            app.Job(5, 31, None, None,
                    f'{ROOT}/playAzaan.sh {ROOT}/media/Adhan-fajr.mp3 -500 paplay 2 {log}'),
            *[app.Job(int(TIMES[name][:2]), int(TIMES[name][3:]), None, None,
                      f'{ROOT}/playAzaan.sh {ROOT}/media/Adhan-Makkah1.mp3 500 paplay 2 {log}')
              for name in PRAYERS[1:]],
            app.Job(7, 0, None, 5,
                    f'{ROOT}/playAzaan.sh {ROOT}/media/002-surah-baqarah-mishary.mp3 '
                    f'300 paplay 2 {log}'),
            UPDATE_JOB, REBOOT_JOB])


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
        cases = [
            ('the command line wins',
             ('--lat', '12.8369', '--lon', '77.4089', '--method', 'Karachi',
              '--azaan-volume', '500', '--fajr-azaan-volume', '-500', '--player', 'vlc'),
             STORED,
             dict(lat=12.8369, lon=77.4089, method='Karachi',
                  volume={'default': 500, 'fajr': -500}, player='vlc')),
            ('the stored value is used', (), STORED,
             dict(lat=10, lon=20, method='ISNA', volume={'default': 700, 'fajr': -700},
                  player='paplay')),
            ('a stored float is used', (),
             merge(STORED, {'location': {'lat': 12.8369, 'lon': -0.5}}),
             dict(lat=12.8369, lon=-0.5)),
            ('the default is used', (), ONLY_LOCATION,
             dict(volume=DEFAULT_VOLUME, player='vlc')),
            ('an empty table gives the defaults', (),
             merge(ONLY_LOCATION, {'audio': {}, 'prayers': {'fajr': {}}, 'surah_baqarah': {}}),
             dict(volume=DEFAULT_VOLUME, player='vlc', offsets=NO_OFFSETS, enabled=ALL_ON,
                  audio=DEFAULT_AUDIO, surah_baqarah=False, surah_volume=0)),
            ('0 from the command line is a value (#6)',
             ('--lat', '0', '--lon', '0', '--azaan-volume', '0', '--fajr-azaan-volume', '0'),
             STORED,
             dict(lat=0, lon=0, volume=DEFAULT_VOLUME)),
            ('one volume missing, the other given (#23)', (),
             merge(STORED, {'audio': {'volume': None}}),
             dict(volume={'default': 0, 'fajr': -700})),
            ('a prayer can have its own volume', (),
             merge(STORED, {'prayers': {'isha': {'volume': -300}}}),
             dict(volume={'default': 700, 'fajr': -700, 'isha': -300})),
            ('karachi is accepted as Karachi (#26)', (),
             merge(STORED, {'location': {'method': 'karachi'}}),
             dict(method='Karachi')),
            ('the stored offsets are used, a missing one is 0 (#12)', (),
             merge(STORED, {'prayers': {'fajr': {'offset_minutes': 5},
                                        'isha': {'offset_minutes': -2}}}),
             dict(offsets=dict(NO_OFFSETS, fajr=5, isha=-2))),
            ('an offset on the command line wins, prayer by prayer (#12)',
             ('--fajr-offset', '7', '--maghrib-offset', '-1'),
             merge(STORED, {'prayers': {'fajr': {'offset_minutes': 5},
                                        'isha': {'offset_minutes': -2}}}),
             dict(offsets=dict(NO_OFFSETS, fajr=7, maghrib=-1, isha=-2))),
            ('0 on the command line is an offset (#12)', ('--fajr-offset', '0'),
             merge(STORED, {'prayers': {'fajr': {'offset_minutes': 5}}}),
             dict(offsets=NO_OFFSETS)),
            ('the default offsets are 0 (#12)', (), ONLY_LOCATION,
             dict(offsets=NO_OFFSETS)),
            ('the stored prayers that are on or off are used (#13)', (),
             merge(STORED, {'prayers': {'fajr': {'enabled': False}, 'asr': {'enabled': False},
                                        'isha': {'enabled': True}}}),
             dict(enabled=dict(ALL_ON, fajr=False, asr=False))),
            ('the command line turns a prayer on or off (#13)',
             ('--no-play-dhuhr', '--play-fajr'),
             merge(STORED, {'prayers': {'fajr': {'enabled': False},
                                        'isha': {'enabled': False}}}),
             dict(enabled=dict(ALL_ON, dhuhr=False, isha=False))),
            ('all prayers are on by default (#13)', (), ONLY_LOCATION,
             dict(enabled=ALL_ON)),
            ('the stored audio files are used (#10)', (),
             merge(STORED, {'audio': {'file': 'Adhan-Madinah.mp3'},
                            'prayers': {'isha': {'file': '/home/me/isha.mp3'}}}),
             dict(audio={'default': 'Adhan-Madinah.mp3', 'fajr': 'Adhan-fajr.mp3',
                         'isha': '/home/me/isha.mp3'})),
            ('an audio file on the command line wins (#10)',
             ('--audio', 'Adhan-Makkah2.mp3', '--fajr-audio', 'Adhan-Turkish.mp3',
              '--asr-audio', 'Adhan-Makkah1-Dua.mp3'),
             merge(STORED, {'audio': {'file': 'Adhan-Madinah.mp3'},
                            'prayers': {'fajr': {'file': 'x.mp3'},
                                        'isha': {'file': 'y.mp3'}}}),
             dict(audio={'default': 'Adhan-Makkah2.mp3', 'fajr': 'Adhan-Turkish.mp3',
                         'asr': 'Adhan-Makkah1-Dua.mp3', 'isha': 'y.mp3'})),
            ('the default audio files are the files of today (#10)', (), ONLY_LOCATION,
             dict(audio=DEFAULT_AUDIO)),
            ('a file name keeps a space, a quote and a backslash', (),
             merge(STORED, {'audio': {'file': 'My "Adhan" \\ 2.mp3'}}),
             dict(audio=dict(DEFAULT_AUDIO, default='My "Adhan" \\ 2.mp3'))),
            ('the stored asr is used, hanafi is accepted as Hanafi (#11)', (),
             merge(STORED, {'location': {'asr': 'hanafi'}}),
             dict(asr='Hanafi')),
            ('asr on the command line wins, in any case (#11)', ('--asr', 'STANDARD'),
             merge(STORED, {'location': {'asr': 'Hanafi'}}),
             dict(asr='Standard')),
            ('the default asr is Standard (#11)', (), ONLY_LOCATION,
             dict(asr='Standard')),
            ('the stored lead-in is used (#14)', (),
             merge(STORED, {'audio': {'leadin_seconds': 2}}),
             dict(leadin=2)),
            ('the lead-in on the command line wins (#14)', ('--leadin-seconds', '10'),
             merge(STORED, {'audio': {'leadin_seconds': 2}}),
             dict(leadin=10)),
            ('0 on the command line is a lead-in (#14)', ('--leadin-seconds', '0'),
             merge(STORED, {'audio': {'leadin_seconds': 2}}),
             dict(leadin=0)),
            ('the default lead-in is 0 (#14)', (), ONLY_LOCATION,
             dict(leadin=0)),
            ('the stored Surah Baqarah is used (#9)', (),
             merge(STORED, {'surah_baqarah': {'enabled': True, 'volume': -100}}),
             dict(surah_baqarah=True, surah_volume=-100)),
            ('Surah Baqarah is off by default (#9)', (), ONLY_LOCATION,
             dict(surah_baqarah=False, surah_volume=0)),
            ('the player in any case', (), merge(STORED, {'audio': {'player': 'VLC'}}),
             dict(player='vlc')),
        ]
        for name, argv, stored, expected in cases:
            with self.subTest(name):
                settings = app.resolveSettings(args(*argv), stored)
                self.assertEqual({key: getattr(settings, key) for key in expected},
                                 expected)

    def test_bad_input_raises_config_error(self):
        """C4: bad or missing input is an error, not a schedule."""
        def prayer(name, **values):
            return merge(STORED, {'prayers': {name: values}})

        cases = [
            ('latitude nan', ('--lat', 'nan'), STORED),
            ('latitude inf', ('--lat', 'inf'), STORED),
            ('latitude 91', ('--lat', '91'), STORED),
            ('longitude 181', ('--lon', '181'), STORED),
            ('stored latitude nan', (), merge(STORED, {'location': {'lat': math.nan}})),
            ('stored longitude -181', (), merge(STORED, {'location': {'lon': -181}})),
            ('unknown method Foo (#26)', (), merge(STORED, {'location': {'method': 'Foo'}})),
            ('unsupported player', (), merge(STORED, {'audio': {'player': 'winamp'}})),
            ('no file', (), {}),
            ('no [location]', (), merge(STORED, {'location': None})),
            ('latitude missing', (), merge(STORED, {'location': {'lat': None}})),
            ('longitude missing', (), merge(STORED, {'location': {'lon': None}})),
            ('method missing', (), merge(STORED, {'location': {'method': None}})),
            # Wrong types: each value has one type
            ('latitude as text', (), merge(STORED, {'location': {'lat': '10'}})),
            ('latitude as a boolean', (), merge(STORED, {'location': {'lat': True}})),
            ('method as a number', (), merge(STORED, {'location': {'method': 1}})),
            ('asr as a list', (), merge(STORED, {'location': {'asr': ['Hanafi']}})),
            ('volume as text', (), merge(STORED, {'audio': {'volume': '700'}})),
            ('volume 1.5 is not a whole number', (), merge(STORED, {'audio': {'volume': 1.5}})),
            ('volume as a boolean', (), merge(STORED, {'audio': {'volume': True}})),
            ('volume of a prayer as text', (), prayer('fajr', volume='-700')),
            ('player as a boolean', (), merge(STORED, {'audio': {'player': False}})),
            ('file as a number', (), merge(STORED, {'audio': {'file': 1}})),
            ('Surah Baqarah on as text (#9)', (),
             merge(STORED, {'surah_baqarah': {'enabled': 'True'}})),
            ('Surah Baqarah volume as text (#9)', (),
             merge(STORED, {'surah_baqarah': {'volume': '0'}})),
            ('Surah Baqarah volume 1.5 (#9)', (),
             merge(STORED, {'surah_baqarah': {'volume': 1.5}})),
            ('a date, which TOML can give', (),
             merge(STORED, {'location': {'lat': datetime.date(2026, 1, 15)}})),
            # A value where a table must be, and a table where a value must be
            ('[location] as a value', (), merge(STORED, {'location': 'London'})),
            ('[prayers] as a value', (), merge(STORED, {'prayers': 5})),
            ('[prayers.fajr] as a value', (), merge(STORED, {'prayers': {'fajr': False}})),
            ('[surah_baqarah] as a value (#9)', (), merge(STORED, {'surah_baqarah': True})),
            ('latitude as a table', (), merge(STORED, {'location': {'lat': {'deg': 10}}})),
            # Unknown keys: a typo must not lose a value
            ('unknown table, the old [FRIDAY]', (), merge(STORED, {'FRIDAY': {}})),
            ('unknown value at the top', (), merge(STORED, {'lat': 10})),
            ('unknown key in [location]', (), merge(STORED, {'location': {'latitude': 10}})),
            ('unknown key in [audio]', (), merge(STORED, {'audio': {'default': 'x.mp3'}})),
            ('unknown key in [surah_baqarah] (#9)', (),
             merge(STORED, {'surah_baqarah': {'time': '07:00'}})),
            ('key in the wrong case', (), merge(STORED, {'location': {'Lat': 10}})),
            ('offset 5.5 is not a whole number (#12)', (), prayer('fajr', offset_minutes=5.5)),
            ('offset as text (#12)', (), prayer('isha', offset_minutes='5')),
            ('offset of an unknown prayer, a typo (#12)', (), prayer('fjar', offset_minutes=5)),
            ('unknown key in a prayer, a typo (#12)', (), prayer('fajr', offset=5)),
            ('on or off as text (#13)', (), prayer('fajr', enabled='false')),
            ('on or off as a number (#13)', (), prayer('isha', enabled=0)),
            ('unknown asr Shafii (#11)', (), merge(STORED, {'location': {'asr': 'Shafii'}})),
            ('empty asr (#11)', (), merge(STORED, {'location': {'asr': ''}})),
            ('lead-in -1 (#14)', (), merge(STORED, {'audio': {'leadin_seconds': -1}})),
            ('lead-in 1.5 is not a whole number (#14)', (),
             merge(STORED, {'audio': {'leadin_seconds': 1.5}})),
            ('lead-in as text (#14)', (), merge(STORED, {'audio': {'leadin_seconds': '2'}})),
            ('lead-in 11, more than 10 seconds (#14)', ('--leadin-seconds', '11'), STORED),
            ('lead-in -1 on the command line (#14)', ('--leadin-seconds', '-1'), STORED),
            ('stored lead-in 11 (#14)', (), merge(STORED, {'audio': {'leadin_seconds': 11}})),
            ('empty audio file (#10)', (), prayer('fajr', file='')),
            ('audio file with %, which cron changes (#10)', (), prayer('isha', file='100%.mp3')),
            ('audio file with % on the command line (#10)', ('--audio', '100%.mp3'), STORED),
            ('audio file with #, which the crontab reads as a comment (#10)', (),
             prayer('isha', file='Adhan #2.mp3')),
            ('audio file with # and no space (#10)', ('--fajr-audio', 'Adhan#2.mp3'), STORED),
            ('audio file with a new line, which ends the cron job (#10)', (),
             merge(STORED, {'audio': {'file': 'Adhan\n.mp3'}})),
            ('audio file with a carriage return (#10)', ('--audio', 'Adhan\r.mp3'), STORED),
            ('audio file with a tab (#10)', ('--audio', 'Adhan\t.mp3'), STORED),
        ]
        for name, argv, stored in cases:
            with self.subTest(name):
                with self.assertRaises(app.ConfigError):
                    app.resolveSettings(args(*argv), stored)


class WriteSettingsTest(unittest.TestCase):
    """C5: the file that the app writes gives the same settings when it is read."""

    def test_the_written_file_gives_the_same_settings(self):
        """C5: write the settings, read them with tomllib, and get the same
        settings back. Also for the values that a TOML string must escape."""
        cases = [
            ('the defaults', app.resolveSettings(args(), ONLY_LOCATION)),
            ('every value changed', SETTINGS._replace(
                lat=-33.8688, lon=151.0, asr='Hanafi', surah_baqarah=True, surah_volume=-200,
                leadin=3, volume={'default': 500, 'fajr': -500, 'maghrib': 100},
                offsets=dict(NO_OFFSETS, fajr=5, isha=-10),
                enabled=dict(ALL_ON, dhuhr=False),
                audio=dict(DEFAULT_AUDIO, isha='/home/me/My "Isha" \\ adhan é.mp3'))),
            ('a whole number latitude', SETTINGS._replace(lat=10.0, lon=0.0)),
            ('a small latitude', SETTINGS._replace(lat=1e-05, lon=-1e-07)),
        ]
        for name, settings in cases:
            with self.subTest(name):
                text = app.settingsText(settings)
                self.assertEqual(app.resolveSettings(args(), tomllib.loads(text)), settings)

    def test_the_writer_gives_typed_values(self):
        """C5: numbers, booleans and text have their TOML types, in tables."""
        data = tomllib.loads(app.settingsText(SETTINGS))
        self.assertEqual(data['location'], {'lat': 12.8369, 'lon': 77.4089,
                                            'method': 'Karachi', 'asr': 'Standard'})
        self.assertEqual(data['audio'], {'player': 'paplay', 'leadin_seconds': 0,
                                         'volume': 500, 'file': 'Adhan-Makkah1.mp3'})
        self.assertEqual(data['prayers']['fajr'], {'file': 'Adhan-fajr.mp3', 'volume': -500,
                                                   'offset_minutes': 0, 'enabled': True})
        self.assertEqual(data['prayers']['isha'], {'offset_minutes': 0, 'enabled': True})
        self.assertEqual(data['surah_baqarah'], {'enabled': False, 'volume': 300})

    def test_the_writer_writes_toml(self):
        """C5: tomlText() writes the tables and values that tomllib reads back."""
        data = {'a': {'text': 'x "y" \\ z\u00e9', 'control': '\x7f\x01',
                      'whole': -3, 'float': 2.5, 'yes': True, 'no': False},
                'b': {'c': {'d': 1}, 'e': {}}}
        self.assertEqual(tomllib.loads(app.tomlText(data)), data)


if __name__ == '__main__':
    unittest.main()
