from modules.praytimes import PrayTimes


def get_username():
    from getpass import getuser

    username = getuser()
    return username
