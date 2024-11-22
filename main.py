from flask import Flask, render_template, request, redirect, url_for
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from flask_cors import CORS

app = Flask(__name__)

app.config['MONGO_DBNAME'] = 'audio-db'

app.config['MONGO_URI'] = 'mongodb://localhost:27017/audio-db'

mongo = PyMongo(app)

CORS(app)

@app.route('/')
def index():
    return render_template('index.html')
