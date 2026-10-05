import requests

session: requests.Session = requests.Session()
session.headers.update({"User-Agent": "kiwix-bot/1.0.0 (hotspot-imager-api)"})
