from __future__ import annotations
from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash, request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, ForeignKey
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from forms import CreatePostForm, SignupForm, SigninForm, CommentForm
from typing import List
from markupsafe import escape
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SEC_KEY")
ckeditor = CKEditor(app)
Bootstrap5(app)


login_manager = LoginManager()
login_manager.init_app(app)


# CREATE DATABASE
class Base(DeclarativeBase):
    pass


app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DB_URI", "sqlite:///blog.db")
db = SQLAlchemy(model_class=Base)
db.init_app(app)


# CONFIGURE TABLES
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    password: Mapped[str] = mapped_column(String(100))
    username: Mapped[str] = mapped_column(String(1000), unique=True)

    posts: Mapped[List["BlogPost"]] = relationship(
        back_populates="author",
        cascade="all, delete, delete-orphan",
        passive_deletes=False
    )
    comments: Mapped[List["Comment"]] = relationship(
        back_populates="comment_author",
        cascade="all, delete, delete-orphan",
        passive_deletes=False
    )


class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    author: Mapped["User"] = relationship(back_populates="posts")

    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)

    comments: Mapped[List["Comment"]] = relationship(
        back_populates="post",
        cascade="all, delete, delete-orphan",
        passive_deletes=False
    )


class Comment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    comment_author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    comment_author: Mapped["User"] = relationship(back_populates="comments")

    post_id: Mapped[int] = mapped_column(ForeignKey("blog_posts.id", ondelete="CASCADE"))
    post: Mapped["BlogPost"] = relationship(back_populates="comments")


with app.app_context():
    db.create_all()


def admin_only(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if int(current_user.get_id()) != 1:
            return abort(403)
        return function(*args, **kwargs)
    return decorated_function


@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("get_all_posts"))

    form = SignupForm()
    if form.validate_on_submit():
        result = db.session.execute(db.select(User).where(User.email == form.email.data))
        user = result.scalar()
        if user:
            flash("This email already exists. Sign in instead", "error")
            return redirect(url_for("signin"))

        hashed_and_salted_password = generate_password_hash(
            password=form.password.data,
            method="pbkdf2:sha256",
            salt_length=8
        )

        new_user = User(
            email=form.email.data,
            password=hashed_and_salted_password,
            username=form.username.data.lower()
        )

        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)

        return redirect(url_for("get_all_posts"))

    return render_template(
        "signup.html",
        form=form,
        signed_in=current_user.is_authenticated
    )


@app.route("/signin", methods=["GET", "POST"])
def signin():
    if current_user.is_authenticated:
        return redirect(url_for("get_all_posts"))

    form = SigninForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        result = db.session.execute(db.select(User).where(User.email == email))
        user = result.scalar()
        if user is None:
            flash("Email doesn't exist. Try again", "error")
            return redirect(url_for("signin"))

        if check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("get_all_posts"))

        else:
            flash("Incorrect Password. Try again", "error")
            return redirect(url_for("signin"))

    return render_template(
        "signin.html",
        form=form,
        signed_in=current_user.is_authenticated
    )


@app.route("/signout")
def signout():
    logout_user()
    return redirect(url_for("get_all_posts"))


@app.route("/user/<username>")
@login_required
def user_profile(username):
    active_username = "guest"
    if current_user.username:
        active_username = current_user.username

    if active_username == username:
        return render_template(
            "profile.html",
            signed_in=current_user.is_authenticated,
            active_user=current_user
        )

    else:
        return abort(403)


# Home
@app.route("/")
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    posts = posts[::-1]
    return render_template(
        "index.html",
        all_posts=posts,
        signed_in=current_user.is_authenticated,
        active_user=current_user
    )


@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    form = CommentForm()
    requested_post = db.get_or_404(BlogPost, post_id)
    gravatar = Gravatar(app,
                        size=100,
                        rating="g",
                        default="retro",
                        force_default=False,
                        force_lower=False,
                        use_ssl=False,
                        base_url=None)

    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("Please login to comment", "error")
            return redirect(url_for("signin"))

        new_comment = Comment(
            text=escape(form.comment.data),
            comment_author=current_user,
            post=requested_post
        )

        db.session.add(new_comment)
        db.session.commit()

        return redirect(url_for("show_post", post_id=post_id))

    return render_template(
        "post.html",
        form=form,
        post=requested_post,
        signed_in=current_user.is_authenticated,
        active_user=current_user
    )


@app.route("/new-post", methods=["GET", "POST"])
@login_required
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            author=current_user,
            title=form.title.data,
            subtitle=form.subtitle.data,
            date=date.today().strftime("%B %d, %Y"),
            body=form.body.data,
            img_url=form.img_url.data
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))

    return render_template(
        "make-post.html",
        form=form,
        signed_in=current_user.is_authenticated,
        active_user=current_user
    )


@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@login_required
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        author=post.author,
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.author = current_user
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))

    return render_template(
        "make-post.html",
        form=edit_form,
        signed_in=current_user.is_authenticated,
        active_user=current_user
    )


@app.route("/delete-post/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for("get_all_posts"))


@app.route("/delete-comment/<int:comment_id>")
def delete_comment(comment_id):
    comment_to_delete = db.get_or_404(Comment, comment_id)
    db.session.delete(comment_to_delete)
    db.session.commit()
    return redirect(url_for("show_post", post_id=comment_to_delete.post_id))


@app.route("/delete-user/<username>")
def delete_user(username):
    user_to_delete = db.session.execute(db.select(User).where(User.username == username)).scalar()
    logout_user()
    db.session.delete(user_to_delete)
    db.session.commit()
    return redirect(url_for("get_all_posts"))


@app.route("/about")
def about():
    return render_template(
        "about.html",
        signed_in=current_user.is_authenticated,
        active_user=current_user
    )


@app.route("/contact", methods=["GET", "POST"])
def contact():
    return render_template(
        "contact.html",
        signed_in=current_user.is_authenticated,
        active_user=current_user
    )


if __name__ == "__main__":
    app.run(debug=False)
