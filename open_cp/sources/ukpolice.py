import csv
import os.path
import datetime
import numpy as np
from ..data import TimedPoints

_default_filename = os.path.join(os.path.split(__file__)[0],"uk_police.csv")
_DESCRIPTION_FIELD = 'Crime type'
_X_FIELD = 'Longitude'
_Y_FIELD = 'Latitude'
_TIME_FIELD = 'Month'

def _date_from_csv(date_string):
    return datetime.datetime.strptime(date_string, "%Y-%m")
    raise Exception("This: '{}'".format(date_string))

def _convert_header(header):
    lookup = dict()
    for field in [_DESCRIPTION_FIELD, _X_FIELD, _Y_FIELD, _TIME_FIELD]:
        if not field in header:
            raise Exception("No field '{}' found in header".format(field))
        lookup[field] = header.index(field)
    return lookup

def default_burglary_data():
    try:
        return load(_default_filename, {"Burglary"})
    except Exception:
        return None

def load(filename, primary_description_names):
    data = []

    with open(filename) as file:
        reader = csv.reader(file)
        lookup = _convert_header(next(reader))
        for row in reader:
            description = row[lookup[_DESCRIPTION_FIELD]].strip()
            if len(primary_description_names) > 0 and not description in primary_description_names:
                continue
            x = row[lookup[_X_FIELD]].strip()
            y = row[lookup[_Y_FIELD]].strip()
            t = row[lookup[_TIME_FIELD]].strip()
            if x != "" and y != "":
                data.append((_date_from_csv(t), float(x), float(y)))

    data.sort(key = lambda triple : triple[0])
    return TimedPoints.from_coords([t for t, _, _ in data],
        [x for _, x, _ in data], [y for _, _, y in data])