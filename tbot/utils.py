from typing import Union


def parse_size(value: Union[str, int, float]) -> int:
    """Returns size in bytes."""
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if not value:
        raise ValueError('Not a valid size (empty string)')
    value = value.lower()
    suffix = value[-1]
    suffixes = 'kmgt'
    if suffix in suffixes:
        modifier = 1024**(suffixes.index(suffix)+1)
        value = value[:-1]
    else:  # no suffix or unknown suffix
        modifier = 1
    try:
        value = int(value)
    except ValueError:
        value = float(value)  # may still raise if value is not valid
    return int(value * modifier)
