import json
import requests
import time
import semver
import functools
import redis
import random
from bs4 import BeautifulSoup
try:
    from packaging.version import parse
except ImportError:
    from pip._vendor.packaging.version import parse

URL_PATTERN = 'https://pypi.python.org/pypi/{package}/json'

r_con = redis.StrictRedis(host='***REMOVED***', port=***REMOVED***, db=0, password='***REMOVED***')

# https://stackoverflow.com/a/34366589/1005215
def get_pypi_version(package, url_pattern=URL_PATTERN):
  """Return version of package on pypi.python.org using json."""
  req = requests.get(url_pattern.format(package=package))
  version = parse('0')
  if req.status_code == requests.codes.ok:
      j = json.loads(req.text.encode(req.encoding))
      if 'releases' in j:
          releases = j['releases']
          for release in releases:
              ver = parse(release)
              if not ver.is_prerelease:
                  version = max(version, ver)
  return version

def update_info(channels):
    print('Fetching pypi manifest ...')
    pypi_soup = BeautifulSoup(requests.get('https://pypi.python.org/simple/').text, 'html.parser')
    pypi_pkgs = {x.text.lower() for x in pypi_soup.findAll('a')}

    for channel in channels:
        print('Fetching {} manifest ...'.format(channel))
        channel_pkgs = {}
        repodata = requests.get('https://conda.anaconda.org/{}/linux-64/repodata.json'.format(channel)).json()

        for pkg in repodata['packages'].keys():
            pkg_name = repodata['packages'][pkg]['name']
            pkg_ver = repodata['packages'][pkg]['version']
            if pkg_name in channel_pkgs:
                channel_pkgs[pkg_name].append(pkg_ver)
            else:
                channel_pkgs[pkg_name] = [pkg_ver]

        for pkg, val in channel_pkgs.items():
            try:
                channel_pkgs[pkg] = sorted(val, key=functools.cmp_to_key(semver.compare))[-1]
            except:
                channel_pkgs[pkg] = sorted(val)[-1]

        common_pkgs = list(set(channel_pkgs.keys()).intersection(pypi_pkgs))
        random.shuffle(common_pkgs)

        for pkg in common_pkgs:
            pkg_com = "{}#{}".format(channel_pkgs[pkg], get_pypi_version(pkg))
            r_con.hset(channel, pkg, pkg_com)
            print(pkg, pkg_com)
            time.sleep(1)

def compare_versions(v1, v2):
    try:
        res = semver.compare(v1, v2)
    except:
        res = (v1 > v2) - (v1 < v2)
    if (res > 0):
        return '🎉'
    elif res == 0:
        return '✓'
    else:
        factor = 1
        v1, v2 = v1.split('.'), v2.split('.')
        # Difference in major
        if len(v1) >= 1 and len(v2) >= 1 and v1[0] != v2[0]:
            factor = 3
        # Difference in minor
        if len(v1) >= 2 and len(v2) >= 2 and v1[1] != v2[1]:
            factor = 2
        return factor * '🤔'
