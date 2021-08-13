import re
import sqlite3
from enum import Flag
from pathlib import Path
from threading import Lock

from . import strings


class FlagPreferences(Flag):
    default_share = (1, False)
    private_notifications = (2, True)
    shared_notifications = (4, False)

    def __new__(cls, value, default_value):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.default_value = default_value
        return obj

    def description(self):
        if self.name is None:
            raise NotImplementedError()  # multiple or zero values
        return getattr(strings.Preferences, self.name)['description']

    def status_description(self, value):
        if self.name is None:
            raise NotImplementedError()
        return getattr(strings.Preferences, self.name)['values'][value]['status']

    def choice_description(self, value):
        if self.name is None:
            raise NotImplementedError()
        return getattr(strings.Preferences, self.name)['values'][value]['choice']


default_flag_prefs = sum(pref.value * pref.default_value for pref in FlagPreferences)


class MTSQLConnection(sqlite3.Connection):
    """SQLite connection with a lock"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = Lock()

    @property
    def lock(self):
        return self._lock

    # Use the lock when used as context manager
    def __enter__(self):
        self._lock.acquire()
        try:
            return super().__enter__()
        except Exception:  # is it possible?
            self._lock.release()
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        result = super().__exit__(exc_type, exc_val, exc_tb)
        self._lock.release()
        return result


class Driver:
    valid_dirname = re.compile(r'^[\w. -]+$')

    def __init__(self, *, data_dir: Path, reserved_space: int, client_cfg, ftp_cfg, job_queue):
        if not data_dir.exists():
            data_dir.mkdir(parents=True)
        self._db = sqlite3.connect(data_dir / 'main.db',
                                   factory=MTSQLConnection, check_same_thread=False)
        ...
        self._init_db()

    @property
    def ftp_enabled(self):
        return ...

    def is_valid_user(self, uid):
        with self._db:
            return self._db.execute(
                'SELECT id FROM users WHERE id = ?', (uid,)
            ).fetchone() is not None

    def add_user(self, uid):
        with self._db:
            self._db.execute(
                'INSERT INTO users VALUES (?, ?)', (uid, default_flag_prefs)
            )

    def get_speed_limits(self):
        ...

    def get_disk_usage(self):
        ...

    def share_root_ftp(self):
        ...

    def unshare_root_ftp(self):
        ...

    def is_valid_dirname(self, dirname):
        return self.valid_dirname.match(dirname) and dirname not in ['.', '..']

    def _init_db(self):
        with self._db:  # subclass sqlite3.Connection to lock automatically?
            if self._db.execute(
                    'SELECT name FROM sqlite_master WHERE type=\'table\' AND name=\'torrents\''
            ).fetchone() is not None:
                return
            self._db.execute(
                'CREATE TABLE users (id INT PRIMARY KEY, flag_preferences INT)'
            )
            self._db.execute(
                'CREATE TABLE torrents ('
                'hash BLOB PRIMARY KEY,'
                'owner INT,'
                'is_watched INT,'
                'is_shared INT,'
                'FOREIGN KEY (owner) REFERENCES users(id)'
                ')'
            )
            self._db.execute('CREATE INDEX torrents_owner_idx on torrents(owner)')
            self._db.execute('CREATE INDEX torrents_watched_idx on torrents(is_watched)')
            self._db.execute('CREATE INDEX torrents_shared_idx on torrents(is_shared)')
