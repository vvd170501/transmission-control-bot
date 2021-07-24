import os
import random
import threading
from pathlib import Path

try:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import ThreadedFTPServer
    from pyftpdlib.filesystems import AbstractedFS
    ftp_available = True
except ImportError:
    ftp_available = False


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


class RestrictedFS(AbstractedFS):
    def __init__(self, root, cmd_channel):
        self._root_file = None

        rootpath = Path(root)
        if rootpath.is_file():  # should only be used with readonly FS (??)
            self._root_file = rootpath.name
            self._fakeroot = self._root_file + os.sep
            self._fakeroot2 = str(rootpath) + os.sep
            root = str(rootpath.parent)

        super().__init__(root, cmd_channel)

    def validpath(self, path):
        """Check whether the path belongs to user's home directory.
        Expected argument is a "real" filesystem pathname.

        If path is a symbolic link it is resolved to check its real
        destination.

        Pathnames escaping from user's root directory are considered
        not valid.
        """
        assert isinstance(path, str), path
        root = self.realpath(self.root)
        path = self.realpath(path)
        if not root.endswith(os.sep):
            root = root + os.sep
        if not path.endswith(os.sep):
            path = path + os.sep
        if path[0:len(root)] == root:
            if self._root_file is not None:
                return path == root or path == self._fakeroot or path == self._fakeroot2
            return True
        return False

    def listdir(self, path):
        """List the content of a directory."""
        assert isinstance(path, str), path
        if self._root_file is not None:
            return [self._root_file] if self._root_file in os.listdir(path) else []
        return os.listdir(path)

    def listdirinfo(self, path):
        """List the content of a directory."""
        assert isinstance(path, str), path
        if self._root_file is not None:
            return [self._root_file] if self._root_file in os.listdir(path) else []
        return os.listdir(path)


class DummyAuthorizer2(DummyAuthorizer):
    def add_user(self, username, password, homedir, perm='elr',
                 msg_login="Login successful.", msg_quit="Goodbye."):
        if self.has_user(username):
            raise ValueError('user %r already exists' % username)
        if not isinstance(homedir, str):
            homedir = homedir.decode('utf8')
        if not os.path.isdir(homedir) and not os.path.isfile(homedir):
            raise ValueError('no such file or directory: %r' % homedir)
        homedir = os.path.realpath(homedir)
        self._check_permissions(username, perm)
        dic = {'pwd': str(password),
               'home': homedir,
               'perm': perm,
               'operms': {},
               'msg_login': str(msg_login),
               'msg_quit': str(msg_quit)
               }
        self.user_table[username] = dic


class FTPDrop():
    def __init__(self, addr):
        self.addr = addr

        self.shares = {}

        self.authorizer = DummyAuthorizer2()
        self.handler = FTPHandler
        self.handler.use_sendfile = True
        self.handler.authorizer = self.authorizer
        self.handler.abstracted_fs = RestrictedFS
        self.handler.banner = "pyftpdlib based ftpd ready."

        self.server = None

    def _run_server(self):
        self.server = ThreadedFTPServer(self.addr, self.handler)
        self.server.max_cons = 20
        self.server.max_cons_per_ip = 5
        self.server.serve_forever()

    def share(self, rootdir, writable, key=None):
        if key is None:
            key = rootdir

        if not isinstance(rootdir, Path):
            rootdir = Path(rootdir)
        rootdir = str(rootdir.resolve())

        if key in self.shares:
            return self.shares[key]
        login, password = rand_creds(self.authorizer.user_table)
        self.authorizer.add_user(login, password, rootdir, perm='elr' if not writable else 'elradfmwMT')
        self.shares[key] = (login, password)

        if not self.active():
            srv = threading.Thread(target=self._run_server, name='FTP')
            srv.deamon = True
            srv.start()

        return login, password

    def get_creds(self, key):
        return self.shares.get(key)

    def unshare(self, key):
        if key not in self.shares:
            return False
        self.authorizer.remove_user(self.shares[key][0])
        del self.shares[key]
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
