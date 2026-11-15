"""Explicit US, German, British, French and Spanish evdev decoder. Unsupported sequences reject a scan.

Linux key codes describe physical keys, not translated text. Layout must match
the scanner. Calibration and custom mappings can build on this boundary later.
"""
import time
import unicodedata

LETTERS = dict(zip(
    (16,17,18,19,20,21,22,23,24,25,30,31,32,33,34,35,36,37,38,44,45,46,47,48,49,50),
    "qwertyuiopasdfghjklzxcvbnm"))
US = {**{code: (str(n), shifted) for code, n, shifted in
              zip(range(2, 12), "1234567890", "!@#$%^&*()")},
      12: ("-", "_"), 13: ("=", "+"), 26: ("[", "{"), 27: ("]", "}"),
      39: (";", ":"), 40: ("'", '"'), 41: ("`", "~"), 43: ("\\", "|"),
      51: (",", "<"), 52: (".", ">"), 53: ("/", "?"), 57: (" ", " ")}
DE = {**US, **dict(zip(range(2,12), zip("1234567890", '!"§$%&/()='))),
      12: ("ß", "?"), 13: ("´", "`"), 26: ("ü", "Ü"), 27: ("+", "*"),
      39: ("ö", "Ö"), 40: ("ä", "Ä"), 41: ("^", "°"), 43: ("#", "'"),
      51: (",", ";"), 52: (".", ":"), 53: ("-", "_"), 86: ("<", ">")}
ALTGR_DE = {3:"²",4:"³",8:"{",9:"[",10:"]",11:"}",12:"\\",16:"@",
            18:"€",27:"~",50:"µ",86:"|"}
GB = {**US, 3: ('2', '"'), 4: ('3', '£'), 40: ("'", '@'),
      41: ('`', '¬'), 43: ('#', '~'), 86: ('\\', '|')}
FR = {**US, **dict(zip(range(2, 12), zip("&é\"'(-è_çà", '1234567890'))),
      12: (')', '°'), 13: ('=', '+'), 26: ('^', '¨'), 27: ('$', '£'),
      39: ('m', 'M'), 40: ('ù', '%'), 41: ('²', '~'), 43: ('*', 'µ'),
      50: (',', '?'), 51: (';', '.'), 52: (':', '/'), 53: ('!', '§'), 86: ('<', '>')}
ES = {**US, **dict(zip(range(2, 12), zip('1234567890', '!"·$%&/()='))),
      12: ("'", '?'), 13: ('¡', '¿'), 26: ('`', '^'), 27: ('+', '*'),
      39: ('ñ', 'Ñ'), 40: ('´', '¨'), 41: ('º', 'ª'), 43: ('ç', 'Ç'),
      51: (',', ';'), 52: ('.', ':'), 53: ('-', '_'), 86: ('<', '>')}
LAYOUTS = {'us': US, 'de': DE, 'gb': GB, 'fr': FR, 'es': ES}
ALTGR = {'us': {}, 'de': ALTGR_DE, 'gb': {5: '€', 18: '€', 43: '|'},
         'fr': {3: '~', 4: '#', 5: '{', 6: '[', 7: '|', 8: '`', 9: '\\',
                10: '^', 11: '@', 12: ']', 13: '}', 18: '€', 27: '¤'},
         'es': {2: '|', 3: '@', 4: '#', 5: '~', 6: '€', 18: '€',
                26: '[', 27: ']', 41: '\\', 43: '{', 40: '}'}}
DEAD_KEYS = {'fr': {26: ('^', '¨')}, 'es': {26: ('`', '^'), 40: ('´', '¨')}}
ACCENTS = {'^': '\u0302', '¨': '\u0308', '`': '\u0300', '´': '\u0301'}

KEYPAD = {82:"0",79:"1",80:"2",81:"3",75:"4",76:"5",77:"6",71:"7",72:"8",73:"9",
          55:"*",74:"-",78:"+",98:"/"}


