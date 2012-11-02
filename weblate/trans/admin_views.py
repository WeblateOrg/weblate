# -*- coding: utf-8 -*-
#
# Copyright © 2012 Michal Čihař <michal@cihar.com>
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

from weblate.trans.models import SubProject
from django.template import RequestContext
from django.shortcuts import render_to_response
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
import weblate

import os

@staff_member_required
def report(request):
    return render_to_response("admin/report.html", RequestContext(request, {
        'subprojects': SubProject.objects.all()
    }))

@staff_member_required
def ssh(request):
    key_path = os.path.expanduser('~/.ssh/id_rsa.pub')

    try:
        ret = os.system('which ssh-keygen > /dev/null 2>&1')
        can_generate = ret == 0
    except:
        can_generate = False

    # Generate key if it does not exist yet
    if can_generate and request.method == 'POST' and  not os.path.exists(key_path):
        try:
            ret = os.system('ssh-keygen -q -N \'\' -C Weblate -t rsa -f %s' % key_path[:-4])
            if ret != 0:
                messages.error(request, _('Failed to generate key!'))
            else:
                messages.info(request, _('Created new SSH key.'))
        except:
            messages.error(request, _('Failed to generate key!'))

    if os.path.exists(key_path):
        key_data = file(key_path).read()
        key_type, key_fingerprint, key_id = key_data.strip().split()
        key = {
            'key': key_data,
            'type': key_type,
            'fingerprint': key_fingerprint,
            'id': key_id,
        }
    else:
        key = None

    return render_to_response("admin/ssh.html", RequestContext(request, {
        'public_key': key,
        'can_generate': can_generate,
        'ssh_docs': weblate.get_doc_url('admin', 'private'),
    }))
