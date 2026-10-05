import requests

from manager.__about__ import __version__

session: requests.Session = requests.Session()
session.headers.update({"User-Agent": f"kiwix-bot/{__version__} (hotspot-imager)"})
