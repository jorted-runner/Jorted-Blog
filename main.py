from flask import Flask, render_template, redirect, url_for, request, flash, g, abort
from functools import wraps
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user, logout_user
from forms import CreatePostForm, NewUser, UserLogin, CommentCreator
from flask_ckeditor import CKEditor, CKEditorField
from flask_gravatar import Gravatar
import datetime as dt
import os
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")
ckeditor = CKEditor(app)
Bootstrap(app)

if os.environ.get("LOCAL") == "True":
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'    
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")

db.init_app(app)


login_manager = LoginManager()
login_manager.init_app(app)

gravatar = Gravatar(app, size=50, rating='g', default='identicon', force_default=False, force_lower=False, use_ssl=False, base_url=None)

def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.id != 1:
            return abort(403)
        return f(*args, **kwargs)
    return decorated_function

class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    author = relationship("Users", back_populates="posts")
    title = db.Column(db.String(250), unique=True, nullable=False)
    subtitle = db.Column(db.String(250), nullable=False)
    date = db.Column(db.String(250), nullable=False)
    body = db.Column(db.Text, nullable=False)
    img_url = db.Column(db.String(250), nullable=False)
    comments = relationship("Comment", back_populates="parent_post")

class Users(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(250), unique=True, nullable=False)
    name = db.Column(db.String(250), unique=False, nullable=False)
    password = db.Column(db.String(250), unique=False, nullable=False)
    posts = relationship("BlogPost", back_populates="author")
    comments = relationship("Comment", back_populates="comment_author")

class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("blog_posts.id"))
    parent_post = relationship("BlogPost", back_populates="comments")
    text = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    comment_author = relationship("Users", back_populates="comments")


with app.app_context():
    db.create_all()


@login_manager.user_loader
def load_user(user_id):
    return Users.query.get(int(user_id))


@app.route('/')
def get_all_posts():
    posts= BlogPost.query.all()
    return render_template("index.html", all_posts=posts, current_user=current_user)

@app.route('/register', methods=["GET", "POST"])
def register():
    new_user = NewUser()
    if new_user.validate_on_submit():
        if Users.query.filter_by(email=new_user.email.data).first():
            flash("You've already signed up with that email, log in instead!")
            return redirect(url_for('register'))
        new_user_name = request.form.get('name')
        new_user_email = request.form.get('email')
        new_user_password = generate_password_hash(request.form.get('password'), method='pbkdf2:sha256', salt_length=8)
        new_user = Users(email = new_user_email, password = new_user_password, name = new_user_name)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for("get_all_posts"))
    else:
        return render_template("register.html", form = new_user, current_user=current_user)

@app.route('/login', methods=["GET", "POST"])
def login():
    login_form = UserLogin()
    if login_form.validate_on_submit():
        if not Users.query.filter_by(email=login_form.email.data).first():
            flash("No user associated with that email, try registering!")
            return redirect(url_for('login'))
        email = request.form.get("email")
        user = Users.query.filter_by(email = email).first()
        if user:
            password = request.form.get('password')
            if check_password_hash(user.password, password):
                login_user(user)
                return redirect(url_for('get_all_posts'))
            else:
                flash("Incorrect Password, try again!")
                return render_template("login.html", form = login_form)
    else:
        return render_template("login.html", form = login_form, current_user=current_user)


@app.route("/post/<int:index>", methods=["GET", "POST"])
def show_post(index):
    requested_post = BlogPost.query.get(index)
    add_comment = CommentCreator()
    if add_comment.validate_on_submit():
        if not current_user.is_authenticated:
            flash("Must be logged in to leave a comment!")
            return redirect(url_for('show_post', index=index))
        else:
            comment = request.form.get('comment_body')
            new_comment = Comment(post_id=index, text=comment, author_id=current_user.id)
            db.session.add(new_comment)
            db.session.commit()
            return redirect(url_for('show_post', index=index))
    return render_template("post.html", post=requested_post, current_user=current_user, form = add_comment)


@app.route("/about")
def about():
    return render_template("about.html", current_user=current_user)


@app.route("/contact")
def contact():
    return render_template("contact.html", current_user=current_user)

@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def new_post():
    today_info = dt.datetime.now()
    today = today_info.strftime("%B %d, %Y")
    new_post = CreatePostForm()
    if request.method == "POST":
        if new_post.validate_on_submit():
            blog_post = BlogPost(title=new_post.title.data, subtitle=new_post.subtitle.data, author=current_user, 
                                 img_url=new_post.img_url.data, body=new_post.body.data, date=today)
            db.session.add(blog_post)
            db.session.commit()
            return redirect(url_for('get_all_posts'))
    else:
        return render_template("make-post.html", post_form = new_post, is_edit = False, current_user=current_user)

@app.route("/edit-post/<post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = BlogPost.query.get(post_id)
    edit_post_form = CreatePostForm(title=post.title, subtitle=post.subtitle, img_url=post.img_url, author=post.author, body=post.body)
    if edit_post_form.validate_on_submit():
        post.title = edit_post_form.title.data
        post.subtitle = edit_post_form.subtitle.data
        post.img_url = edit_post_form.img_url.data
        post.author = edit_post_form.author.data
        post.body = edit_post_form.body.data    
        db.session.commit()
        return redirect(url_for("show_post", index=post.id))
    return render_template ("make-post.html", post_form = edit_post_form, is_edit = True, current_user=current_user)

@app.route("/delete/<index>")
@admin_only
def delete_post(index):
    post_to_delete = BlogPost.query.filter_by(id=index).first()
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))        

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))

if __name__ == "__main__":
    app.run(debug=True)

    # app.run(host='0.0.0.0', port=5000)
    
    # However, if you want to run it with host 0.0.0.0, here's what you may need to do. Go to command prompt or terminal and type "ipconfig" without double quotes. 
    # You'll see your IPv4 address there. Copy that address and paste it into your browser url followed by ":5000". This is how your url should look like:

    #   http://your-ip-address:5000/

    # This should work just fine. Interesting thing about 0.0.0.0 is that you can type the same address in your mobile phone browser and it'll run your app there too 
    # if your mobile and computer are connected on the same network.