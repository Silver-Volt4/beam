#!/usr/bin/env python
import tornado.ioloop
import os
import logging

from hotaru import Hotaru

ENABLE_INSPECT = True

logging.basicConfig(
    format='%(name)s/%(levelname)s: %(message)s',
    level=logging.DEBUG
)


def main():
    app = Hotaru(
        do_inspect=ENABLE_INSPECT,
        max_servers=int(os.environ.get("MAX_SERVERS","3")),
        max_users=int(os.environ.get("MAX_SERVERS","3"))
    )
    port = os.environ.get("PORT")
    if not port:
        port = 8000
    logging.info("Starting Hotaru on port {0}".format(port))
    app.listen(port)
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
