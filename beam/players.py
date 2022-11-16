from beam import messages
import uuid
import json

import logging

"""
Class for handling connected players.
"""


class Player:
    def __init__(self, name: str, client):
        self.name = str(name)
        self.su = str(uuid.uuid4())
        self.client = client

    # This is used when something sends a message TO this player
    def write_message(self, message):
        try:
            self.client.write_message(json.dumps(
                {
                    "type": "inbound",
                    "msg": message.repr()
                }
            ))
        except:
            pass

    # This is used when THIS PLAYER sends something to someone else
    def sends_message(self, to, content):
        # This is how we identify that we're dealing with a PlayerPool object
        if to.name == 2:
            for recipient in to.list():
                # Run this function again, but one message by one.
                self.sends_message(recipient, content)

        # When we're dealing with anyone but a PlayerPool
        else:
            to.write_message(content)
