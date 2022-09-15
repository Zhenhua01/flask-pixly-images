import os
from dotenv import load_dotenv

from flask import Flask, render_template, flash, redirect, json
from flask_debugtoolbar import DebugToolbarExtension
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename
from models import Image, Image_Metadata, db, connect_db
from forms import AddImageForm, EditImageForm, EditImageForUploadForm
from botocore.exceptions import ClientError

import requests
import boto3
from io import BytesIO
from PIL import ExifTags, Image as PilImage, ImageFilter
from PIL.ExifTags import TAGS


load_dotenv()

app = Flask(__name__)
connect_db(app)

# Get DB_URI from environ variable (useful for production/testing) or,
# if not set there, use development local db.
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_DATABASE_URI'] = (
    os.environ['DATABASE_URL'].replace("postgres://", "postgresql://"))
app.config['SQLALCHEMY_ECHO'] = False
app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = True
app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
toolbar = DebugToolbarExtension(app)

# ACCESS_KEY_ID = os.environ['ACCESS_KEY_ID']
# SECRET_ACCESS_KEY = os.environ['SECRET_ACCESS_KEY']
# BUCKET = os.environ['BUCKET_NAME']

s3 = boto3.client(
    "s3",
    "us-west-1",
    aws_access_key_id=os.environ['ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['SECRET_ACCESS_KEY']
)
BUCKET = os.environ['BUCKET_NAME']

# home/index page shows collection of all photos with search and add button
# if search term, re-render home page route with query string

# add image form page
# individual image page with edit button for options
# if edit, make copy of photo to backend, commit to db, redirect to home

# boto3 client functions/helpers, import .env var


@app.get('/')
def homepage():
    """Display home page with list of top 20 images."""
    # query db for amazon links (img url)
    images = Image.query.all()

    return render_template('index.html', images=images)


@app.route('/addimage', methods=['GET', 'POST'])
def add_image():
    form = AddImageForm()

    if form.validate_on_submit():
        f = form.photo.data

        filename = secure_filename(f.filename)
        f.save(os.path.join(filename))
        with open(filename, 'rb') as photo:
            # print(type(photo))
            s3.upload_fileobj(photo, BUCKET, filename)

        # delete image form app or use uploadfileobj

        # insert image data to images table
        image_name = form.image_name.data
        uploaded_by = form.uploaded_by.data
        notes = form.notes.data

        image = Image(
            image_name=image_name,
            uploaded_by=uploaded_by,
            notes=notes,
            amazon_file_path=f"http://{BUCKET}.s3.us-west-1.amazonaws.com/{filename}"
        )
        db.session.add(image)
        db.session.commit()

        # insert image metadata to Image_Metadata table
        img = PilImage.open(f)
        img_metadata = img.getexif()
        exif_data = {}

        for tag_id in img_metadata:
            tag = TAGS.get(tag_id, tag_id)
            data = img_metadata.get(tag_id)
            # decode data from bytes
            if isinstance(data, bytes):
                data = data.decode()

            print("data", type(data))
            exif_data[tag] = data

        # print("exif_data", exif_data)

        # for tag in exif_data:
        #     metadata = Image_Metadata(
        #         image_id = image.id,
        #         name = tag,
        #         value = exif_data[tag]
        #     )
        #     db.session.add(metadata)
        # db.session.commit()

        return redirect("/")

    return render_template('add_image.html', form=form)


@app.route('/image/<int:id>', methods=['GET'])
def show_image(id):
    image = Image.query.get_or_404(id)

    return render_template('image.html', image=image)


@app.route('/image/<int:id>/edit', methods=['GET', 'POST'])
def edit_image(id):
    image = Image.query.get_or_404(id)

    form = EditImageForm()

    filename = image.amazon_file_path
    print('refreshing here')
    response = requests.get(filename)
    img = PilImage.open(BytesIO(response.content))
    img.save("static/images/edit.JPG")
    size = img.size
    if form.validate_on_submit():

        print("formData", form.black_and_white.data)
        print("img is", img)
        print("edge-detect", form.edge_detection.data)
        if form.black_and_white.data == True:
            print("did something here 2")
            img = img.convert('L')
        if "Smooth" in form.edge_detection.data:
            img = img.convert('L')
            img = img.filter(ImageFilter.SMOOTH)
        if "Edges" in form.edge_detection.data:
            img = img.filter(ImageFilter.FIND_EDGES)
        if "Enhance" in form.edge_detection.data:
            img = img.filter(ImageFilter.EDGE_ENHANCE)
        if form.reduce.data > 0:
            print("reduce by", form.reduce.data)
            img = img.reduce(form.reduce.data)
        size = img.size
        img.save("static/images/edit.JPG")
        return render_template('edit_image.html', image=image, size=size, form=form)
        # img.show() it works
        # img.save to is edit
        # redirect with new img

    return render_template('edit_image.html', image=image, size=size, form=form)


@app.route('/uploadedit', methods=['GET', 'POST'])
def upload_edit_image():

    form = EditImageForUploadForm()

    if form.validate_on_submit():
        filename = form.file_name.data
        with open(os.path.join("static/images/edit.JPG"), 'rb') as photo:
            # print(type(photo))
            s3.upload_fileobj(photo, BUCKET, filename)

        # delete image form app or use uploadfileobj

        # insert image data to images table
        image_name = form.image_name.data
        uploaded_by = form.uploaded_by.data
        notes = form.notes.data

        image = Image(
            image_name=image_name,
            uploaded_by=uploaded_by,
            notes=notes,
            amazon_file_path=f"http://{BUCKET}.s3.us-west-1.amazonaws.com/{filename}"
        )

        db.session.add(image)
        db.session.commit()

        return redirect(f'/image/{image.id}')

    return render_template('upload_edit.html', form=form)
