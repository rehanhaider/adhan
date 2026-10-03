#!/usr/bin/env python3

import datetime
import time
import sys
from os.path import dirname, abspath, join as pathjoin
import argparse
import getpass
import shutil
import subprocess
from configparser import ConfigParser


root_dir = dirname(abspath(__file__))
sys.path.insert(0, pathjoin(root_dir, 'crontab'))
from modules.praytimes import PrayTimes
PT = PrayTimes() 

from crontab import CronTab
system_cron = CronTab(user=getpass.getuser())

# Players that playAzaan.sh knows how to drive, mapped to the command each one
# needs on PATH. Add a player here and a matching case in playAzaan.sh.
SUPPORTED_PLAYERS = {'vlc': 'cvlc', 'paplay': 'paplay'}
DEFAULT_PLAYER = 'vlc'


# HELPER FUNCTIONS
# ---------------------------------
# ---------------------------------
# Function to add azaan time to cron
def parseArgs():
    parser = argparse.ArgumentParser(description='Calculate prayer times and install cronjobs to play Adhan')
    parser.add_argument('--lat', type=float, dest='lat',
                        help='Latitude of the location, for example 30.345621')
    parser.add_argument('--lon', type=float, dest='lon',
                        help='Longitude of the location, for example 60.512126')
    parser.add_argument('--method', choices=['MWL', 'ISNA', 'Egypt', 'Makkah', 'Karachi', 'Tehran', 'Jafari'],
                        dest='method',
                        help='Method of calculation')
    parser.add_argument('--azaan-volume', type=int, dest='default_azaan_vol',
                        help='Volume for azaan (other than fajr) in millibels, 1500 is loud and -30000 is quiet (default 0)')
    parser.add_argument('--fajr-azaan-volume', type=int, dest='fajr_azaan_vol',
                        help='Volume for fajr azaan in millibels, 1500 is loud and -30000 is quiet (default 0)')
    parser.add_argument('--player', choices=sorted(SUPPORTED_PLAYERS), dest='player',
                        help=f'Program used to play the adhan (default {DEFAULT_PLAYER})')
    return parser

def getConfig():
    # Parse arguments
    parser = parseArgs()
    args = parser.parse_args()

    
    # Initialise and read config file if present
    config = ConfigParser()
    file_path = pathjoin(root_dir, 'settings.ini')
    config.read(file_path)

    lat = lon = method = fajr_azaan_vol = default_azaan_vol = surahBaqarah = surahVolume = player = None

    # Get mandatory data. First check args, if not present check settings.ini
    try:
        if args.lat:
            lat = float(args.lat)
            config['DEFAULT']['lat'] = str(lat)
        else:
            lat = float(config['DEFAULT']['lat'])
        
        if args.lon:
            lon = float(args.lon)
            config['DEFAULT']['lon'] = str(lon)
        else:
            lon = float(config['DEFAULT']['lon'])

        if args.method:
            method = args.method
            config['DEFAULT']['method'] = method
        else:
            method = config['DEFAULT']['method']
    except (KeyError, ValueError) as err:
        print(f"Incorrect value or values not provided: {err}")
        lat = lon = method = None


    # Get optional data
    try:
        if args.default_azaan_vol:
            default_azaan_vol = int(args.default_azaan_vol)
        else:
            default_azaan_vol = int(config['VOLUME']['defaultAzaanVolume'])

        if args.fajr_azaan_vol:
            fajr_azaan_vol = int(args.fajr_azaan_vol)
        else:
            fajr_azaan_vol = int(config['VOLUME']['fajrAzaanVolume'])
    except (KeyError, ValueError) as err:
        print(f"Using default volumes, could not read configured ones: {err}")
        default_azaan_vol = 0
        fajr_azaan_vol = 0

        
    config["VOLUME"] = {
        "defaultAzaanVolume": str(default_azaan_vol), 
        "fajrAzaanVolume": str(fajr_azaan_vol)
        }


    # Setup Surah Baqarah on Fridays
    try:
        # getboolean, not bool(): bool() on the string "False" is True
        surahBaqarah = config['FRIDAY'].getboolean('playSurahBaqarah', fallback=False)
        surahVolume = int(config['FRIDAY']['surahVolume'])
    except (KeyError, ValueError) as err:
        print(f"Surah Baqarah not configured, disabling it: {err}")
        surahBaqarah = False
        surahVolume = 0
        config["FRIDAY"] = {"playSurahBaqarah": str(surahBaqarah), "surahVolume": str(surahVolume)}
    

    # Player used by playAzaan.sh. A value edited by hand in settings.ini is not
    # covered by argparse's choices, so validate it here too.
    if args.player:
        player = args.player
    else:
        player = config.get('PLAYER', 'player', fallback=DEFAULT_PLAYER).strip().lower()
    if player not in SUPPORTED_PLAYERS:
        print(f"Unsupported player '{player}' in settings.ini, "
              f"use one of: {', '.join(sorted(SUPPORTED_PLAYERS))}")
        sys.exit(1)
    config["PLAYER"] = {"player": player}


    # If any of the mandatory values not provided or configures in settings.ini, exit and show usage
    if lat is None or lon is None or not method:
        print("No values provided, please provide values as per below usage")
        parser.print_usage()
        sys.exit(1)

    # save values to settings.ini
    with open(file_path, 'w') as configfile:
        config.write(configfile)

    return lat, lon, method, fajr_azaan_vol, default_azaan_vol, surahBaqarah, surahVolume, player


