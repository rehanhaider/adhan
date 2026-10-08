#!/usr/bin/env python3

import datetime
import math
import time
import sys
from collections import namedtuple
from os.path import dirname, abspath, join as pathjoin
import argparse
import getpass
import os
import shlex
import shutil
import re
import subprocess
import tomllib


root_dir = dirname(abspath(__file__))
sys.path.insert(0, pathjoin(root_dir, 'crontab'))
from modules.praytimes import PrayTimes

from crontab import CronTab

# Players that playAzaan.sh knows how to drive, mapped to the command each one
# needs on PATH. Add a player here and a matching case in playAzaan.sh.
SUPPORTED_PLAYERS = {'vlc': 'cvlc', 'paplay': 'paplay'}
DEFAULT_PLAYER = 'vlc'

# The file of the settings, next to this script (#42). It is read with
# tomllib and written with tomlText().
SETTINGS_FILE = 'adhan.toml'

# Calculation methods that PrayTimes knows. The same list is used for the
# --method choices and to check a method edited by hand in adhan.toml.
SUPPORTED_METHODS = list(PrayTimes.methods)

# Asr schools that PrayTimes knows (#11). Hanafi uses a shadow factor of 2, so
# Asr is later. Standard is the default, so the times of today do not change.
SUPPORTED_ASR = ['Standard', 'Hanafi']
DEFAULT_ASR = 'Standard'

PRAYERS = ('fajr', 'dhuhr', 'asr', 'maghrib', 'isha')

# Seconds of silence that playAzaan.sh plays before the adhan, so that a
# speaker that is slow to wake up does not lose the start of it (#14). 0 adds
# no silence. More than MAX_LEADIN is probably a typo, and delays the adhan.
DEFAULT_LEADIN = 0
MAX_LEADIN = 10

# The adhan files and volumes when adhan.toml does not give one (#10).
# 'default' is for each prayer that has no value of its own. Fajr always has
# its own file and volume, so that a change of the default does not change
# Fajr. The volumes are in millibels, see playAzaan.sh.
DEFAULT_AUDIO = {'default': 'Adhan-Makkah1.mp3', 'fajr': 'Adhan-fajr.mp3'}
DEFAULT_VOLUME = {'default': 0, 'fajr': 0}

# The file of the Friday job (#9), in media/
SURAH_BAQARAH_FILE = '002-surah-baqarah-mishary.mp3'

# The tables and keys of adhan.toml, with the type of each value. A key that
# is not here stops the script, so that a typo cannot lose a value.
NUMBER = (int, float)
SCHEMA = {
    'location': {'lat': NUMBER, 'lon': NUMBER, 'method': str, 'asr': str},
    'audio': {'player': str, 'leadin_seconds': int, 'volume': int, 'file': str},
    'prayers': {name: {'file': str, 'volume': int, 'offset_minutes': int, 'enabled': bool}
                for name in PRAYERS},
    'surah_baqarah': {'enabled': bool, 'volume': int},
}
TYPE_NAMES = {NUMBER: 'a number', int: 'a whole number', bool: 'true or false',
              str: 'a text in double quotes'}

# The first lines of adhan.toml
SETTINGS_HEADER = ('# The settings of the adhan clock. See README.md.\n'
                   '# updateAzaanTimers.py writes this file again on each run, '
                   'so comments are lost.\n')

# Every job this script adds has this comment, so that the next run can remove
# them and leave the other jobs in the user's crontab alone.
JOB_COMMENT = 'rpiAdhanClockJob'

# Each line that this script and playAzaan.sh write to adhan.log starts with a
# timestamp in this format. Each update deletes the lines that are older than
# LOG_DAYS days (#7).
LOG_TIME_FORMAT = '%Y-%m-%d %H:%M:%S'
LOG_DAYS = 30

