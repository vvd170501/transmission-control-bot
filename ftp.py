import random
import threading

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import ThreadedFTPServer

def rand_creds():
    user = 'user'
    # no "`" allowed
    password = ''.join(random.choices('23456789abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ!@#$%^&*', k=8))  # python random is ok
    return user, password


class FTPDrop():
    def __init__(self, addr):
        self.addr = addr
        self.login = '???'

        authorizer = DummyAuthorizer()
        handler = FTPHandler
        handler.use_sendfile = True
        handler.authorizer = authorizer
        handler.banner = "pyftpdlib based ftpd ready."
        self.handler = handler

        self.server = None

    def _run_server(self):
        self.server = ThreadedFTPServer(self.addr, self.handler)
        self.server.max_cons = 20
        self.server.max_cons_per_ip = 5
        self.server.serve_forever()

    def start(self, rootdir, writable):
        if self.server is not None:
            self.handler.authorizer.remove_user(self.login)

        self.login, password = rand_creds()
        self.handler.authorizer.add_user(self.login, password, rootdir, perm='elr' if not writable else 'elradfmwMT')

        if self.server is None:
            srv = threading.Thread(target=self._run_server, name='FTP')
            srv.deamon = True
            srv.start()

        return self.login, password

    def stop(self):
        if self.server is None:
            return
        self.server.close_all()
        self.server.handler.authorizer.remove_user(self.login)
        self.server = None

    def active(self):
        return self.server is not None
