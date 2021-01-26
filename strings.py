units = ['B', 'KB', 'MB', 'GB', 'TB']

def format_size(size):
    i = 0
    while size > 1024:
        size /= 1024
        i += 1
    return f'{size:.2f} {units[i]}'

def format_speed(bps):
    if bps < 1000:
        return f'{bps} B/s'
    bps /= 1000
    if bps < 1000:
        return f'{round(bps)} KB/s'
    bps /= 1000
    return f'{bps:.2f} MB/s'

help = """Пришлите боту .torrent-файл для начала загрузки

Доступные команды:
/help - вывести эту инструкцию
/limit - показать установленные ограничения скорости
/setlimit - установить / снять ограничения скорости
/my_torrents - вывести / редактировать список ваших торрентов
/disk - показать заполненность диска"""

#TODO create keyboard class

disk_usage = 'Использовано: {} из {}, {:.1f}%'

#limit
notif_limit_set = '⚠ Установлены ограничения скорости\n'
notif_limit_reset = '⚡ Ограничения скорости убраны'
perm_limit = 'Download: {}\nUpload: {}'
temp_limit = 'Download: {}\nUpload: {}\nОграничения до: {}'
soon = 'Сброс ограничений...'

#set limit
select_dl = 'Ограничение скорости загрузки'
dllist = [('1 MB/s', 1000), ('5 MB/s', 5000), ('10 MB/s', 10000), ('20 MB/s', 20000), ('Неогр. (до ~37 MB/s)', None)]
dl_buttons = dict(dllist)
dl_kb = [[e[0] for e in dllist[row_start:row_end]] for (row_start, row_end) in [(0, 2), (2, 4), (4, 5)]]

select_ul = 'Ограничение скорости раздачи'
ullist = [('1 MB/s', 1000), ('2 MB/s', 2000), ('5 MB/s', 5000), ('10 MB/s', 10000), ('Неогр. (до ~37 MB/s)', None)]
ul_buttons = dict(ullist)
ul_kb = [[e[0] for e in ullist[row_start:row_end]] for (row_start, row_end) in [(0, 2), (2, 4), (4, 5)]]

select_dur = 'Таймер ограничения'
durlist = [('5 мин.', 300), ('10 мин.', 600), ('15 мин.', 900), ('30 мин.', 1800), ('1 ч.', 3600), ('Навсегда', None)]
dur_buttons = dict(durlist)
dur_kb = [[e[0] for e in durlist[i:i+2]] for i in range(0, len(durlist), 2)]

limit_set = '⚠ Ограничения скорости установлены'
limit_reset = '⚡ Ограничения скорости сброшеы'

# new torrent
added = '✅ Торрент успешно добавлен!'
duplicate = '❌ Дубликат существующего торрента'
error_load_file = '❌ Ошибка при чтении torrent-файла'
error = '❌ Неизвестная ошибка'
invalid_dirname = '❌ Недопустимое имя папки. Попробуйте еще раз (/cancel для отмены)'
nohash = '❌ Ошибка - не найден хеш торрента.'

select_dir = 'Выберите папку для загрузки (/cancel для отмены)'
dirlist = [('🎬 Фильмы', 'Films'), ('📺 Сериалы', 'Series'), ('🎵 Музыка', 'Music'),
        #('🎮 Игры', 'Games'), ('⚙ ПО', 'Software'), 
        ('Другое', '')]
dir_buttons = dict(dirlist)
dir_kb = [[e[0] for e in dirlist[i:i+2]] for i in range(0, len(dirlist), 2)]

make_dir = 'Введите имя папки (допустимые символы - буквы, цифры, пробел, ".", "-", "_")'

#fallbacks
howtocancel = 'Неизвестная команда. Отправьте /cancel для отмены'
cancelled = 'Операция отменена'

# notification
finished = '🔔 "{}" - загрузка завершена!'
disk_full = '❗ Диск переполнен, все загрузки были остановлены'
disk_ok = '💾 На диске достаточно свободного места, можно возобновить загрузку вручную'

# torrent management
status = {
    'stopped': ('Остановлен', '⏸'),
    'check pending': ('Ожидание проверки', '⏳🔄⏳'),
    'checking': ('Проверка', '🔄'),
    'download pending': ('Ожидание загрузки', '⏳⬇⏳'),
    'downloading': ('Загрузка', '⬇'),
    'seed pending': ('Ожидание раздачи', '⏳⬆⏳'),
    'seeding': ('Раздаётся', '⬆'),
    'stopping': ('Остановка...', '⏳⏸⏳')
}

def format_torrents(torrents, offset, n):
    if not torrents:
        return 'Торрентов не найдено!'
    lines = [f'Торренты {offset+1}-{offset+len(torrents)} из {n}'] + [f'{i+1}. {t.name} ({format_size(t.sizeWhenDone)}) {status[t.status][1]}' + (f' {t.progress:.2f}%' if t.status.startswith('down') else '') for i, t in enumerate(torrents)]
    return '\n'.join(lines)

def format_torrent(t, override_status=None):
    lines = [
            t.name,
            f'Скачано: {format_size(t.sizeWhenDone - t.leftUntilDone)} / {format_size(t.sizeWhenDone)} ({t.progress:.2f}%)',
            f'Статус: {status[t.status if override_status is None else override_status][0]}',
            f'⬇ {format_speed(t.rateDownload)} | ⬆ {format_speed(t.rateUpload)}'
            ]
    if override_status is None:
        if t.status == 'downloading':
            lines[2] += f' от {t.peersSendingToUs} из {t.peersConnected} пиров'
            lines.append(f'Осталось: {t.format_eta()}')
        elif t.status == 'seeding':
            lines[2] += f' к {t.peersGettingFromUs} из {t.peersConnected} пиров'
    return '\n'.join(lines)

del_confirm = 'Вы точно хотите удалить торрент "{}" и скачанные файлы?'
deleted = 'Торрент был удалён'

left = 'Вы уже на первой странице!'
right = 'Вы уже на последней странице!'
