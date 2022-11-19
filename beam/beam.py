import asyncio
import tornado.escape
import tornado.template
import tornado.web
import tornado.websocket

from beam import messages, ratelimiting, exceptions
from beam.servers import Server, ServerPool
from beam.players import Player
from beam.exceptions import BASE

import logging
import json
import time

BEAM_VERSION = "v0"


class Beam(tornado.web.Application):
    """
    Main object for the Tornado server.
    """

    def __init__(self, do_inspect, **kwargs):
        self.pool = ServerPool()
        self.html = tornado.template.Loader("./html")

        self.rate_limits = ratelimiting.RoomCreateLimiting()

        self.MAX_SERVERS = kwargs.get("max_servers", 3)

        self.MAX_USERS = kwargs.get("max_users", 3)
        self.PER_N_SECONDS = kwargs.get("per_n_seconds", 1)
        self.BAN_FOR = kwargs.get("ban_for", 200)

        handlers = [
            ("/ws/(.*)", BeamWebsocket),
            ("/beam/(.*)",   BeamCommands)
        ]

        if do_inspect:
            handlers.append(
                ("/inspect(.*)", BeamInspector)
            )

        super().__init__(handlers)

    def delete_server(self, server):
        self.rate_limits.ip_deown(server.owner_ip)
        server.close_server()
        self.pool.free(server.code)
        logging.info(f"Closed server: {server.code}")

    async def delete_on_inactive(self, server):
        logging.info(f"Waiting 90 seconds to close: {server.code}")
        await asyncio.sleep(90)
        self.delete_server(server)


###          ###
### HANDLERS ###
###          ###


class BeamInspector(tornado.web.RequestHandler):
    """
    Object for the optional Beam inspector.
    Currently lacks authentication, but it can be turned off.
    """

    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "x-requested-with")
        self.set_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')

    def get(self, cmd):
        logging.debug("Handling request BeamInspector/" +
                      self.request.path)

        if not cmd.startswith("/"):
            cmd = "/" + cmd
        cmd = cmd.split("/")[1:]

        if cmd[0] == "":
            s = list(self.application.pool.pool.values())
            self.write(self.application.html.load(
                "home.html").generate(a="x", servers=s))

        else:
            serv = self.application.pool.get_server_safe(cmd[0])
            if serv:
                pass  # TODO
            else:
                self.set_status(404)
                self.write("Not found")


class BeamCommands(tornado.web.RequestHandler):
    """
    Object for the /beam endpoint.
    This is where apps ask for new servers, delete them...
    """

    def prepare(self):
        logging.debug("Handling request BeamCommands/" + self.path_args[0])
        if not self.path_args[0].startswith(BEAM_VERSION + "/"):
            self.set_status(400)
            self.write({
                "error": "version incompatible"
            })

    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "x-requested-with")
        self.set_header('Access-Control-Allow-Methods', 'POST, DELETE')

    def post(self, cmd):
        if self._status_code == 400:
            return
        if cmd.endswith("server"):
            if self.application.rate_limits.check_ip_owns(self.request.remote_ip) >= self.application.MAX_SERVERS:
                self.write({
                    "error": "you have reached the limit of rooms for your IP address. please remove other servers first"
                })
            else:
                limit = int(self.get_argument("limit", -1))
                if limit < 0:
                    limit = -1

                prefix = self.get_argument("prefix", "")

                server = self.application.pool.create_server(limit, prefix)
                game_code = server.code
                token = server.token
                server.owner_ip = self.request.remote_ip
                logging.info(f"Created new Server: {game_code}")
                self.application.rate_limits.ip_own(server.owner_ip)
                server.close_task = asyncio.create_task(self.application.delete_on_inactive(server))
                self.set_status(201)
                self.write({
                    "code": game_code[-4:],
                    "token": token
                })
        else:
            self.set_status(404)

    def delete(self, cmd):
        if self._status_code == 400:
            return
        if cmd.endswith("server"):
            server = self.application.pool.get_server_safe(
                self.get_argument("code"))
            if server:
                if server.token == self.get_argument("token"):
                    self.application.delete_server(server)
                    self.set_status(200)
                else:
                    self.set_status(401)
            else:
                self.set_status(404)
        else:
            self.set_status(404)