# After a reboot, the update waits for the clock to synchronize (#15): it asks
# timedatectl every TIME_SYNC_INTERVAL seconds, for at most TIME_SYNC_TIMEOUT
# seconds. On this Pi, NTP synchronizes about 40 seconds after the boot.
TIME_SYNC_TIMEOUT = 15 * 60
TIME_SYNC_INTERVAL = 5


class ConfigError(Exception):
    """A setting is missing or bad, or a prayer time cannot be calculated.

    main() prints it and exits 1 before it changes the crontab.
    """


Settings = namedtuple('Settings', [
    'lat', 'lon', 'method', 'asr',
    'volume',  # 'default' and the prayers that have their own volume, see prayerVolume()
    'surah_baqarah', 'surah_volume', 'player',
    'leadin',  # seconds of silence before each adhan
    'offsets',  # minutes to add to each prayer time, by prayer name
    'enabled',  # True for each prayer that has a job, by prayer name
    'audio'])  # 'default' and the prayers that have their own file, see audioFile()

# One cron job. A day or weekday of None means every day ('*'). A job with
# reboot runs once each time the Pi starts (@reboot), and has no time.
Job = namedtuple('Job', ['hour', 'minute', 'day', 'weekday', 'command', 'reboot'],
                 defaults=(False,))


def parseArgs():
    parser = argparse.ArgumentParser(description='Calculate prayer times and install cronjobs to play Adhan')
    parser.add_argument('--lat', type=float, dest='lat',
                        help='Latitude of the location, for example 30.345621')
    parser.add_argument('--lon', type=float, dest='lon',
                        help='Longitude of the location, for example 60.512126')
    parser.add_argument('--method', choices=SUPPORTED_METHODS,
                        dest='method',
                        help='Method of calculation')
    # No choices=: checkAsr() accepts any case, and checks adhan.toml too
    parser.add_argument('--asr', dest='asr', metavar='{' + ','.join(SUPPORTED_ASR) + '}',
                        help=f'Asr school, Hanafi gives a later Asr (default {DEFAULT_ASR})')
    parser.add_argument('--azaan-volume', type=int, dest='default_azaan_vol',
                        help='Volume for azaan (other than fajr) in millibels, 1500 is loud and -30000 is quiet (default 0)')
    parser.add_argument('--fajr-azaan-volume', type=int, dest='fajr_azaan_vol',
                        help='Volume for fajr azaan in millibels, 1500 is loud and -30000 is quiet (default 0)')
    parser.add_argument('--player', choices=sorted(SUPPORTED_PLAYERS), dest='player',
                        help=f'Program used to play the adhan (default {DEFAULT_PLAYER})')
    parser.add_argument('--leadin-seconds', type=int, dest='leadin', metavar='SECONDS',
                        help='Seconds of silence before the adhan, so that a slow speaker '
                             f'is awake when it starts, 0 to {MAX_LEADIN} (default {DEFAULT_LEADIN})')
    for name in PRAYERS:
        parser.add_argument(f'--{name}-offset', type=int, dest=f'{name}_offset', metavar='MINUTES',
                            help=f'Minutes to add to the {name} time, may be negative (default 0)')
    parser.add_argument('--audio', dest='default_audio', metavar='FILE',
                        help='Adhan file for each prayer that has no file of its own, in media/ '
                             f"or an absolute path (default {DEFAULT_AUDIO['default']})")
    for name in PRAYERS:
        parser.add_argument(f'--{name}-audio', dest=f'{name}_audio', metavar='FILE',
                            help=f'Adhan file for {name}, in media/ or an absolute path'
                                 + (f" (default {DEFAULT_AUDIO[name]})" if name in DEFAULT_AUDIO
                                    else ' (default: the file of --audio)'))
    for name in PRAYERS:
        parser.add_argument(f'--play-{name}', action=argparse.BooleanOptionalAction,
                            dest=f'{name}_enabled',
                            help=f'Play the {name} adhan or not (default: play)')
    parser.add_argument('--wait-for-time-sync', action='store_true', dest='wait_for_time_sync',
                        help='Wait until the clock is synchronized before the update. '
                             'The update after a reboot uses this')
    return parser


