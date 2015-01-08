#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright © 2014 Daniel Tschan <tschan@puzzle.ch>
#
# This file is part of Weblate <http://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import os
from string import Template

virtenv = os.environ['OPENSHIFT_PYTHON_DIR'] + '/virtenv/'
virtualenv = os.path.join(virtenv, 'bin/activate_this.py')
try:
    execfile(virtualenv, dict(__file__=virtualenv))
except IOError:
    pass


def application(environ, start_response):

    ctype = 'text/html'
    response_body = Template('''<!doctype html>
<html lang="en">
<head>
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta charset="utf-8">
  <title>Installing Weblate</title>
<style>
html {
  background: #f5f5f5;
  height: 100%;
}
body {
  color: #404040;
  font-family: "Helvetica Neue",Helvetica,"Liberation Sans",Arial,sans-serif;
  font-size: 14px;
  line-height: 1.4;
}
h1 {
  color: #000;
  line-height: 1.38em;
  margin: .4em 0 .5em;
  font-size: 25px;
  font-weight: 300;
  border-bottom: 1px solid #fff;
}
h1:after {
  content: "";
  display: block;
  height: 1px;
  background-color: #ddd;
}
p {
  margin: 0 0 2em;
}
pre {
  padding: 13.333px 20px;
  margin: 0 0 20px;
  font-size: 13px;
  line-height: 1.4;
  background-color: #fff;
  border-left: 2px solid rgba(120,120,120,0.35);
  font-family: Menlo,Monaco,"Liberation Mono",Consolas,monospace !important;
}
.content {
  display: table;
  margin-left: -15px;
  margin-right: -15px;
  position: relative;
  min-height: 1px;
  padding-left: 30px;
  padding-right: 30px;

}
</style>
</head>
<body>
  <div class="content">
    <h1>$action1 Weblate</h1>

    <p>
    Weblate is beeing $action2.
    Please wait a few minutes and refresh this page.
    </p>

    $log
  </div>
</body>
</html>''')
    context = {}

    if os.path.exists(os.environ['OPENSHIFT_DATA_DIR'] + '/.installed'):
        context['action1'] = 'Updating'
        context['action2'] = 'updated'
        context['log'] = ''
    else:
        context['action1'] = 'Installing'
        context['action2'] = 'installed'
        log_msg = os.popen(
            r"cat ${OPENSHIFT_PYTHON_LOG_DIR}/install.log |"
            r" grep '^[^ ]\|setup.py install' |"
            r" sed 's,/var/lib/openshift/[a-z0-9]\{24\},~,g'"
        ).read()
        context['log'] = '<pre>' + log_msg + '</pre>'

    response_body = response_body.substitute(context)
    status = '200 OK'
    response_headers = [
        ('Content-Type', ctype),
        ('Content-Length', str(len(response_body)))
    ]

    start_response(status, response_headers)
    return [response_body]
