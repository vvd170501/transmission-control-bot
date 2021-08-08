class BotDB():
    def __init__(self, path):
        self.db = ...(path)
        self._init_db()

    def whitelist_user(self, user):
        self.db['whitelist'].append(user)
        self.db.sync(['whitelist'])

    def whitelist(self):
        return self.db['whitelist']

    def set_timer(self, name, time):
        self.db[f'timer_{name}'] = time

    def get_timer(self, name):
        return self.db.get(f'timer_{name}')

    def update_torrents(self, torrents):
        """torrents - list of (hash, active)"""
        hashes = {t[0] for t in torrents}
        need_sync = False
        for t_hash in self.all_torrents():
            if t_hash not in hashes:
                need_sync = True
                self._remove_torrent(t_hash)
        for t_hash, active in torrents:
            if not self.has_torrent(t_hash):
                need_sync = True
                self._add_torrent(t_hash, None, active=active)
            elif active and t_hash not in self.get_active():  # if user selected additional files to download?
                need_sync = True
                self.db['torrents']['active'].add(t_hash)
        if need_sync:
            self._sync_torrents()

    def add_torrent(self, t_hash, owner=None, *, active):
        self._add_torrent(t_hash, owner, active)
        self._sync_torrents()

    def _add_torrent(self, t_hash, owner, active):
        self.db['torrents']['owner'][t_hash] = owner
        if active:
            self.db['torrents']['active'].add(t_hash)
        if owner is not None:
            self.db['torrents']['owned'].setdefault(owner, set()).add(t_hash)

    def remove_torrent(self, t_hash):
        self._remove_torrent(t_hash)
        self._sync_torrents()

    def _remove_torrent(self, t_hash):
        owner = self.get_owner(t_hash)
        if owner is not None:
            self.db['torrents']['owned'][owner].discard(t_hash)
        del self.db['torrents']['owner'][t_hash]
        self.db['torrents']['active'].discard(t_hash)

    def has_torrent(self, t_hash):
        return t_hash in self.db['torrents']['owner']

    def get_active(self):
        return self.db['torrents']['active']

    def get_owner(self, t_hash):
        return self.db['torrents']['owner'][t_hash]

    def all_torrents(self):
        return list(self.db['torrents']['owner'].keys())

    def owned_torrents(self, owner):
        return list(self.db['torrents']['owned'].get(owner, []))

    def mark_finished(self, hashes):
        for t_hash in hashes:
            self.db['torrents']['active'].discard(t_hash)
        self._sync_torrents()

    def disk_full(self):
        return self.db['disk_full']

    def set_disk_full(self, value):
        self.db['disk_full'] = value

    def _sync_torrents(self):
        self.db.sync(['torrents'])


    def close(self):
        self.db.close()

    def _init_db(self):
        pass