# CORE: pure functions, no I/O
# ---------------------------------
# ---------------------------------
def resolveSettings(args, stored):
    """Merge the command line (args) with adhan.toml (stored, as tomllib reads it).

    Each value comes from the command line, then adhan.toml, then the
    default. Returns Settings, or raises ConfigError.
    """
    checkSchema(stored)
    location = stored.get('location', {})
    audio = stored.get('audio', {})
    prayers = stored.get('prayers', {})
    surah = stored.get('surah_baqarah', {})

    def required(arg_value, key):
        value = location.get(key) if arg_value is None else arg_value
        if value is None:
            raise ConfigError(f"No {key} in [location] in {SETTINGS_FILE}, "
                              f"please provide --lat, --lon and --method")
        return value

    lat = checkCoordinate('latitude', float(required(args.lat, 'lat')), 90)
    lon = checkCoordinate('longitude', float(required(args.lon, 'lon')), 180)
    method = checkMethod(required(args.method, 'method'))
    asr = checkAsr(location.get('asr', DEFAULT_ASR) if args.asr is None else args.asr)

    # Player used by playAzaan.sh. A value edited by hand in adhan.toml is not
    # covered by argparse's choices, so validate it here too.
    player = (args.player or audio.get('player', DEFAULT_PLAYER)).strip().lower()
    if player not in SUPPORTED_PLAYERS:
        raise ConfigError(f"Unsupported player '{player}' in {SETTINGS_FILE}, "
                          f"use one of: {', '.join(sorted(SUPPORTED_PLAYERS))}")

    return Settings(
        lat, lon, method, asr,
        volume=readVolume(args, audio, prayers),
        surah_baqarah=surah.get('enabled', False),
        surah_volume=surah.get('volume', 0),
        player=player,
        leadin=readLeadin(args, audio),
        offsets={name: prayerValue(args, f'{name}_offset', prayers, name, 'offset_minutes', 0)
                 for name in PRAYERS},
        enabled={name: prayerValue(args, f'{name}_enabled', prayers, name, 'enabled', True)
                 for name in PRAYERS},
        audio=readAudio(args, audio, prayers))


def checkSchema(data, schema=SCHEMA, path=''):
    """Raise ConfigError on a key that is not in schema, or on a value of the
    wrong type, so that the whole file is correct before it is used."""
    for key, value in data.items():
        name = path + key
        if key not in schema:
            where = f'[{path[:-1]}]' if path else 'the top level'
            raise ConfigError(f"Unknown key '{name}' in {SETTINGS_FILE}, "
                              f"use one of these in {where}: {', '.join(schema)}")
        expected = schema[key]
        if isinstance(expected, dict):
            if not isinstance(value, dict):
                raise ConfigError(f"'{name}' in {SETTINGS_FILE} must be a table, [{name}]")
            checkSchema(value, expected, name + '.')
        # In Python, True is also an int, but in TOML true is not a number
        elif isinstance(value, bool) != (expected is bool) or not isinstance(value, expected):
            raise ConfigError(f"Invalid value {value!r} for '{name}' in {SETTINGS_FILE}, "
                              f"use {TYPE_NAMES[expected]}")


def prayerValue(args, arg_name, prayers, name, key, default):
  # The value of one key of one prayer, from the command line, then
  # [prayers.<name>] in adhan.toml, then default
  arg_value = getattr(args, arg_name)
  if arg_value is not None:
    return arg_value
  return prayers.get(name, {}).get(key, default)


def checkCoordinate(name, value, limit):
  # float() accepts 'nan' and 'inf', and PrayTimes gives wrong times or none at
  # all for values out of range. Stop before adhan.toml is saved so a bad
  # value is not saved and every nightly update after it does not fail on it too.
  if not math.isfinite(value) or not -limit <= value <= limit:
    raise ConfigError(f"Invalid {name} {value}, use a number from {-limit} to {limit}")
  return value


