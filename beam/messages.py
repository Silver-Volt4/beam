from beam.players import Player

"""
Holder classes for all message types we currently support.
"""


class RawMessage:
    """
    Class for user-sent messages, these are always
    from someone else, not Beam itself
    """

    def __init__(self, from_: Player, message_content):
        self.from_ = from_
        self.message_content = message_content

    def repr(self):
        return {
            "type": "msg",
            "from": self.from_.name,
            "am": self.message_content
        }


class UserAppend:
    """
    Sent to the owner when a player enters the game for the first time,
    their name should be appended to some kind of dictionary
    on the server owner's end
    """

    def __init__(self, user: Player):
        self.user = user

    def repr(self):
        return {
            "type": "userappend",
            "user": self.user.name
        }


class UserJoin:
    """
    Sent to the owner when an already registered player joins the game back,
    presumably after being disconnected or when switching devices
    """

    def __init__(self, user: Player):
        self.user = user

    def repr(self):
        return {
            "type": "userjoin",
            "user": self.user.name
        }


class UserLeft:
    """
    Sent to the owner when an already registered player disconnects abnormally,
    presumably after network problems
    """

    def __init__(self, user: Player):
        self.user = user

    def repr(self):
        return {
            "type": "userleft",
            "user": self.user.name
        }


class Su:
    """
    Sent to every newly registered player, this code is used for
    authentication later on, for instance when reconnecting
    """

    def __init__(self, su: str):
        self.su = su

    def repr(self):
        return {
            "type": "su",
            "su": self.su
        }