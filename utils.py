import os
import json
import requests
import time
import redis
import random
import threading
from bs4 import BeautifulSoup
from collections import defaultdict
from packaging.version import parse
from memoize import Memoizer

PYPI_URL_PATTERN = 'https://pypi.python.org/pypi/{package}/json'

CHANNEL_URL_PATTERN = 'https://conda.anaconda.org/{channel}/{platform}/repodata.json'

REDIS_CONN = redis.StrictRedis(
        host=os.environ.get('REDIS_HOST', '127.0.0.1'),
        port=os.environ.get('REDIS_PORT', '6379'),
        password=os.environ.get('REDIS_PASSWORD', '¯\_(ツ)_/¯'))

CHANNELS = ['conda-forge', 'anaconda', 'c3i_test']

PKG_INFO = {}

memo = Memoizer({})

# https://stackoverflow.com/a/34366589/1005215
def get_pypi_version(package, url_pattern=PYPI_URL_PATTERN):
  """Return version of package on pypi.python.org using json."""
  req = requests.get(url_pattern.format(package=package))
  version = parse('0')
  if req.status_code == requests.codes.ok:
      j = json.loads(req.text.encode(req.encoding))
      if 'releases' in j:
          versions = [parse(s) for s in j['releases']]
          filtered = [v for v in versions if not v.is_prerelease]
          if len(filtered) == 0:
              return max(versions)
          else:
              return max(filtered)
  return version

@memo(max_age=20*60)
def fetch_pypi_pkg_list():
    print('Fetching pypi manifest ...')
    pypi_soup = BeautifulSoup(requests.get('https://pypi.python.org/simple/').text, 'html.parser')
    pypi_pkgs = {x.text.lower() for x in pypi_soup.findAll('a')}
    return pypi_pkgs

def fetch_channel_repodata(channel):
    global PKG_INFO
    print('Fetching {} manifest ...'.format(channel))
    repodata = requests.get(CHANNEL_URL_PATTERN.format(
        channel=channel, platform='linux-64')).json()
    repodata = repodata['packages']

    manifest = defaultdict(list)
    for pkg in repodata:
        pkg_name = repodata[pkg]['name']
        pkg_ver = repodata[pkg]['version']
        manifest[pkg_name].append(pkg_ver)

    for pkg, val in manifest.items():
        manifest[pkg] = sorted(val, key = lambda x: parse(x))[-1]

    PKG_INFO[channel] = manifest
    return manifest

def update_info(channel):
    manifest = fetch_channel_repodata(channel)

    common_pkgs = list(set(manifest.keys()).intersection(fetch_pypi_pkg_list()))

    for pkg in sorted(common_pkgs):
        pkg_com = "{}#{}".format(manifest[pkg], get_pypi_version(pkg))
        REDIS_CONN.hset(channel, pkg, pkg_com)
        print("{}:\t{}#{}".format(channel, pkg, pkg_com))
        time.sleep(1)

def compare_versions(v1, v2):
    res = (parse(v1) > parse(v2)) - (parse(v1) < parse(v2))
    if (res > 0):
        return '🎉'
    elif res == 0:
        return '✓'
    else:
        factor = 1
        # FIXME: Many edge cases here
        v1, v2 = v1.split('.'), v2.split('.')
        # Difference in minor
        if len(v1) >= 2 and len(v2) >= 2 and v1[1] != v2[1]:
            factor = 2
        # Difference in major
        if len(v1) >= 1 and len(v2) >= 1 and v1[0] != v2[0]:
            factor = 3
        return factor * '🤔'

def infinity(f, rest, args=(), kwargs={}):
    while True:
        try:
            f(*args, **kwargs)
        except:
            pass
        time.sleep(rest)
