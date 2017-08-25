from flask import Flask
from datetime import datetime
from getversions import update_info, r_con
import threading
import time
import os

app = Flask(__name__)

@app.route('/')
def homepage():

    tbl_fmt = '''
    <link rel= "stylesheet" type= "text/css" href= "/static/style.css">
    <table>
    <thead>
     <tr>
        <th>Package Name</th>
        <th>Conda Forge Version</th>
        <th>Pip Version</th>
     </tr>
    </thead>
    {}
    </table>'''

    row_fmt  = '''
    <tr>
        <td>{}</td>
        <td>{}</td>
        <td>{}</td>
    </tr>'''
    res = r_con.hgetall('conda-forge')
    res = {k.decode(): (v.decode().split('#')[0], v.decode().split('#')[1]) for k, v in res.items()}
    return tbl_fmt.format(''.join([row_fmt.format(k,v[0], v[1]) for k,v in res.items()]))

def infinity():
    while True:
        try:
            update_info()
        except:
            pass
        time.sleep(3600)

if __name__ == '__main__':
    print('first thread')
    threading.Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': int(os.environ.get('PORT', 5000))}).start()
    print('second thread')
    threading.Thread(target=infinity).start()
