"""Monochrome icons from 'Symbols Nerd Font' (Material Design set)."""

_CODES = {
    "apps": 0x003B, "terminal": 0x018D, "server": 0x048D, "web": 0x059F, "folder": 0x024B,
    "monitor": 0x0379, "remote": 0x08B9, "keyboard": 0x030C, "wifi": 0x05A9, "wifi-off": 0x05AA,
    "wifi-1": 0x091F, "wifi-2": 0x0922, "wifi-3": 0x0925, "wifi-4": 0x0928, "ethernet": 0x0200,
    "bluetooth": 0x00AF, "bluetooth-off": 0x00B2,
    "volume-high": 0x057E, "volume-mid": 0x0580, "volume-low": 0x057F, "volume-off": 0x0581,
    "brightness": 0x00E0, "power": 0x0425, "settings": 0x0493,
    "left": 0x0141, "right": 0x0142, "up": 0x0143, "down": 0x0140,
    "lock": 0x033E, "unlock": 0x033F, "backspace": 0x006E, "check": 0x012C, "close": 0x0156,
    "minimize": 0x0374, "home": 0x02DC, "restart": 0x0709, "sleep": 0x0904, "back": 0x030D,
    "rotate": 0x0475, "rotate-lock": 0x0478, "coffee": 0x0176,
    "alert": 0x0026, "plus": 0x0415, "edit": 0x03EB, "delete": 0x01B4, "refresh": 0x0450,
    "search": 0x0349, "account": 0x0004, "key": 0x0306, "leaf": 0x032A, "speed": 0x04C5,
    "enter": 0x0311, "shift": 0x0636, "windows": 0x05B2, "image": 0x02E9, "palette": 0x03D8,
    "info": 0x02FC, "update": 0x06B0, "camera": 0x0100, "more": 0x01D8, "exit": 0x0206,
    "lan": 0x0317, "vpn": 0x0582, "cpu": 0x061A, "memory": 0x035B, "disk": 0x02CA, "swap": 0x04E1,
    "temperature": 0x050F, "clock": 0x0150, "touchpad": 0x037D, "link": 0x0337,
    "link-off": 0x0338, "shield": 0x0498, "history": 0x02DA,
    "night": 0x0594, "eject": 0x01EA, "mic": 0x036C, "mic-off": 0x036D, "usb": 0x0553,
    "battery": 0x0079, "battery-charging": 0x0084,
}


def glyph(name):
    return chr(0xF0000 + _CODES[name])


def battery_glyph(percent, charging=False):
    if charging:
        return glyph("battery-charging")
    if percent >= 95:
        return glyph("battery")
    step = min(max(round(percent / 10), 1), 9)
    return chr(0xF007A + step - 1)


def wifi_glyph(strength):
    return glyph(f"wifi-{min(int(strength) // 25 + 1, 4)}")


def volume_glyph(percent, muted=False):
    if muted or percent == 0:
        return glyph("volume-off")
    return glyph("volume-high" if percent >= 60 else "volume-mid" if percent >= 25 else "volume-low")