def checkMethod(method):
  # PrayTimes.setMethod() ignores a name it does not know and keeps calculating
  # with the previous method, so a typo gives wrong times and no error. Accept
  # any case (karachi) but return the canonical name, so that it is saved.
  canonical = {name.lower(): name for name in SUPPORTED_METHODS}
  name = canonical.get(method.strip().lower())
  if name is None:
    raise ConfigError(f"Unsupported method '{method}' in {SETTINGS_FILE}, "
                      f"use one of: {', '.join(SUPPORTED_METHODS)}")
  return name


def checkAsr(asr):
  # PrayTimes reads an unknown school as a shadow factor, and gives no error
  # for a typo. Accept any case (hanafi) but return the canonical name.
  canonical = {name.lower(): name for name in SUPPORTED_ASR}
  name = canonical.get(asr.strip().lower())
  if name is None:
    raise ConfigError(f"Unsupported asr '{asr}', use one of: {', '.join(SUPPORTED_ASR)}")
  return name


def readLeadin(args, audio):
  # The seconds of silence before the adhan (#14), from the command line, then
  # [audio] in adhan.toml, then DEFAULT_LEADIN. Stop on a value that is not
  # from 0 to MAX_LEADIN.
  leadin = audio.get('leadin_seconds', DEFAULT_LEADIN) if args.leadin is None else args.leadin
  if not 0 <= leadin <= MAX_LEADIN:
    raise ConfigError(f"Invalid lead-in '{leadin}', use a whole number of seconds "
                      f"from 0 to {MAX_LEADIN}")
  return leadin


def readVolume(args, audio, prayers):
  # The volumes, from the command line, then adhan.toml, then
  # DEFAULT_VOLUME. Keep 'default', 'fajr' and the other prayers that have a
  # volume of their own, so that a later change of 'default' still changes
  # them.
  volume = dict(DEFAULT_VOLUME)
  if 'volume' in audio:
    volume['default'] = audio['volume']
  for name in PRAYERS:
    if 'volume' in prayers.get(name, {}):
      volume[name] = prayers[name]['volume']
  if args.default_azaan_vol is not None:
    volume['default'] = args.default_azaan_vol
  if args.fajr_azaan_vol is not None:
    volume['fajr'] = args.fajr_azaan_vol
  return volume


def prayerVolume(volume, name):
  # The volume of the adhan of the prayer name
  return volume.get(name, volume['default'])


def readAudio(args, audio, prayers):
  # The adhan files (#10), from the command line, then adhan.toml, then
  # DEFAULT_AUDIO. Keep 'default', 'fajr' and the other prayers that have a
  # file of their own, so that a later change of 'default' still changes
  # them. main() checks that the files are there.
  stored = {'default': audio.get('file')}
  stored.update((name, prayers.get(name, {}).get('file')) for name in PRAYERS)
  files = {}
  for key in ('default',) + PRAYERS:
    value = getattr(args, f'{key}_audio')
    if value is None:
      value = stored[key] if stored[key] is not None else DEFAULT_AUDIO.get(key)
    if value is None:
      continue
    if not value:
      raise ConfigError(f"No audio file for {key} in {SETTINGS_FILE}")
    # cron changes % into a new line, and the crontab library reads # as the
    # start of the comment, so the next update would not find the job. A
    # control character such as a new line breaks the line of the job.
    if any(char in '%#' or not char.isprintable() for char in value):
      raise ConfigError(f"Invalid audio file {value!r} for {key}, a file name "
                        f"cannot have %, # or a control character")
    files[key] = value
  return files


def audioFile(audio, name, root_dir):
  # The path of the adhan file of the prayer name. A name is a file in
  # media/, and an absolute path is used as it is.
  value = audio.get(name, audio['default'])
  return value if os.path.isabs(value) else f"{root_dir}/media/{value}"


