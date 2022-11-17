import logging
from beam import exceptions, ratelimiting
from beam.players import Player, PlayerPool
import uuid
import random
import string
import messages

"""
Classes for the servers.
"""


class Server(Player):
    def __init__(self, code: str, limit: int):
        self.code = code
        self.token = str(uuid.uuid4())

        self.p2pmode = False

        self.client = None

        self.players = PlayerPool()
        self.lock = False
        self.limit = limit

        self.owner_ip = None
        self.rate_limit = ratelimiting.RoomJoinLimiting()

        logging.debug(f"Initialized new Server instance: {self.code}")

    # Add a Player to the PlayerPool
    def add_user(self, player: Player):
        if not player.name in self.players:
            message = messages.UserJoin(player)
            self.client.write_message(message)
            if self.p2pmode:
                for p in self.players.list():
                    p.write_message(message)
            self.players[player.name] = player
            logging.debug(f"Server {self.code} adds new player {player}")
        else:
            logging.error(
                f"Server {self.code} tried to add player {player} but the name is taken. Did an earlier check fail?")

    # Check for a Player in PlayerPool, return None if not found
    def get_player_safe(self, player_name):
        if not player_name in self.players:
            return None
        else:
            return self.players[player_name]

    # Disconnect everyone and send a specific close code
    def close_server(self):
        logging.debug(f"Server {self.code} closes all connections")

        for player in self.players.list():
            try:
                player.client.close(exceptions.ServerClosing())
            except:
                logging.debug(
                    f"Couldn't close connection with {player.name}, the user is likely away.")
        try:
            self.client.close(exceptions.ServerClosing())
        except:
            logging.debug(
                f"Couldn't close connection with server's owner, the user is likely away.")


class ServerPool:
    """
    Holder for Server classes.
    """

    def __init__(self):
        self.pool = {}

    def __contains__(self, what):
        return what in self.pool

    def _gen_code(self, prefix: str):
        x = "".join(random.choices(string.ascii_uppercase, k=4))
        if not prefix+x in self:
            return x
        else:
            return None

    def create_server(self, limit: int, prefix=""):
        code = None
        while not code:
            code = self._gen_code(prefix)

        self.pool[prefix+code] = Server(prefix+code, limit)
        return self.pool[prefix+code]

    def get_server_safe(self, server):
        if not server in self.pool:
            return None
        else:
            return self.pool[server]

    def free(self, server):
        if not server in self.pool:
            logging.error(
                f"ServerPool tried to free {server}, but this server is not present. Did an earlier check fail?")
        else:
            self.pool.pop(server)
