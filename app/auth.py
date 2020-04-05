import decimal
import functools
import io
import logging
import os
import re
import shutil
import time
from datetime import datetime
from functools import wraps

import bcrypt
import boto3
import botocore
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
from flask import (Blueprint, g, jsonify, redirect, render_template, request,
                   session, url_for)
from PIL import Image

import app

bp = Blueprint("auth", __name__)
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('Events')
s3_client = boto3.client('s3')
BUCKET = "ece1779-a3-pic"
APP_ROOT = os.path.dirname(os.path.abspath(__file__))


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@bp.before_app_request
def load_logged_in_user():
    username = session.get('username')
    if username is None:
        g.user = None

    g.user = username


def _authenticate(username, password):

    assert username is not None, "invalid username"
    assert password is not None, "invalid password"

    response = table.query(
        KeyConditionExpression=Key('username').eq(
            username),
        FilterExpression=Attr('item_type').eq('account')
    )

    assert password == response['Items'][0]['password'], "invalid credential"


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == "GET":
        return render_template('login.html', urls={'login': url_for('auth.login')})

    try:
        username = request.form['username']
        password = request.form['password']

        _authenticate(username, password)

        session.clear()
        session.permanent = True

        session['username'] = username

        return jsonify({
            'isSuccess': True,
            'url': url_for('index')
        })

    except (AssertionError, botocore.exceptions.ClientError) as e:
        return jsonify({
            'isSuccess': False,
            'message': e.args
        })


@bp.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'GET':
        return render_template('register.html', urls={'register': url_for('auth.register')})

    try:

        username = request.form['username']
        password = request.form['password']
        email = request.form['email']

        assert username is not None, "Please enter username"
        assert password is not None, "Please enter password"

        result_name = r'^[A-Za-z0-9._-]{2,100}$'
        result_password = r'^.{6,}$'

        assert re.match(result_name, username, re.M | re.I)
        "Username should have 2 to 100 characters, and only contains letter, number, underline and dash."
        assert re.match(result_password, password)
        "Password should have 6 to 18 characters"

        response = table.query(
            KeyConditionExpression=Key('username').eq(username),
            # in order to test
            FilterExpression=Attr('item_type').eq('account')
        )
        assert len(response['Items']) == 0, "username exists"

        profile_image = "profile image"

        if request.files.getlist("image"):
            for photo in request.files.getlist("image"):
                profile_image = save_image(username, photo)

        response = table.put_item(
            Item={
                'username': username,
                'start_time': int(datetime.utcnow().strftime("%s")),
                'email': request.form['email'],
                'phone_number': request.form['phone_number'],
                'password': password,
                'item_type': 'account',
                'profile_image': profile_image,
            }
        )

        return jsonify({
            'isSuccess': True,
            'url': url_for('auth.login')
        })

    except (botocore.exceptions.ClientError, AssertionError) as e:
        return jsonify({
            'isSuccess': False,
            'message': e.args
        })


def save_image(username, image):
    extension = image.filename.split('.')[-1]
    assert extension.lower() in set(
        ["bmp", "pbm", "pgm", "ppm", "sr", "ras", "jpeg", "jpg", "jpe", "jp2", "tiff", "tif", "png"]), \
        "Unsupported format "

    target = os.path.join(APP_ROOT, 'static/uploaded_images')

    if not os.path.isdir(target):
        os.mkdir(target)

    timestamp = str(int(time.time()))
    filename = username + "_" + timestamp + "." + extension

    image_path = "/".join([target, filename])
    # save images to file "uploaded_images"
    image.save(image_path)
    im_thumb = Image.open(image_path)
    im_thumb.thumbnail((256, 256), Image.ANTIALIAS)
    thumb_filename = username + "_" + timestamp + "_thumb" + "." + extension
    thumb_path = "/".join([target, thumb_filename])
    im_thumb.save(thumb_path)
    s3_client.upload_file(thumb_path, BUCKET, thumb_filename)

    shutil.rmtree(target)

    return thumb_filename


@bp.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    """[summary] this endpoint accepts a POST request and logs out an user
    Returns:
        [type] -- [description] this endpoint returns json result
        {
            isSuccess: boolean indecating if logout is successful,
            message: error message if applicable
        }
    """
    try:
        session.clear()
        return jsonify({
            "isSuccess": True
        })
    except:
        return jsonify({
            'isSuccess': False,
            'message': 'Logout Failed'
        })
