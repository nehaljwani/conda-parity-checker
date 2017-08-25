from flask import Flask
from datetime import datetime
from getversions import update_info, r_con
import threading
import time

app = Flask(__name__)

@app.route('/')
def homepage():
    the_time = datetime.now().strftime("%A, %d %b %Y %l:%M %p")

    return """
    <h1>Hello heroku</h1>
    <p>It is currently {time}.</p>

    <img src="http://loremflickr.com/600/400">
    """.format(time=the_time)

def infinity():
    while True:
        update_info()
        time.sleep(3600)

if __name__ == '__main__':
    threading.Thread(target=app.run).start()
    threading.Thread(target=infinity).start()