def settingsData(settings):
    """The settings as the tables of adhan.toml, in the order of the file."""
    prayers = {}
    for name in PRAYERS:
        table = prayers[name] = {}
        if name in settings.audio:
            table['file'] = settings.audio[name]
        if name in settings.volume:
            table['volume'] = settings.volume[name]
        table['offset_minutes'] = settings.offsets[name]
        table['enabled'] = settings.enabled[name]
    return {
        'location': {'lat': settings.lat, 'lon': settings.lon,
                     'method': settings.method, 'asr': settings.asr},
        'audio': {'player': settings.player, 'leadin_seconds': settings.leadin,
                  'volume': settings.volume['default'], 'file': settings.audio['default']},
        'prayers': prayers,
        'surah_baqarah': {'enabled': settings.surah_baqarah, 'volume': settings.surah_volume},
    }


def settingsText(settings):
    """The text of adhan.toml for settings."""
    return SETTINGS_HEADER + '\n' + tomlText(settingsData(settings))


def tomlText(data):
    """data, a dict of tables, as TOML text that tomllib reads back as data.

    The standard library of Python can read TOML but not write it. This small
    writer knows only what adhan.toml needs: tables, and text, whole numbers,
    floats and booleans in them. All the TOML that the app writes comes from
    here, so tomlkit can replace this function after #29.
    """
    blocks = []

    def table(name, values):
        lines = [f'{tomlKey(key)} = {tomlValue(value)}'
                 for key, value in values.items() if not isinstance(value, dict)]
        # A table that has only tables in it needs no header of its own
        if lines or not values:
            blocks.append('\n'.join([f'[{name}]'] + lines) + '\n')
        for key, value in values.items():
            if isinstance(value, dict):
                table(f'{name}.{tomlKey(key)}', value)

    for key, value in data.items():
        if not isinstance(value, dict):
            raise TypeError(f'{key}: the top level of adhan.toml has only tables')
        table(tomlKey(key), value)
    return '\n'.join(blocks)


def tomlKey(key):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', key):
        raise ValueError(f'{key!r} is not a bare TOML key')
    return key


def tomlValue(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f'{value} is not a TOML number that the app writes')
        return repr(value)
    if isinstance(value, str):
        # A basic string: escape the quote, the backslash and the control
        # characters, which TOML does not allow as they are
        return '"' + ''.join(
            '\\' + char if char in '"\\'
            else f'\\u{ord(char):04x}' if ord(char) < 0x20 or ord(char) == 0x7f
            else char
            for char in value) + '"'
    raise TypeError(f'{value!r} is not a type that the app writes to adhan.toml')


def prayerTimes(lat, lon, method, date, utcOffset, offsets=None, asr=DEFAULT_ASR):
    """The five prayer times of one day as 'HH:MM', by prayer name.

    utcOffset is in hours and includes daylight saving time. offsets has the
    minutes to add to each prayer (#12). asr is the Asr school (#11). Raises ConfigError if a time cannot
    be calculated.
    """
    calculator = PrayTimes(method)
    # Always set asr: PrayTimes keeps its settings in the class, so a Hanafi
    # calculation would otherwise change the next Standard one
    calculator.adjust({'asr': asr})
    if offsets:
        # PrayTimes adds the offsets before it rounds to the minute
        calculator.tune(offsets)
    times = calculator.getTimes((date.year, date.month, date.day), (lat, lon), utcOffset)

    # PrayTimes returns '-----' when a time cannot be calculated, which happens
    # at extreme latitudes. Stop before rescheduling anything rather than
    # crashing part way through, so the crontab that is already installed
    # keeps working.
    invalid = [name for name in PRAYERS if ':' not in times[name]]
    if invalid:
        raise ConfigError(f"Could not calculate a time for: {', '.join(invalid)}\n"
                          "Existing cron jobs have been left untouched.")
    return {name: times[name] for name in PRAYERS}


