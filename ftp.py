import random
import threading

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import ThreadedFTPServer

def rand_password(n):
    # not totally secure, but ok for LAN-restricted access
    return ''.join(random.choices('23456789abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ!@#$%^&*', k=n))  # 1 char = 6 bit entropy


def rand_creds(existing):
    user = f'user{random.randint(1000,9999)}'
    while user in existing:  # collisions are rare
        user = f'user{random.randint(1000,9999)}'
    # no "`" allowed
    password = rand_password(8)
    return user, password


class FTPDrop():
    def __init__(self, addr):
        self.addr = addr

        self.shares = {}

        self.authorizer = DummyAuthorizer()
        self.handler = FTPHandler
        self.handler.use_sendfile = True
        self.handler.authorizer = self.authorizer
        self.handler.banner = "pyftpdlib based ftpd ready."

        self.server = None

    def _run_server(self):
        self.server = ThreadedFTPServer(self.addr, self.handler)
        self.server.max_cons = 20
        self.server.max_cons_per_ip = 5
        self.server.serve_forever()

    def share(self, rootdir, writable):
        if rootdir in self.shares:
            return self.shares[rootdir]
        login, password = rand_creds(self.authorizer.user_table)
        self.authorizer.add_user(login, password, rootdir, perm='elr' if not writable else 'elradfmwMT')
        self.shares[rootdir] = (login, password)

        if not self.active():
            srv = threading.Thread(target=self._run_server, name='FTP')
            srv.deamon = True
            srv.start()

        return login, password

    def unshare(self, rootdir):
        if rootdir not in self.shares:
            return False
        self.authorizer.remove_user(self.shares[rootdir][0])
        del self.shares[rootdir]
        if self.shares:
            return True
        if not self.active():  # never?
            return True
        self.server.close_all()
        self.server = None
        return True

    def force_stop(self):
        if not self.active():
            return
        self.server.close_all()
        self.server = None


    def active(self):
        return self.server is not None
