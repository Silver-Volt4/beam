from asyncio import exceptions
from typing import List
from beam import messages
import uuid
import json
import logging


class Client:
    def __init__(self, client) -> None:
        self.client = client
        self.token = str(uuid.uuid4())

        self.queue = []
    
    # This is used when something sends a message TO this player
    def write_message(self, message):
        try:
            self.client.write_message(json.dumps(message))
        except:
            self.queue.append(message)

    # This is used when THIS PLAYER sends something to someone else
    def sends_message(self, to, content):
        if isinstance(to, PlayerPool):
            for recipient in to.list():
                self.sends_message(recipient, content)
        else:
            to.write_message(content)
    
    def assign(self, client):
        try:
            self.client.close(code=exceptions.Overridden())
        except:
            pass

        self.client = client
        while len(self.queue) > 0:
            self.write_message(self.queue.pop(0))


class Player(Client):
    """
    A member of a game room.
    """

    def __init__(self, name: str, client):
        super().__init__(client)
        self.name = str(name)


class PlayerPool:
    """
    Holder class for a list of players connected to a server.
    """

    def __init__(self):
        self.players = {}

    # For subscript access
    def __setitem__(self, player_name, player):
        self.players[player_name] = player

    def __getitem__(self, player_name):
        return self.players[player_name]

    # For x in y access
    def __contains__(self, what):
        return what in self.players

    def list(self) -> List[Player]:
        return list(self.players.values())

    def count(self):
        return len(self.players)
