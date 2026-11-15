"""Stable scanner identity and the three explicitly supported MQTT controls."""
PROJECT = 'usb_scanner_mqtt'
CONTROLS = {
    'scan_forwarding': ('Scan forwarding', None, 'scan_send_enabled', 'mdi:send'),
    'open_facts': ('Product lookup', 'open_facts', 'enabled', 'mdi:barcode-search'),
    'product_data': ('Include product data', 'open_facts', 'include_mqtt', 'mdi:package-variant'),
}


def identity(config):
    return PROJECT + '_' + config['scanner']['id']


def entity_slug(config):
    return identity(config).lower().replace('-', '_')


def base_topic(config):
    return 'usb-scanner-mqtt/' + config['scanner']['id']


def control_topic(config, key, direction):
    return base_topic(config) + '/control/' + key + '/' + direction


def values(config):
    return {key: (config[section][field] if section else config[field])
            for key, (_, section, field, _) in CONTROLS.items()}


def device(config):
    from . import __version__
    return {'identifiers': [identity(config)], 'name': config['scanner']['name'],
            'manufacturer': 'Nisbo', 'model': 'USB HID MQTT Scanner', 'sw_version': __version__}


def discovery(config):
    prefix = config['mqtt']['discovery_prefix'].rstrip('/')
    return [(f'{prefix}/switch/{identity(config)}/{key}/config', {
        'name': name, 'unique_id': identity(config) + '_' + key,
        'default_entity_id': 'switch.' + entity_slug(config) + '_' + key,
        'command_topic': control_topic(config, key, 'set'),
        'state_topic': control_topic(config, key, 'state'),
        'payload_on': 'ON', 'payload_off': 'OFF', 'state_on': 'ON', 'state_off': 'OFF',
        'optimistic': False, 'retain': False, 'qos': 1, 'icon': icon,
        'entity_category': 'config', 'availability_topic': base_topic(config) + '/status/availability',
        'payload_available': 'online', 'payload_not_available': 'offline', 'device': device(config),
    }) for key, (name, _, _, icon) in CONTROLS.items()]
