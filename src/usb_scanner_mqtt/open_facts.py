"""Optional, bounded Open Facts lookups. No network work runs in the input reader."""
import html
import json
import queue
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

LANGUAGES = ('en', 'de', 'fr', 'es', 'it', 'nl', 'pt', 'pl')
API = 'https://world.openfoodfacts.org/api/v3/product/'


def clean(value):
    return html.unescape(value).strip()[:1000] if isinstance(value, str) else ''


def parse_product(product, language):
    if not isinstance(product, dict):
        return None
    name = next((clean(product.get(key)) for key in
                 (f'product_name_{language}', 'product_name_en', 'product_name') if clean(product.get(key))), '')
    if not name:
        return None
    brand = next((part.strip() for part in clean(product.get('brands')).split(',') if part.strip()), '')
    quantity = clean(product.get('quantity'))
    if not quantity:
        amount = product.get('product_quantity')
        unit = clean(product.get('product_quantity_unit'))
        if isinstance(amount, (str, int, float)) and not isinstance(amount, bool) and unit:
            quantity = f'{amount} {unit}'
    if quantity.lower() == 'unknown':
        quantity = ''
    quantity = re.sub(r'(\d)\s*(ml|cl|dl|l|mg|kg|g)\b', lambda m: m[1] + ' ' + m[2].lower(), quantity, flags=re.I)
    if language == 'de':
        quantity = re.sub(r'(?<=\d)\.(?=\d)', ',', quantity)
    image = clean(product.get('image_front_thumb_url'))
    if not image.startswith('https://'):
        image = ''
    return dict(name=name, brand=brand or None, package_quantity=quantity or None,
                image_url=image or None, product_type=clean(product.get('product_type')) or None,
                source='Open Food Facts')


class RequestBudget:
    """Process-wide limits survive configuration reloads and abandoned HTTP calls."""
    def __init__(self):
        self.busy = threading.Lock()
        self.next_request = 0


_BUDGET = RequestBudget()


class Lookup:
    """At most one HTTP thread, even if DNS/server ignores its socket timeout."""
    def __init__(self, store, fetch=None, budget=None):
        self.store = store
        self.fetch = fetch or self.request
        self.budget = budget if budget is not None else _BUDGET
        self.busy = self.budget.busy

    @property
    def next_request(self):
        return self.budget.next_request

    @next_request.setter
    def next_request(self, value):
        self.budget.next_request = value

    @staticmethod
    def request(code, language, timeout):
        fields = ['product_name', 'product_name_en', f'product_name_{language}', 'brands', 'quantity',
                  'product_quantity', 'product_quantity_unit', 'image_front_thumb_url', 'product_type']
        url = API + code + '.json?' + urllib.parse.urlencode({'product_type': 'all', 'fields': ','.join(dict.fromkeys(fields))})
        request = urllib.request.Request(url, headers={'Accept': 'application/json',
            'User-Agent': f'usb-scanner-mqtt/{__version__} (https://github.com/Nisbo/usb-scanner-mqtt)'})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read(512 * 1024 + 1)
                if len(raw) > 512 * 1024:
                    return 'error', None
                body = json.loads(raw)
                if not isinstance(body, dict):
                    return 'error', None
                data = parse_product(body.get('product'), language)
                return ('found', data) if data else ('not_found', None)
        except urllib.error.HTTPError as error:
            return ('not_found' if error.code == 404 else 'rate_limited' if error.code == 429 else 'error'), None
        except TimeoutError:
            return 'timeout', None
        except urllib.error.URLError as error:
            return ('timeout' if isinstance(error.reason, TimeoutError) else 'error'), None
        except (OSError, ValueError):
            return 'error', None

    def lookup(self, code, language, timeout):
        if not isinstance(code, str) or not re.fullmatch(r'[0-9]{4,32}', code):
            return 'not_applicable', None, False
        cached = self.store.cached(code, language)
        if cached:
            return cached[0], cached[1], True
        if time.monotonic() < self.next_request:
            return 'rate_limited', None, False
        if not self.busy.acquire(blocking=False):
            return 'unavailable', None, False
        result = queue.Queue(maxsize=1)
        def work():
            try:
                result.put(self.fetch(code, language, timeout))
            except Exception:
                result.put(('error', None))
            finally:
                self.busy.release()
        # 15 product requests/minute/IP; this process spaces its own requests.
        self.next_request = time.monotonic() + 4.1
        threading.Thread(target=work, name='open-facts-http', daemon=True).start()
        try:
            status, data = result.get(timeout=timeout)
        except queue.Empty:
            status, data = 'timeout', None
        if status in ('found', 'not_found'):
            self.store.cache(code, language, status, data, 86400 if status == 'found' else 3600)
        elif status in ('error', 'timeout', 'unavailable', 'rate_limited'):
            self.next_request = time.monotonic() + 60
        return status, data, False


class Enricher:
    def __init__(self, store, lookup=None, enabled=True):
        self.store = store
        self.enabled = enabled
        self.lookup = lookup or Lookup(store)
        self.stop = threading.Event()
        self.worker = threading.Thread(target=self.run, name='open-facts-jobs', daemon=True)

    def start(self):
        self.worker.start()

    def process(self):
        job = self.store.next_job()
        if job is None:
            return False
        scan_id, code, options = job
        status, data, cached = self.lookup.lookup(code, options['language'], options['timeout']) if self.enabled else ('disabled', None, False)
        self.store.finish_job(scan_id, status, data, cached)
        return True

    def run(self):
        while not self.stop.is_set():
            try:
                if not self.process():
                    self.stop.wait(.1)
            except Exception:
                # Never print scan contents or credentials; leave durable work for retry.
                self.stop.wait(1)

    def close(self):
        self.stop.set()
        if self.worker.is_alive():
            self.worker.join(timeout=6)