class BeamWebsocket(tornado.websocket.WebSocketHandler):
    """
    Main object for the WebSocket endpoint itself.
    This is where actual communication happens.
    """

    def __init__(self, application, request, **kwargs) -> None:
        super().__init__(application, request, **kwargs)
        self.code = None
        self.player_name = None
        self.token = None

        self.server = None
        self.player = None

    def parse_args(self):
        self.code = self.get_argument("code")
        self.player_name = self.get_argument("name", None)
        self.token = self.get_argument("token", None)

    def check_origin(self, origin):
        # VERY UNSAFE. This should get a tweak as soon as possible!!!
        return True

    def get_compression_options(self):
        # Non-None enables compression with default options
        return {}

    def open(self, client):
        logging.debug("Handling request BeamWebsocket/" +
                      self.path_args[0])
        if not self.path_args[0] == BEAM_VERSION:
            self.close(code=exceptions.BreakingApiChange())
            return

        self.parse_args()

        # Check for errors in the connection and kick the client if necessary
        server = self.application.pool.get_server_safe(self.code)
        if not server:
            self.close(code=exceptions.ServerCodeDoesntExist())
            return

        self.server = server
        player = self.server.get_player_safe(self.player_name)

        registering = self.player_name and not self.token
        logging_in = self.player_name and self.token
        owner_connecting = self.token and not self.player_name

        if registering:
            if self.server.lock:
                self.close(code=exceptions.ServerIsLocked())
                return

            elif self.server.players.count() == self.server.limit:
                self.close(code=exceptions.RoomLimitReached())
                return

            elif player:
                self.close(code=exceptions.NameIsTaken())
                return

            elif self.player_name == "":
                self.close(code=exceptions.NamePropertyIsEmpty())
                return

            else:
                # Check for spam and ban if necessary
                request_time = time.time()
                ratelimit = self.server.rate_limit.get_ratelimit_data(
                    self.request.remote_ip)

                if request_time > ratelimit.banned_until:
                    ratelimit.banned_until = 0
                    logging.debug("Lift ban")
                else:
                    self.close(code=exceptions.BannedByRateLimit())
                    return

                if request_time - ratelimit.striking_test < self.application.PER_N_SECONDS:
                    ratelimit.strike += 1
                    logging.debug("Award strike")
                    if ratelimit.strike >= self.application.MAX_USERS:
                        ratelimit.banned_until = request_time + self.application.BAN_FOR
                        logging.debug("Issue ban for a spammer")
                        self.close(code=exceptions.BannedByRateLimit())
                        return
                else:
                    ratelimit.strike = 0
                    ratelimit.striking_test = request_time
                    logging.debug("Reset strikes")

                # Add player
                p = Player(self.player_name, self)
                self.player = p
                self.server.add_user(p)
                p.write_message(
                    messages.Token(p.token)
                )

        elif logging_in:
            if not player:
                self.close(code=exceptions.NameDoesntExist())
                return

            elif player.token != self.token:
                self.close(code=exceptions.TokenCodeMismatch())
                return

            # The player name exists and the code is correct
            elif player.token == self.token:
                self.player = player
                self.player.assign(self)
                self.server.write_message(
                    messages.UserConnected(self.player)
                )

        elif owner_connecting:
            if self.server.token != self.token:
                self.close(code=exceptions.AdminTokenCodeMismatch())
                return
            else:
                self.player = self.server
                self.player.assign(self)
                if self.server.players.count() > 0:
                    self.server.write_message(
                        messages.UsersList(self.server.players.list())
                    )
        
        self.server.active_connections += 1
        if self.server.close_task:
            self.server.close_task.cancel()

    # We notify the server owner about the disconnection
    def on_connection_close(self):
        if (self.close_code or 0) < BASE:
            if self.server and isinstance(self.player, Player):
                self.server.write_message(
                    messages.UserDisconnected(self.player)
                )
        if self.player and self.server:
            self.server.active_connections -= 1
            if self.server.active_connections == 0:
                self.server.close_task = asyncio.create_task(self.application.delete_on_inactive(self.server))

    # Responsible for delivering messages

    def _send_message(self, data):
        if data["to"] == 1:
            recipient = self.server
        elif data["to"] == 2:
            recipient = self.server.players
        else:
            recipient = self.server.get_player_safe(data["to"])

        self.player.sends_message(
            recipient,
            messages.Message(self.player, data["content"])
        )
        if data["to"] == 2:
            self.player.sends_message(
                self.server,
                messages.Message(self.player, data["content"])
            )

    # Fires when a WS packet is received
    def on_message(self, message):
        command = ord(message[0])
        if len(message) > 1:
            data = json.loads(message[1:])

        # Discard packet.
        if command == 32:
            return

        # Send a message.
        if command == 33:
            self._send_message(data)

        # Send more messages at once.
        elif command == 34:
            for part in data:
                self._send_message(part)

        # Lock the instance; ban newcomers.
        if command == 35 and isinstance(self.player, Server):
            self.server.lock = True

        # Unlock the instance; allow newcomers.
        if command == 36 and isinstance(self.player, Server):
            self.server.lock = False

        # Enable p2p mode, broadcast other usernames
        if command == 37 and isinstance(self.player, Server):
            self.server.p2pmode = True

        # Disable p2p mode
        if command == 38 and isinstance(self.player, Server):
            self.server.p2pmode = False
