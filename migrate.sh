#!/bin/sh

action="$1"
collection="$2"
field="$3"
default="$4"
type="$5"

if [ -z "$default" ]; then
    default="1"
fi

python3 - <<EOF
from pymongo import MongoClient
from app.settings import mongodb_uri

actions = {
    'add': '\$set',
    'remove': '\$unset'
}

defaults_types = {
    'int': int,
    'float': float,
    'bool': bool,
    'dict': dict,
    'list': list,
    'tuple': tuple,
    'str': str,
    '': str
}

default = defaults_types['$type']('$default') if '$default'.lower() != 'false' else False

client = MongoClient(mongodb_uri)
db = client["chatgpt_telegram_bot"]
collection = db['$collection']
collection.update_many({}, {actions['$action']: {'$field': default}})
EOF