class Decoder:
    def __init__(self, layout="us", timeout=2.0, max_length=4096, output_profile="standard"):
        if output_profile not in ("standard", "alt-pair-latin1"):
            raise ValueError("Unsupported scanner output profile.")
        if layout not in LAYOUTS:
            raise ValueError("Unsupported keyboard layout.")
        self.dead = None
        self.output_profile = output_profile
        self.alt_digits = None
        self.profile_last = None
        self.completed = False
        self.terminator = None
        self.layout = layout
        self.timeout = timeout
        self.max_length = max_length
        self.modifiers = set()
        self.caps = False
        self.buffer = []
        self.invalid = False
        self.last = None

    def feed(self, code, value, now=None):
        self.completed = value == 1 and code in (28, 96, 15)
        self.terminator = code if self.completed else None
        if self.output_profile == "standard":
            return self._feed_keys(code, value, now)
        now = time.monotonic() if now is None else now
        if self.profile_last is not None and now - self.profile_last > self.timeout:
            interrupted_alt = self.alt_digits is not None
            self.dead = None
            self.buffer.clear()
            self.invalid = interrupted_alt
            self.alt_digits = None
            self.modifiers.clear()
        self.profile_last = now
        if code == 56:
            if value == 1:
                if self.alt_digits is not None or self.modifiers or self.dead is not None:
                    self.invalid = True
                self.alt_digits = []
                self.modifiers.add(56)
            elif value == 0:
                self.modifiers.discard(56)
                if self.alt_digits is None:
                    return None
                digits = ''.join(self.alt_digits)
                self.alt_digits = None
                if not digits or len(digits) > 5:
                    self.invalid = True
                    return None
                number = int(digits)
                if not 32768 <= number <= 65535:
                    self.invalid = True
                    return None
                high, low = divmod(number, 256)
                if high < 160 or 127 <= low <= 159 or (low < 32 and low not in (9, 10, 13)):
                    self.invalid = True
                    return None
                if len(self.buffer) + (1 if low in (9, 10, 13) else 2) > self.max_length:
                    self.invalid = True
                if not self.invalid:
                    self.buffer.append(chr(high))
                    if low not in (9, 10, 13):
                        self.buffer.append(chr(low))
                if low in (9, 10, 13):
                    self.completed = True
                    self.terminator = 'packed-' + str(low)
                    text = ''.join(self.buffer)
                    valid = not self.invalid
                    self.dead = None
                    self.buffer.clear()
                    self.invalid = False
                    return text if valid and text else None
            return None
        if self.alt_digits is not None:
            if value == 1:
                digit = KEYPAD.get(code)
                if digit is None or not digit.isdecimal() or len(self.alt_digits) >= 5:
                    self.invalid = True
                else:
                    self.alt_digits.append(digit)
            if self.completed:
                self.alt_digits = None
                self.modifiers.discard(56)
                self.dead = None
                self.buffer.clear()
                self.invalid = False
            return None
        self.last = now  # Profile timeout already covers all raw events, including Alt codes.
        return self._feed_keys(code, value, now)

    def _feed_keys(self, code, value, now=None):
        now = time.monotonic() if now is None else now
        if code in (29,42,54,56,97,100,125,126):
            if value == 1:
                self.modifiers.add(code)
            elif value == 0:
                self.modifiers.discard(code)
            return None
        # Key-up and auto-repeat are not additional characters.
        if value != 1:
            return None
        if self.last is not None and now - self.last > self.timeout:
            self.dead = None
            self.buffer.clear()
            self.invalid = False
        self.last = now
        if code in (28,96,15):
            text = "".join(self.buffer)
            valid = not self.invalid and self.dead is None
            self.dead = None
            self.buffer.clear()
            self.invalid = False
            return text if text and valid else None
        if code == 58:
            self.caps = not self.caps
            return None
        if code == 69:  # Scanner keypad digits are decoded regardless of LED state.
            return None
        if code == 14:
            if self.dead is not None:
                self.dead = None
                return None
            if self.buffer:
                self.buffer.pop()
            return None
        if self.modifiers & {29,56,97,125,126}:
            self.invalid = True
            return None
        shift = bool(self.modifiers & {42,54})
        if 100 in self.modifiers:
            char = ALTGR[self.layout].get(code)
        elif code in LETTERS and not (self.layout == "fr" and code == 50):
            char = LETTERS[code]
            if self.layout == "de":
                char = {"y":"z", "z":"y"}.get(char, char)
            if self.layout == "fr":
                char = {"q": "a", "a": "q", "w": "z", "z": "w"}.get(char, char)
            if shift != self.caps:
                char = char.upper()
        elif code in KEYPAD:
            char = KEYPAD[code]
        elif code == 83:
            char = "," if self.layout in ("de", "fr", "es") else "."
        else:
            pair = LAYOUTS[self.layout].get(code)
            char = pair[int(shift)] if pair else None
            if pair and pair[0].isalpha() and pair[1] == pair[0].upper():
                char = pair[int(shift != self.caps)]
        dead_pair = DEAD_KEYS.get(self.layout, {}).get(code)
        if dead_pair and 100 not in self.modifiers:
            accent = dead_pair[int(shift)]
            if self.dead is None:
                self.dead = accent
                return None
            if self.dead == accent:
                self.dead = None
                char = accent
            else:
                self.invalid = True
                return None
        elif self.dead is not None and char is not None:
            accent, self.dead = self.dead, None
            char = accent if char == ' ' else unicodedata.normalize('NFC', char + ACCENTS[accent])
            if len(char) != 1:
                self.invalid = True
                return None
        if char is None or len(self.buffer) >= self.max_length:
            self.invalid = True
        elif not self.invalid:
            self.buffer.append(char)
        return None
