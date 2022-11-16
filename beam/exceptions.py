"""
This is just a holder for returning error codes and whatnot.
Because .close(code=ServerCodeDoesntExist()) makes more sense than .close(code=4000)
"""

import logging
BASE = 4000


def ServerCodeDoesntExist():
    logging.debug(f"exception: ServerCodeDoesntExist")
    return BASE + 0


def ServerIsLocked():
    logging.debug(f"exception: ServerIsLocked")
    return BASE + 1


def NameIsTaken():  # This one happens when you're trying to register and the name is taken
    logging.debug(f"exception: NameIsTaken")
    return BASE + 2


def NameDoesntExist():  # This one happens when you supply a token code in the login
    logging.debug(f"exception: # NameDoesntExist")
    return BASE + 3


def SuCodeMismatch():
    logging.debug(f"exception: SuCodeMismatch")
    return BASE + 4


def SuAdminCodeMismatch():
    logging.debug(f"exception: SuAdminCodeMismatch")
    return BASE + 5


def NamePropertyIsEmpty():
    logging.debug(f"exception: NamePropertyIsEmpty")
    return BASE + 6


def RoomLimitReached():
    logging.debug(f"exception: RoomLimitReached")
    return BASE + 7


def Overridden():
    logging.debug(f"exception: Overridden")
    return BASE + 10


def BreakingApiChange():
    logging.debug(f"exception: BreakingApiChange")
    return BASE + 19


def ServerClosing():
    logging.debug(f"exception: ServerClosing")
    return BASE + 20


def BannedByRateLimit():
    return BASE + 30
