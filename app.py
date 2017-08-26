import threading
import time
import os
from flask import Flask
from flask import render_template
from datetime import datetime
from utils import CHANNELS, compare_versions, infinity, REDIS_CONN, update_info

app = Flask(__name__)

@app.route('/')
def homepage():

     pkg_info = {}
     status_order = {'🤔🤔🤔': 1, '🤔🤔': 2, '🤔': 3, '✓': 4, '🎉': 5}
     for channel in CHANNELS:
         res = REDIS_CONN.hgetall(channel)
         res = {k.decode(): (v.decode().split('#')[0], v.decode().split('#')[1])
                 for k, v in res.items()}
         pkg_info[channel] = []
         for k, v in res.items():
             pkg_info[channel].append({'pkg_name': k,
                 'pkg_status': compare_versions(v[0], v[1]),
                 'pkg_ver': v[0],
                 'pip_ver': v[1]})
         pkg_info[channel].sort(key = lambda x: status_order[x['pkg_status']])

     return render_template("index.html", pkg_info=pkg_info)


if __name__ == '__main__':
    print('Starting thread to run app ...')
    threading.Thread(
            target = app.run,
            kwargs = {'host': '0.0.0.0',
                      'port': int(os.environ.get('PORT', 5000))}
            ).start()
    print('Starting thread to populate info ...')
    threading.Thread(
            target = infinity,
            args = (update_info, (CHANNELS, ))
            ).start()
