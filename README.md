# conda-parity-checker
A simple webapp to compare conda package versions between channels and pypi

The master branch of this project is deployed at: https://conda-parity-checker.herokuapp.com/

To develop locally, the steps to be followed are:

* Install and setup [Miniconda](https://conda.io/miniconda.html) and create a python3 environment
* Install the dependencies from `requirements.txt`
* Install and setup the [heroku-cli](https://devcenter.heroku.com/articles/heroku-cli).
* Make sure to have access to a remote/local redis-server.
* Create a file `.env` in the top level of the project and fill the following in
  `KEY=VALUE` format:
  - `REDIS_HOST`
  - `REDIS_PORT`
  - `REDIS_PASSWORD`
* To run the app, type `heroku local web` and visit http://localhost:5000
