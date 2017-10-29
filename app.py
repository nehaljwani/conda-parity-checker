import threading
import time
import os
from flask import Flask
from flask import render_template
from datetime import datetime
from itertools import combinations
from utils import CHANNELS, compare_versions, infinity, REDIS_CONN, update_info, \
        fetch_pypi_pkg_list, fetch_archlinux_pkg_list

app = Flask(__name__)

status_order = {'🤔🤔🤔': 1, '🤔🤔': 2, '🤔': 3, '✓': 4, '🎉': 5}

@app.route('/')
def homepage():
     return render_template("index.html")

@app.route('/pypi')
def pypi():
     pkg_info = {}
     for channel in CHANNELS:
         res = REDIS_CONN.hgetall("{}|{}".format(channel, 'pypi'))
         if len(res) == 0:
             continue
         res = {k.decode(): (v.decode().split('#')[0], v.decode().split('#')[1])
                 for k, v in res.items()}
         pkg_info[channel] = []
         for k, v in res.items():
             pkg_info[channel].append({'pkg_name': k,
                 'pkg_status': compare_versions(v[0], v[1]),
                 'pkg_ver': v[0],
                 'pip_ver': v[1]})
         pkg_info[channel].sort(key = lambda x: status_order[x['pkg_status']])

     return render_template("pypi.html", pkg_info=pkg_info)


@app.route('/archlinux')
def archlinux():
     pkg_info = {}
     for channel in CHANNELS:
         res = REDIS_CONN.hgetall("{}|{}".format(channel, 'archlinux'))
         if len(res) == 0:
             continue
         split_this = lambda x: tuple(x.decode().split('#'))
         res = {split_this(k): split_this(v) for k, v in res.items()}
         pkg_info[channel] = []
         for k, v in res.items():
             pkg_info[channel].append({'conda_pkg_name': k[0],
                 'archlinux_pkg_name': k[1],
                 'conda_pkg_status': compare_versions(v[0], v[1]),
                 'conda_pkg_ver': v[0],
                 'archlinux_pkg_ver': v[1]})
         pkg_info[channel].sort(key = lambda x: status_order[x['conda_pkg_status']])

     return render_template("archlinux.html", pkg_info=pkg_info)


@app.route('/channeldiff')
def channeldiffgen():
    return render_template("channeldiffgen.html",
                           entries=list(combinations(CHANNELS, r=2)))


@app.route('/channeldiff/<ch1>/<ch2>')
def channeldiff(ch1, ch2):
    pkg_info = []

    if not all(REDIS_CONN.exists("{}|repodata".format(x)) for x in [ch1, ch2]):
        return ":'("

    pkg1_dict = {k.decode(): v.decode() for k, v in
                 REDIS_CONN.hgetall("{}|repodata".format(ch1)).items()}
    pkg2_dict = {k.decode(): v.decode() for k, v in
                 REDIS_CONN.hgetall("{}|repodata".format(ch2)).items()}

    common_pkgs = list(set(pkg1_dict.keys()).intersection(pkg2_dict.keys()))

    for pkg in sorted(common_pkgs):
        pkg_info.append({'pkg_name': pkg,
            'pkg_status': compare_versions(pkg1_dict[pkg], pkg2_dict[pkg]),
            'ch1_ver': pkg1_dict[pkg],
            'ch2_ver': pkg2_dict[pkg]})

    pkg_info.sort(key = lambda x: status_order[x['pkg_status']])

    return render_template("channeldiff.html", pkg_info=pkg_info,
                           ch1=ch1, ch2=ch2)

if __name__ == '__main__':
    # One thread for the flask app
    print('Starting thread to run app ...')
    threading.Thread(
            target = app.run,
            kwargs = {'host': '0.0.0.0',
                      'port': int(os.environ.get('PORT', 5000))}
            ).start()

    # Prefill some info (blocking)
    fetch_pypi_pkg_list()
    fetch_archlinux_pkg_list()

    # Launch a thread per channel
    for channel in CHANNELS:
        print('Starting thread to populate {} info ...'.format(channel))
        threading.Thread(
                target = infinity,
                args = (update_info, 15*60, (channel, ))
                ).start()