def checkPlayer(player):
  # Fail loudly rather than fall back to another player: the configured player
  # is the one that will run at prayer time, so it is the one that must work.
  command = SUPPORTED_PLAYERS[player]
  if not shutil.which(command):
    print(f"Player '{player}' is selected but {command} was not found on PATH, "
          f"please install it or choose another player with --player")
    sys.exit(1)
  if player == 'paplay':
    # paplay reads files through libsndfile, which only supports MP3 from 1.1
    formats = subprocess.run([command, '--list-file-formats'],
                             capture_output=True, text=True).stdout
    if not any(line.split('\t')[0] == 'm1a' for line in formats.splitlines()):
      print("paplay cannot play MP3 files on this system (libsndfile 1.1 or newer "
            "is needed), please upgrade it or use --player vlc")
      sys.exit(1)


def addAzaanTime (strPrayerName, strPrayerTime, objCronTab, strCommand):
  job = objCronTab.new(command=strCommand,comment=strPrayerName)
  timeArr = strPrayerTime.split(':')
  hour = timeArr[0]
  minute = timeArr[1]
  job.minute.on(int(minute))
  job.hour.on(int(hour))
  job.set_comment(strJobComment)
  print(job)
  return

def addFriday(strSurahName, objCronTab, strCommand):
  job = objCronTab.new(command=strCommand,comment=strSurahName)
  job.minute.on(0)
  job.hour.on(7)
  job.dow.on(5)
  job.set_comment(strJobComment)
  print(job)
  return

def addUpdateCronJob (objCronTab, strCommand):
  job = objCronTab.new(command=strCommand)
  job.minute.on(15)
  job.hour.on(3)
  job.set_comment(strJobComment)
  print(job)
  return

def addClearLogsCronJob (objCronTab, strCommand):
  job = objCronTab.new(command=strCommand)
  job.day.on(1)
  job.minute.on(0)
  job.hour.on(0)
  job.set_comment(strJobComment)
  print(job)
  return
# ---------------------------------
# ---------------------------------
# HELPER FUNCTIONS END
# Merge args with saved values if any
lat, lon, method, fajr_azaan_vol, default_azaan_vol, surahBaqarah, surahVolume, player = getConfig()
# Set calculation method, utcOffset and dst here
# By default system timezone will be used
# --------------------
PT.setMethod(method)
utcOffset = -(time.timezone/float(3600))
isDst = time.localtime().tm_isdst

now = datetime.datetime.now()
# Check the configured player is actually usable. Note that
# CronTab.find_command() cannot do this: it searches existing cron jobs, not
# PATH, and returns a generator (always truthy), so it never reported anything.
checkPlayer(player)

# Playback goes through playAzaan.sh, which applies the configured volume,
# runs the before/after hooks and plays the file with the configured player.
strPlayer = f"{root_dir}/playAzaan.sh"
strLog = f">> {root_dir}/adhan.log 2>&1"
strPlayFajrAzaanMP3Command = f"{strPlayer} {root_dir}/media/Adhan-fajr.mp3 {fajr_azaan_vol} {player} {strLog}"
strPlayAzaanMP3Command = f"{strPlayer} {root_dir}/media/Adhan-Makkah1.mp3 {default_azaan_vol} {player} {strLog}"
strSurahBaqarahMP3Command = f"{strPlayer} {root_dir}/media/002-surah-baqarah-mishary.mp3 {surahVolume} {player} {strLog}"
strUpdateCommand = f"python3 {root_dir}/updateAzaanTimers.py {strLog}"
strClearLogsCommand = f"truncate -s 0 {root_dir}/adhan.log 2>&1"
strJobComment = "rpiAdhanClockJob"

# Calculate prayer times
times = PT.getTimes((now.year,now.month,now.day), (lat, lon), utcOffset, isDst)

# PrayTimes returns '-----' when a time cannot be calculated, which happens at
# extreme latitudes. Bail out before rescheduling anything rather than crashing
# part way through, so the crontab that is already installed keeps working.
prayers = ('fajr', 'dhuhr', 'asr', 'maghrib', 'isha')
invalid = [name for name in prayers if ':' not in times[name]]
if invalid:
    print(f"Could not calculate a time for: {', '.join(invalid)}")
    print("Existing cron jobs have been left untouched.")
    sys.exit(1)

# Remove existing jobs created by this script
system_cron.remove_all(comment=strJobComment)
print("---------------------------------")
print("Co-ordinates provided")
print("---------------------------------")
print(f"Latitude:   {lat} \nLongitude:  {lon} \nMethod:     {method} \nPlayer:     {player}")
print("---------------------------------")
print()
print("---------------------------------")
print("Prayer Times")
print("---------------------------------")
print(f"Fajr:    {times['fajr']} hrs")
print(f"Dhuhr:   {times['dhuhr']} hrs")
print(f"Asr:     {times['asr']} hrs")
print(f"Maghrib: {times['maghrib']} hrs")
print(f"Isha:    {times['isha']} hrs")
print("---------------------------------")

# Add times to crontab
print()
print("---------------------------------")
print("Crob jobs scheduled")
print("---------------------------------")
addAzaanTime('fajr',times['fajr'],system_cron,strPlayFajrAzaanMP3Command)
addAzaanTime('dhuhr',times['dhuhr'],system_cron,strPlayAzaanMP3Command)
addAzaanTime('asr',times['asr'],system_cron,strPlayAzaanMP3Command)
addAzaanTime('maghrib',times['maghrib'],system_cron,strPlayAzaanMP3Command)
addAzaanTime('isha',times['isha'],system_cron,strPlayAzaanMP3Command)
if surahBaqarah == True:
    addFriday('Surah Baqarah', system_cron, strSurahBaqarahMP3Command)
print("---------------------------------")
print()
# Run this script again overnight
addUpdateCronJob(system_cron, strUpdateCommand)

# Clear the logs every month
addClearLogsCronJob(system_cron,strClearLogsCommand)

system_cron.write_to_user(user=getpass.getuser())
print('Script execution finished at: ' + str(now))

