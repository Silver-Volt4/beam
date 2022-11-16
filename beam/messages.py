from typing import List
from beam.players import Player

def Message(from_: Player, data):
    """
    For user-sent messages, these are always
    from someone else, not Beam itself
    """

    return {
        "type": "msg",
        "from": from_.name,
        "data": data
    }

def UsersList(users: List[Player]):
    return {
        "type": "users",
        "list": [u.name for u in users]
    }

def UserJoin(user: Player):
    """
    Sent to the owner when a player enters the game for the first time,
    their name should be appended to some kind of dictionary
    on the server owner's end
    """

    return {
        "type": "joined",
        "name": user.name
    }


def UserConnected(user: Player):
    """
    Sent to the owner when an already registered player joins the game back,
    presumably after being disconnected or when switching devices
    """

    return {
        "type": "connected",
        "name": user.name
    }


def UserDisconnected(user: Player):
    """
    Sent to the owner when an already registered player disconnects abnormally,
    presumably after network problems
    """

    return {
        "type": "disconnected",
        "name": user.name
    }


def Token(token: str):
    """
    Sent to every newly registered player, this code is used for
    authentication later on, for instance when reconnecting
    """

    return {
        "type": "token",
        "token": token
    }
