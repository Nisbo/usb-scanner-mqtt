"""Test-only key diagnostics; never infer a character encoding from Alt digits."""
from .keyboard import Decoder, LAYOUTS, KEYPAD


def diagnose_scan(events, output_profile="standard"):
    sequences = []
    current = None
    for index, (code, value) in enumerate(events):
        if code == 56 and value == 1 and current is None:
            current = {'digits': '', 'other_keys': [], 'complete': False, 'start_event': index}
        elif code == 56 and value == 0 and current is not None:
            current['complete'] = True
            sequences.append(current)
            current = None
        elif current is not None and value == 1:
            digit = KEYPAD.get(code)
            if digit is not None and digit.isdecimal():
                current['digits'] += digit
            else:
                current['other_keys'].append(code)
    if current is not None:
        sequences.append(current)

    layouts = {}
    for layout in LAYOUTS:
        decoder = Decoder(layout, output_profile=output_profile)
        first_error = None
        for index, (code, value) in enumerate(events):
            invalid = decoder.invalid
            decoder.feed(code, value, now=index * 0.001)
            if decoder.invalid and not invalid and first_error is None:
                first_error = {'event': index, 'keycode': code,
                               'modifiers': sorted(decoder.modifiers), 'prefix': ''.join(decoder.buffer)}
        layouts[layout] = first_error
    return {'alt_sequences': sequences, 'first_error': layouts}
