#!/usr/bin/env python
import tornado.ioloop
import os

from hotaru import Hotaru

LOGGING = False # Currently has no effect.
ENABLE_INSPECT = True


def main():
    app = Hotaru(logging=LOGGING, inspect=ENABLE_INSPECT)
    port = os.environ.get("PORT")
    if not port:
        port = 8000
    app.listen(port)
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