def buildJobs(times, settings, root_dir):
    """The cron jobs for the prayer times, and the jobs that keep them current."""
    # Playback goes through playAzaan.sh, which applies the configured volume,
    # runs the before/after hooks and plays the file with the configured player.
    strPlayer = f"{root_dir}/playAzaan.sh"
    strLog = f">> {root_dir}/adhan.log 2>&1"

    # Give the lead-in only when there is one, so that the jobs of an install
    # without a lead-in do not change (#14)
    leadin = f" {settings.leadin}" if settings.leadin else ""

    def play(path, volume):
        # quote, so that a path with a space is one argument
        return f"{strPlayer} {shlex.quote(path)} {volume} {settings.player}{leadin} {strLog}"

    jobs = []
    for name in PRAYERS:
        if not settings.enabled[name]:
            continue
        hour, minute = times[name].split(':')
        command = play(audioFile(settings.audio, name, root_dir),
                       prayerVolume(settings.volume, name))
        jobs.append(Job(int(hour), int(minute), None, None, command))
    if settings.surah_baqarah:
        jobs.append(Job(7, 0, None, 5,
                        play(f"{root_dir}/media/{SURAH_BAQARAH_FILE}",
                             settings.surah_volume)))
    # Run this script again overnight. It also deletes the old lines of the log.
    jobs.append(Job(3, 15, None, None, f"python3 {root_dir}/updateAzaanTimers.py {strLog}"))
    # And after each reboot, as the Pi can be off at 03:15. That update waits
    # for the clock first, because a Pi has no clock battery (#15).
    jobs.append(Job(None, None, None, None,
                    f"python3 {root_dir}/updateAzaanTimers.py --wait-for-time-sync {strLog}",
                    reboot=True))
    return jobs


def pruneLog(lines, today, days=LOG_DAYS):
    """The lines of adhan.log that are not older than days days.

    A line with no timestamp, for example a traceback, stays or goes with the
    timestamped line above it. Lines above the first timestamp (a log from
    before #7, or a traceback in a new log) stay or go with the first
    timestamped line below them, and a log with no timestamp stays. Lines with
    a date after today stay: a Pi without a clock battery can start with a
    date that is too early, and the prune must not then delete the recent
    lines.
    """
    first_day = today - datetime.timedelta(days=days)
    kept = []
    head = []  # the lines above the first timestamp
    keep = None  # None until the first timestamp
    for line in lines:
        day = logDate(line)
        if day is not None:
            if keep is None and day >= first_day:
                kept.extend(head)
            keep = day >= first_day
        if keep is None:
            head.append(line)
        elif keep:
            kept.append(line)
    return kept if keep is not None else head


def logDate(line):
    # The date of the timestamp at the start of the line, or None
    try:
        return datetime.datetime.strptime(line[:19], LOG_TIME_FORMAT).date()
    except ValueError:
        return None
# ---------------------------------
# ---------------------------------
# CORE END


# SHELL: reads and writes the crontab, adhan.toml and the system
# ---------------------------------
# ---------------------------------
def checkPlayer(player):
  # Note that CronTab.find_command() cannot do this: it searches existing cron
  # jobs, not PATH, and returns a generator (always truthy).
  # Fail loudly rather than fall back to another player: the configured player
  # is the one that will run at prayer time, so it is the one that must work.
  command = SUPPORTED_PLAYERS[player]
  if not shutil.which(command):
    raise ConfigError(f"Player '{player}' is selected but {command} was not found on PATH, "
                      f"please install it or choose another player with --player")
  if player == 'paplay':
    # paplay reads files through libsndfile, which only supports MP3 from 1.1
    formats = subprocess.run([command, '--list-file-formats'],
                             capture_output=True, text=True).stdout
    if not any(line.split('\t')[0] == 'm1a' for line in formats.splitlines()):
      raise ConfigError("paplay cannot play MP3 files on this system (libsndfile 1.1 or newer "
                        "is needed), please upgrade it or use --player vlc")


