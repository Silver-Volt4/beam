import tornado.escape
import tornado.template
import tornado.web
import tornado.websocket

from beam import messages, ratelimiting, exceptions
from beam.servers import ServerPool
from beam.players import Player

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

        handlers.append(
            ("/(.*)", BeamLanding)
        )
        super().__init__(handlers)

###          ###
### HANDLERS ###
###          ###


class BeamLanding(tornado.web.RequestHandler):
    def get(self, input):
        self.write(self.application.html.load("landingpage.html").generate())


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
        if cmd.endswith("createServer"):
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
                su = server.su
                server.owner_ip = self.request.remote_ip
                logging.info(f"Created new Server: {game_code}")
                self.application.rate_limits.ip_own(server.owner_ip)
                self.set_status(201)
                self.write({
                    "c": game_code[-4:],
                    "su": su
                })
        else:
            self.set_status(404)

    def delete(self, cmd):
        if self._status_code == 400:
            return
        if cmd.endswith("closeServer"):
            server = self.application.pool.get_server_safe(
                self.get_argument("code"))
            if server:
                if server.su == self.get_argument("su"):
                    self.application.rate_limits.ip_deown(server.owner_ip)
                    server.close_server()
                    logging.info(f"Closed server: {server.code}")
                    self.application.pool.free(server.code)
                    self.set_status(200)
                else:
                    self.set_status(401)
            else:
                self.set_status(404)


class BeamWebsocket(tornado.websocket.WebSocketHandler):
    """
    Main object for the WebSocket endpoint itself.
    This is where actual communication happens.
    """

    def __init__(self, application, request, **kwargs) -> None:
        super().__init__(application, request, **kwargs)
        self.server = None
        self.player_name = None
        self.player = None
        self.su = None

    def xtract_args(self):
        code = self.get_argument("code")
        server = self.application.pool.get_server_safe(code)

        player_name = self.get_argument("name", None)
        player = None
        if server and player_name:
            player = server.get_player_safe(player_name)

        su = self.get_argument("su", None)
        if su and not player_name:
            player = server

        return (server, player_name, player, su)

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

        self.server, self.player_name, self.player, self.su = self.xtract_args()

        # Check for errors in the connection and kick the client if necessary

        if not self.server:
            self.close(code=exceptions.ServerCodeDoesntExist())
            return

        registering = self.player_name and not self.su
        logging_in = self.player_name and self.su
        owner_connecting = self.su and not self.player_name

        if registering:
            if self.server.lock:
                self.close(code=exceptions.ServerIsLocked())

            elif self.server.players.count() == self.server.limit:
                self.close(code=exceptions.RoomLimitReached())

            elif self.player:
                self.close(code=exceptions.NameIsTaken())

            elif self.player_name == "":
                self.close(code=exceptions.NamePropertyIsEmpty())

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
                self.server.add_user(p)
                su_message = messages.Su(p.su)
                p.write_message(su_message)
                append = messages.UserAppend(p)
                self.server.write_message(append)

        elif logging_in:
            if not self.player:
                self.close(code=exceptions.NameDoesntExist())

            elif self.player.su != self.su:
                self.close(code=exceptions.SuCodeMismatch())

            # The player name exists and the code is correct
            elif self.player.su == self.su:
                try:
                    self.player.client.close(code=exceptions.Overridden())
                except:
                    pass
                self.player.client = self

                join = messages.UserJoin(self.player)
                self.server.write_message(join)

        elif owner_connecting:
            if self.server.su != self.su:
                self.close(code=exceptions.SuAdminCodeMismatch())

            # The code checks out
            else:
                try:
                    self.server.client.close(code=exceptions.Overridden())
                except:
                    pass
                self.server.client = self

    # We notify the server owner about the disconnection
    def on_connection_close(self):
        if self.close_code:
            if self.close_code != 1000 and self.close_code < 4000:
                if self.server and self.player:
                    left = messages.UserLeft(self.player)
                    self.server.write_message(left)

    # Responsible for delivering messages
    def _send_message(self, server, player, actual_message):
        if actual_message["to"] == 1:
            recipient = server
        elif actual_message["to"] == 2:
            recipient = server.players
        else:
            recipient = server.get_player_safe(actual_message["to"])

        msg = messages.RawMessage(player, actual_message["content"])
        player.sends_message(recipient, msg)

        if actual_message["to"] == 2:
            player.sends_message(server, msg, True)

    # Fires when a WS packet is received
    def on_message(self, message, *args):
        command = ord(message[0])
        if len(message) > 1:
            data = json.loads(message[1:])

        # Discard packet.
        if command == 32:
            return
        
        # Send a message.
        if command == 33:
            self._send_message(self.server, self.player, data)

        # Send more messages at once.
        elif command == 34:
            for ms in data:
                self._send_message(self.server, self.player, ms)


        # player.name is a 1 only if it's sent by the server owner,
        # see servers.py. This is for legacy reasons and how Beam was implemented
        # before the rewrite and open-sourcing.
        if command == 35 and self.player.name == 1:
            self.server.lock = True

        if command == 36 and self.player.name == 1:
            self.server.lock = False

