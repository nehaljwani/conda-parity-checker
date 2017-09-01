import os
import re
import json
import time
import redis
import random
import difflib
import tarfile
import requests
import threading
from io import BytesIO
from memoize import Memoizer
from bs4 import BeautifulSoup
from collections import defaultdict
from packaging.version import parse

PYPI_URL_PATTERN = 'https://pypi.python.org/pypi/{package}/json'

CHANNEL_URL_PATTERN = 'https://conda.anaconda.org/{channel}/{platform}/repodata.json'

REDIS_CONN = redis.StrictRedis(
        host=os.environ.get('REDIS_HOST', '127.0.0.1'),
        port=os.environ.get('REDIS_PORT', '6379'),
        password=os.environ.get('REDIS_PASSWORD', '¯\_(ツ)_/¯'))

CHANNELS = ['conda-forge', 'anaconda', 'c3i_test']

ARCHLINUX_CLOSEST_MATCH_N = 20

ARCHLINUX_REPODB_URL_PATTERN='https://mirrors.kernel.org/archlinux/{repo}/os/x86_64/{repo}.db.tar.gz'

memo = Memoizer({})

# Common Functions
#+=============================================================================
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
        except Exception as e:
            print(e)
            pass
        print("Resting for {} seconds ...".format(rest))
        time.sleep(rest)

# PYPI
#+=============================================================================
# https://stackoverflow.com/a/34366589/1005215
@memo(max_age=20*60)
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

def update_info_pypi(channel, ch_manifest):
    common_pkgs = list(set(ch_manifest.keys()).intersection(fetch_pypi_pkg_list()))

    for pkg in sorted(common_pkgs):
        pkg_com = "{}#{}".format(ch_manifest[pkg], get_pypi_version(pkg))
        REDIS_CONN.hset("{}|{}".format(channel, 'pypi'), pkg, pkg_com)
        print("{}|pypi:\t{}#{}".format(channel, pkg, pkg_com))

# Conda Channels
#+=============================================================================
def fetch_channel_repodata(channel):
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

    REDIS_CONN.hmset("{}|{}".format(channel, 'repodata'),
                    {k: v for k, v in manifest.items()})

    return manifest

# Arch Linux
#+=============================================================================
def obtain_match_archlinux(conda_pkg, archlinux_pkgs):
    # obtain_match_archlinux exact match, return
    if conda_pkg in archlinux_pkgs:
        return conda_pkg

    # prefix, suffix, current
    src_mod = ['', '', conda_pkg]
    dst_mod = {k: ['', '', k] for k in archlinux_pkgs}

    # normalize input
    # replace '-', '.' with '_'
    src_mod[-1] = conda_pkg.replace('-', '_').replace('.', '_')
    for k in archlinux_pkgs:
        dst_mod[k][-1] = dst_mod[k][-1].replace('-', '_').replace('.', '_')
    # remove trailing numbers or decimals
    src_mod[-1] = re.sub(r'[0-9.]+$', '', src_mod[-1])
    for k in archlinux_pkgs:
        dst_mod[k][-1] = re.sub(r'[0-9.]+$', '', dst_mod[k][-1])
    # drop known prefixes from conda_pkg
    for prefix in ['ipython_', 'python_', 'py2', 'py', 'lib', 'c_']:
        if src_mod[-1].startswith(prefix):
            src_mod[0], src_mod[-1] = prefix, src_mod[-1][len(prefix):]
            break
    for suffix in ['_python', '_libs', '_c']:
        if src_mod[-1].endswith(suffix):
            src_mod[1], src_mod[-1] = suffix, src_mod[-1][:len(suffix)]
            break

    # drop known prefixes from archlinux pkg
    for k in archlinux_pkgs:
        for prefix in ['ipython_', 'python2_', 'python_', 'py2', 'py', 'lib', 'c_']:
            if dst_mod[k][-1].startswith(prefix):
                dst_mod[k][0], dst_mod[k][-1] = prefix, dst_mod[k][-1][len(prefix):]
                break
        for suffix in ['_python', '_libs', '_c']:
            if dst_mod[k][-1].endswith(suffix):
                dst_mod[k][1], dst_mod[k][-1] = prefix, dst_mod[k][-1][:len(suffix)]
                break

    exact_matches = [x for x in dst_mod if src_mod[-1] == dst_mod[x][-1]]
    if len(exact_matches) == 1:
        return exact_matches[0]
    elif len(exact_matches) > 1:
        # value of each key is in priority order
        prefix_keys = {'python2_': ['python2_', 'py2', 'python_'],
                        'python_': ['python_', 'py', 'py2', 'python2_'],
                        'py2': ['python2_', 'py2', 'python_', 'py'],
                        'py': ['python_', 'py', 'python2_', 'py2'],
                        'lib': ['lib']}
        for match in exact_matches:
            for key in prefix_keys.get(src_mod[0], []):
                if dst_mod[match][0] == key:
                    return match

    substr_matches = [x for x in dst_mod if src_mod[-1] in dst_mod[x][-1]]
    if len(substr_matches) > 0:
        return substr_matches[0]

    return []

@memo(max_age=60*60)
def fetch_archlinux_pkg_list():
    archlinux_manifest = defaultdict(list)
    for repo in ['extra', 'core', 'community']:
        print('Fetching repodata for {} (archlinux)'.format(repo))
        r = requests.get(ARCHLINUX_REPODB_URL_PATTERN.format(repo=repo))
        t = tarfile.open(mode="r:gz", fileobj=BytesIO(r.content))
        for member in t.getmembers():
            member = member.name.split('/')[0]
            pkg_name = '-'.join(member.split('-')[:-2])
            pkg_ver = member.split('-')[-2]
            archlinux_manifest[pkg_name].append(pkg_ver)
        t.close()
    return archlinux_manifest

def update_info_archlinux(channel, ch_manifest):
    archlinux_manifest = {}

    for pkg, val in fetch_archlinux_pkg_list().items():
        archlinux_manifest[pkg] = sorted(val, key = lambda x: parse(x))[-1]

    archlinux_pkgs_set1 = archlinux_manifest.keys()
    archlinux_pkgs = {re.sub(r'(python.?-|-python.?)', '', x): x for x in archlinux_pkgs_set1}
    archlinux_pkgs_set2 = archlinux_pkgs.keys()
    final_matches = set()

    for package in ch_manifest:
        close_matches = difflib.get_close_matches(package, archlinux_pkgs_set2,
                                                  ARCHLINUX_CLOSEST_MATCH_N)
        close_matches = [archlinux_pkgs[x] for x in close_matches]
        match = obtain_match_archlinux(package, close_matches)
        if match:
            final_matches.add((package, match))

        close_matches = difflib.get_close_matches(package, archlinux_pkgs_set1,
                                                  ARCHLINUX_CLOSEST_MATCH_N)
        match = obtain_match_archlinux(package, close_matches)
        if match:
            final_matches.add((package, match))

    r_dict = {}
    for pkg1, pkg2 in final_matches:
        key = "{}#{}".format(pkg1, pkg2)
        val = "{}#{}".format(ch_manifest[pkg1], archlinux_manifest[pkg2])
        print("{}|archlinux:\t{}#{}".format(channel, key, val))
        r_dict[key] = val
    REDIS_CONN.hmset("{}|{}".format(channel, 'archlinux'), r_dict)

def update_info(channel):
    manifest = fetch_channel_repodata(channel)
    update_info_pypi(channel, manifest)
    update_info_archlinux(channel, manifest)