def checkAudio(settings, root_dir):
  # Stop before the save on an adhan file that is not there or cannot be
  # read, so that a typo cannot silence an adhan (#10). playAzaan.sh would
  # only find it at the time of the prayer. Only the prayers that are on
  # play a file, and the Surah Baqarah file only when it is on.
  files = [(name, audioFile(settings.audio, name, root_dir))
           for name in PRAYERS if settings.enabled[name]]
  if settings.surah_baqarah:
    files.append(('Surah Baqarah', f"{root_dir}/media/{SURAH_BAQARAH_FILE}"))
  for name, path in files:
    if not (os.path.isfile(path) and os.access(path, os.R_OK)):
      raise ConfigError(f"The audio file for {name} is not there or cannot be read: {path}")


def readSettingsFile(path):
    """adhan.toml as tomllib reads it, or {} if there is no file yet."""
    try:
        with open(path, 'rb') as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as err:
        raise ConfigError(f"{path} is not a correct TOML file: {err}") from err


def saveSettings(settings, file_path):
    # Write all the settings, so that the nightly update uses the values of
    # the command line too
    with open(file_path, 'w') as fh:
        fh.write(settingsText(settings))


def log(text=''):
    """Print text for adhan.log, with the date and time before each line."""
    stamp = datetime.datetime.now().strftime(LOG_TIME_FORMAT)
    for line in str(text).split('\n'):
        # flush, so that the lines stay in order with a traceback on stderr
        print(f'{stamp} {line}'.rstrip(), flush=True)


def pruneLogFile(path, today):
    """Delete the lines of the log that pruneLog() does not keep, in place.

    Change the same file. Do not write a new file and rename it: the cron job
    that runs this script adds its output to the log with >> (O_APPEND), and
    after a rename that output goes to the old file, which is deleted.
    """
    # surrogateescape and newline='' write back the lines that stay byte for
    # byte, also when a player wrote bytes that are not UTF-8
    with open(path, 'r+', encoding='utf-8', errors='surrogateescape', newline='') as fh:
        lines = fh.readlines()
        kept = pruneLog(lines, today)
        if kept != lines:
            fh.seek(0)
            fh.write(''.join(kept))
            fh.truncate()


def applyJobs(cron, jobs):
    """Replace the jobs of this script in cron with jobs. Other jobs stay."""
    cron.remove_all(comment=JOB_COMMENT)
    added = []
    for job in jobs:
        item = cron.new(command=job.command, comment=JOB_COMMENT)
        if job.reboot:
            item.every_reboot()
        else:
            item.minute.on(job.minute)
            item.hour.on(job.hour)
            if job.day is not None:
                item.day.on(job.day)
            if job.weekday is not None:
                item.dow.on(job.weekday)
        added.append(item)
    return added


def waitForTimeSync(timeout, interval=TIME_SYNC_INTERVAL):
    """Wait until timedatectl says that the clock is synchronized.

    Return True when it is, or False after timeout seconds or if timedatectl
    is not there. A Pi has no clock battery: at boot, fake-hwclock sets the
    time that it saved last, and the date is wrong until NTP synchronizes it.
    """
    # monotonic, because the clock jumps when it synchronizes
    deadline = time.monotonic() + timeout
    while True:
        try:
            # It can fail early in the boot. Then ask again.
            answer = subprocess.run(['timedatectl', 'show', '-p', 'NTPSynchronized', '--value'],
                                    capture_output=True, text=True, timeout=30).stdout
        except FileNotFoundError:
            log("timedatectl was not found, so the script cannot know if the clock is correct")
            return False
        except subprocess.TimeoutExpired:
            answer = ''
        if answer.strip() == 'yes':
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            log(f"The clock did not synchronize in {timeout} seconds")
            return False
        time.sleep(min(interval, remaining))


def systemUtcOffset():
    # The system timezone in hours, plus 1 while daylight saving time is on
    return -(time.timezone/float(3600)) + (1 if time.localtime().tm_isdst else 0)


