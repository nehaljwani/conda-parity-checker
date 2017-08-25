import json
import requests
import time
import semver
import functools
import redis
from bs4 import BeautifulSoup
try:
  from packaging.version import parse
except ImportError:
  from pip._vendor.packaging.version import parse

URL_PATTERN = 'https://pypi.python.org/pypi/{package}/json'

r_con = redis.StrictRedis(host='***REMOVED***', port=***REMOVED***, db=0, password='***REMOVED***')

conda_forge_pkgs = {}

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

def update_info():
  print('Fetching conda-forge manifest ...')
  repodata = requests.get('https://conda.anaconda.org/conda-forge/linux-64/repodata.json').json()
  for pkg in repodata['packages'].keys():
    pkg_name = repodata['packages'][pkg]['name']
    pkg_ver = repodata['packages'][pkg]['version']
    if pkg_name in conda_forge_pkgs:
        conda_forge_pkgs[pkg_name].append(pkg_ver)
    else:
        conda_forge_pkgs[pkg_name] = [pkg_ver]
  for pkg, val in conda_forge_pkgs.items():
      try:
          conda_forge_pkgs[pkg] = sorted(val, key=functools.cmp_to_key(semver.compare))[-1]
      except:
          conda_forge_pkgs[pkg] = sorted(val)[-1]

  print('Fetching pypi manifest ...')
  pypi_soup = BeautifulSoup(requests.get('https://pypi.python.org/simple/').text, 'html.parser')
  pypi_pkgs = [x.text.lower() for x in pypi_soup.findAll('a')]

  common_pkgs = set(conda_forge_pkgs.keys()).intersection(set(pypi_pkgs))

  for pkg in sorted(common_pkgs):
    pkg_com = "{}#{}".format(conda_forge_pkgs[pkg], get_pypi_version(pkg))
    r_con.hset('conda-forge', pkg, pkg_com)
    print(pkg, pkg_com)
    time.sleep(5)
