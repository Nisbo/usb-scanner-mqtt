"""Known test strings and exact comparisons, independent of scanner language settings."""
BASE = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz 0123456789 :/+-@.,;!?()'
LANGUAGES = {
    'de': {'label': 'Deutsch', 'extra': 'ÖöÄäÜüß123ABc'},
    'en': {'label': 'Englisch', 'extra': 'YyZz'},
    'fr': {'label': 'Französisch', 'extra': 'ÀàÂâÇçÉéÈèÊêËëÎîÏïÔôÙùÛûÜüÿ'},
    'es': {'label': 'Spanisch', 'extra': 'ÑñÁáÉéÍíÓóÚúÜü¿¡'},
}
for language in LANGUAGES.values():
    language['text'] = BASE + ' ' + language.pop('extra')
    language['encoding'] = 'latin1'
    language['coverage'] = 'Prüft genau die Zeichen im angezeigten Testtext, nicht jedes Unicode-Zeichen.'
LANGUAGES['fr']['coverage'] += ' Französische Ligaturen œ/Œ und Ÿ sind in diesem Latin-1-Test nicht enthalten.'


def compare_candidates(candidates, expected, events):
    """Only complete literal matches count. Never normalize case, spaces or Unicode."""
    matches = [candidate for candidate in candidates if candidate['text'] == expected] if expected else []
    has_alt = any(code == 56 and value == 1 for code, value in events)
    matches = [candidate for candidate in matches if has_alt or candidate['output_profile'] == 'standard'
               or not any(other['layout'] == candidate['layout'] and other['output_profile'] == 'standard'
                          for other in matches)]
    difference = None
    if expected and not matches and candidates:
        # Display the closest candidate only as a diagnostic, never as a recommendation.
        def prefix_length(candidate):
            return next((index for index, (a, b) in enumerate(zip(expected, candidate['text'])) if a != b),
                        min(len(expected), len(candidate['text'])))
        closest = max(candidates, key=prefix_length)
        index = prefix_length(closest)
        difference = {'position': index + 1,
                      'expected': expected[index:index + 1], 'received': closest['text'][index:index + 1]}
    return {'matches': matches, 'unique': matches[0] if len(matches) == 1 else None,
            'difference': difference}