def main(argv=None, settings_path=None, cron=None, today=None, utcOffset=None,
         log_path=None, sync_timeout=None):
    """Delete the old lines of the log, calculate today's prayer times and
    replace the jobs of this script.

    Every argument defaults to the real one: the command line, adhan.toml
    next to this script, the user's crontab, today, the system timezone,
    adhan.log next to this script and TIME_SYNC_TIMEOUT.
    On a ConfigError, print it and exit 1 before the crontab is changed. With
    --wait-for-time-sync, if the clock does not synchronize, exit 1 too.
    """
    if settings_path is None:
        settings_path = pathjoin(root_dir, SETTINGS_FILE)
    if log_path is None:
        log_path = pathjoin(root_dir, 'adhan.log')
    if sync_timeout is None:
        sync_timeout = TIME_SYNC_TIMEOUT

    # An error that Python or argparse writes has no timestamp. After this
    # line, it stays with this run when the log is pruned.
    log("Updating the prayer times")
    args = parseArgs().parse_args(argv)

    # The date and the timezone offset come from the clock, so get them after
    # the wait. Without the clock, keep the schedule that is installed (#15).
    if args.wait_for_time_sync:
        if not waitForTimeSync(sync_timeout):
            log("The prayer times were not updated. The 03:15 update will update them.")
            sys.exit(1)
        log("The clock is synchronized")
    if cron is None:
        cron = CronTab(user=getpass.getuser())
    if today is None:
        today = datetime.date.today()
    if utcOffset is None:
        utcOffset = systemUtcOffset()

    # A log with a problem must never stop the schedule (C4 in #16), so catch
    # any error and continue. The lines above are from this run, so they stay.
    try:
        pruneLogFile(log_path, today)
    except FileNotFoundError:
        pass
    except Exception as err:
        log(f"Could not delete the old lines of {log_path}: {err}")

    try:
        settings = resolveSettings(args, readSettingsFile(settings_path))
        # Check the player is usable before it is saved, so a failed --player
        # change does not leave every nightly update failing on the same value
        checkPlayer(settings.player)
        checkAudio(settings, root_dir)
        # Calculate the times before the save too, so a location where a time
        # cannot be calculated is not saved for the nightly update (#31)
        times = prayerTimes(settings.lat, settings.lon, settings.method, today, utcOffset,
                            settings.offsets, settings.asr)
        saveSettings(settings, settings_path)
    except ConfigError as err:
        log(err)
        sys.exit(1)

    log("---------------------------------")
    log("Co-ordinates provided")
    log("---------------------------------")
    log(f"Latitude:   {settings.lat} \nLongitude:  {settings.lon} \nMethod:     {settings.method} \nAsr school: {settings.asr} \nPlayer:     {settings.player} \nLead-in:    {settings.leadin} seconds")
    log("---------------------------------")
    log()
    log("---------------------------------")
    log("Prayer Times")
    log("---------------------------------")
    for name in PRAYERS:
        notes = []
        if settings.offsets[name]:
            notes.append(f"offset {settings.offsets[name]:+d} minutes")
        if not settings.enabled[name]:
            notes.append("not scheduled")
        note = f" ({', '.join(notes)})" if notes else ""
        log(f"{name.capitalize() + ':':<9}{times[name]} hrs{note}")
    log("---------------------------------")
    if not any(settings.enabled.values()):
        log(f"All five prayers are off in {SETTINGS_FILE}, so no adhan is scheduled.")

    # Add times to crontab
    log()
    log("---------------------------------")
    log("Cron jobs scheduled")
    log("---------------------------------")
    for job in applyJobs(cron, buildJobs(times, settings, root_dir)):
        log(job)
    log("---------------------------------")

    cron.write()
    log('Script execution finished at: ' + str(datetime.datetime.now()))
# ---------------------------------
# ---------------------------------
# SHELL END


if __name__ == "__main__":
    main()
