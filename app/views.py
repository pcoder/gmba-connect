#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from app import app, db, admin
from .models import *
from .formats import *
from .convert import refresh_data

from flask_admin.contrib.sqla import ModelView, filters
from flask_admin.form import FileUploadField
from flask_admin import (
    BaseView, expose
)
from flask import (
    url_for, redirect,
    request, flash,
    render_template,
    send_from_directory,
)

from werkzeug import secure_filename
from sqlalchemy import or_

import csv, json
import os.path as ospath
from shutil import move
from tempfile import gettempdir

# Get temporary file storage
UPLOAD_PATH = gettempdir()
DATA_PATH = ospath.join(ospath.dirname(__file__), '..', 'data')
def get_datafile(fmt):
    return ospath.join(DATA_PATH, fmt['filename'] + '.' + fmt['extension'])

# Add views
class PersonView(ModelView):
    column_list = ('first_name', 'last_name', 'organisation')
admin.add_view(PersonView(Person, db.session))

class ResourceView(ModelView):
    column_list = ('title', 'citation', 'url')
admin.add_view(ResourceView(Resource, db.session))

class RangeView(ModelView):
    column_list = ('name', 'countries')
admin.add_view(RangeView(Range, db.session))

# Custom view
class ConfigurationView(BaseView):
    @expose('/')
    def index(self):
        fmts = DATAFORMATS
        for f in fmts: f['ready'] = ospath.isfile(get_datafile(f))
        return self.render('admin/config.html', dataformats=fmts)

admin.add_view(ConfigurationView(name='Configuration', endpoint='config'))

def get_paginated(query):
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    ppp = query.paginate(page, per_page, error_out=False)
    return {
        'items': [p.dict() for p in ppp.items],
        'page': page, 'pages': ppp.pages, 'total': ppp.total,
        'has_next': ppp.has_next, 'has_prev': ppp.has_prev
    }

# API views
@app.route("/api/people", methods=['GET'])
def people_list():
    return get_paginated(Person.query.order_by(Person.last_name.asc()))

@app.route("/api/people/<int:people_id>", methods=['GET'])
def people_detail(people_id):
    person = Person.query.filter_by(id=people_id).first_or_404()
    return {
        'data': person.dict(),
        'resources': [r.dict() for r in person.resources]
    }

@app.route("/api/resources", methods=['GET'])
def resources_list():
    return get_paginated(Resource.query.order_by(Resource.title.asc()))

@app.route("/api/ranges", methods=['GET'])
def ranges_list():
    return [r.dict() for r in Range.query.limit(10).all()]

@app.route("/api/search", methods=['GET'])
def search_list():
    q = request.args.get('q')
    if not q or len(q) < 3: return {}
    query = Person.query.filter(or_(
        Person.first_name.ilike('%' + q + '%'),
        Person.last_name.ilike('%' + q + '%'),
        Person.organisation.ilike('%' + q + '%'),
        Person.biography.ilike('%' + q + '%'),
    )).order_by(Person.last_name.asc())
    return get_paginated(query)


# Data upload
@app.route('/upload', methods=['GET', 'POST'])
def upload_data():
    if request.method == 'POST' and 'datafile' in request.files:
        fs = request.files['datafile']
        fs_name = secure_filename(fs.filename)
        fs_path = ospath.join(UPLOAD_PATH, fs_name)
        fs.save(fs_path)

        # Validation
        count = 0
        fmt = None
        if fs_name.endswith('.csv'):
            with open(fs_path, 'rt') as csvfile:
                datareader = csv.DictReader(csvfile)
                datalist = list(datareader)
                fmt = detect_dataformat(datalist[0])
                if fmt is not None:
                    count = len(datalist)

        elif fs_name.endswith('.geojson'):
            with open(fs_path, 'rt') as jsonfile:
                jsondata = json.load(jsonfile)
                fmt = detect_dataformat(jsondata['features'][0]['properties'])
                if fmt is not None:
                    count = len(jsondata['features'])

        # Loading
        if count > 0 and fmt is not None:
            fs_target = get_datafile(fmt)
            move(fs_path, fs_target)
            final_count = refresh_data(fs_target, fmt)
            flash("Uploaded, validated %d and imported %d objects for %s" %
                (count, final_count, fmt['filename']))
        elif count == 0:
            flash("No data rows could be loaded!")
        else:
            flash("Could not detect data format!")
    else:
        flash("Please select a valid file")
    return redirect(url_for('config.index'))

# Data update
@app.route('/refresh', methods=["POST"])
def refresh_all():
    stats = []
    count_total = 0
    for fmt in DATAFORMATS:
        filename = get_datafile(fmt)
        count = refresh_data(filename, fmt)
        if count is None:
            return redirect(url_for('config.index'))
        stats.append({ 'format': fmt['dataformat'], 'count': count })
        count_total = count_total + count
    flash("%d objects updated" % (count_total))
    print(stats)
    return redirect(url_for('config.index'))

# Static paths
@app.route('/data/<path:path>')
def send_data(path):
    return send_from_directory('../data', path)
@app.route('/client/<path:path>')
def send_client(path):
    return send_from_directory('../client', path)
@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('../static', path)
