# social_network.py
import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from dataclasses import dataclass
from typing import List, Optional
from dotenv import load_dotenv
from neo4j import GraphDatabase


# ======================
# Database Access Layer
# ======================
class Database:
    def __init__(self):
        load_dotenv()
        uri = os.environ.get("NEO4J_URI")
        user = os.environ.get("NEO4J_USER")
        password = os.environ.get("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    # User operations
    def create_user(self, username: str, name: str) -> str:
        with self.driver.session() as session:
            result = session.run(
                "CREATE (u:User {username: $username, name: $name}) "
                "SET u.id = randomUUID() "
                "RETURN u.id AS id",
                username=username, name=name
            )
            return result.single()["id"]

    def get_user(self, user_id: str) -> Optional[dict]:
        with self.driver.session() as session:
            result = session.run(
                "MATCH (u:User {id: $user_id}) RETURN u", user_id=user_id
            )
            record = result.single()
            if record:
                u = record["u"]
                return {'id': u["id"], 'username': u["username"], 'name': u["name"]}
            return None
            

    def get_all_users(self) -> List[dict]:
        with self.driver.session() as session:
            result = session.run("MATCH (u:User) RETURN u")
            return [{'id': u["u"]["id"], 'username': u["u"]["username"], 'name': u["u"]["name"]} for u in result]

    def create_post(self, post_id, user_id, content):
        query = (
            "MATCH (u:User {id: $user_id}) "
            "CREATE (p:Post {id: $post_id, content: $content, timestamp: datetime()}) "
            "CREATE (u)-[:AUTHORED]->(p) RETURN p"
        )
        with self.driver.session() as session:
            return session.run(query, post_id=post_id, user_id=user_id, content=content).single()["p"]

    def get_posts_by_user(self, user_id):
        query = (
            "MATCH (u:User {id: $user_id})-[:AUTHORED]->(p:Post) "
            "RETURN p ORDER BY p.timestamp DESC"
        )
        with self.driver.session() as session:
            return [r["p"] for r in session.run(query, user_id=user_id)]
    
    def get_feed(self, user_id):
        query = (
            "MATCH (u:User {id: $user_id})-[:FOLLOWS]->(f:User)-[:AUTHORED]->(p:Post) "
            "RETURN p, f ORDER BY p.timestamp DESC"
        )
        with self.driver.session() as session:
            return [ {"post": r["p"], "author": r["f"]} for r in session.run(query, user_id=user_id) ]
        
        
    def follow_user(self, follower_id, followee_id):
        query = (
            "MATCH (a:User {id: $follower}), (b:User {id: $followee}) "
            "MERGE (a)-[:FOLLOWS]->(b)"
        )
        with self.driver.session() as session:
            session.run(query, follower=follower_id, followee=followee_id)

    def unfollow_user(self, follower_id, followee_id):
        query = (
            "MATCH (a:User {id: $follower})-[r:FOLLOWS]->(b:User {id: $followee}) "
            "DELETE r"
        )
        with self.driver.session() as session:
            session.run(query, follower=follower_id, followee=followee_id)

    def get_followers(self, user_id):
        query = (
            "MATCH (f:User)-[:FOLLOWS]->(u:User {id: $user_id}) RETURN f"
        )
        with self.driver.session() as session:
            return [r["f"] for r in session.run(query, user_id=user_id)]

    def get_following(self, user_id):
        query = (
            "MATCH (u:User {id: $user_id})-[:FOLLOWS]->(f:User) RETURN f"
        )
        with self.driver.session() as session:
            return [r["f"] for r in session.run(query, user_id=user_id)]
# ======================
# Web Application
# ======================
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
db = Database()

# Sample data initialization
with app.app_context():
    if not db.get_all_users():
        db.create_user('alice', 'Alice Smith')
        db.create_user('bob', 'Bob Johnson')
        db.create_user('charlie', 'Charlie Brown')

# ======================
# API Endpoints
# ======================
@app.route('/api/users', methods=['GET'])
def api_get_users():
    return jsonify(db.get_all_users())

@app.route('/api/users/<user_id>', methods=['GET'])
def api_get_user(user_id):
    user = db.get_user(user_id)
    return jsonify(user) if user else ('User not found', 404)

@app.route('/api/users/<user_id>/posts', methods=['GET'])
def api_get_user_posts(user_id):
    return jsonify(db.get_posts_by_user(user_id))

@app.route('/api/users/<user_id>/feed', methods=['GET'])
def api_get_user_feed(user_id):
    return jsonify(db.get_feed(user_id))

@app.route('/api/users/<user_id>/followers', methods=['GET'])
def api_get_user_followers(user_id):
    return jsonify(db.get_followers(user_id))

@app.route('/api/users/<user_id>/following', methods=['GET'])
def api_get_user_following(user_id):
    return jsonify(db.get_following(user_id))

@app.route('/api/posts', methods=['POST'])
def api_create_post():
    data = request.get_json()
    post_id = db.create_post(data['user_id'], data['content'])
    return jsonify({'post_id': post_id}), 201

@app.route('/api/follow', methods=['POST'])
def api_follow_user():
    data = request.get_json()
    success = db.follow_user(data['follower_id'], data['followee_id'])
    return jsonify({'success': success}), 201 if success else 200

# ======================
# Frontend Routes
# ======================
@app.route('/')
def home():
    users = db.get_all_users()
    current_user = None
    if 'user_id' in session:
        current_user = db.get_user(session['user_id'])
    return render_template('index.html', users=users, current_user=current_user)

@app.route('/user/<user_id>')
def user_profile(user_id):
    user = db.get_user(user_id)
    if not user:
        return "User not found", 404

    current_user = None
    is_following = False

    if 'user_id' in session:
        current_user = db.get_user(session['user_id'])
        if current_user and current_user['id'] != user_id:
            following = db.get_following(current_user['id'])
            is_following = any(f['id'] == user_id for f in following)

    posts = db.get_posts_by_user(user_id)
    followers = db.get_followers(user_id)
    following = db.get_following(user_id)

    return render_template('profile.html',
                         user=user,
                         posts=posts,
                         followers=followers,
                         following=following,
                         current_user=current_user,
                         is_following=is_following)

@app.route('/user/<user_id>/feed')
def user_feed(user_id):
    user = db.get_user(user_id)
    feed = db.get_feed(user_id)
    return render_template('feed.html', user=user, feed=feed)

@app.route('/create_post', methods=['POST'])
def create_post():
    user_id = request.form['user_id']
    content = request.form['content']
    db.create_post(user_id, content)
    return redirect(url_for('user_profile', user_id=user_id))

@app.route('/login/<user_id>')
def login(user_id):
    session['user_id'] = user_id
    return redirect(url_for('home'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('home'))

@app.route('/follow', methods=['POST'])
def follow():
    follower_id = request.form['follower_id']
    followee_id = request.form['followee_id']
    following = db.get_following(follower_id)
    is_following = any(f['id'] == followee_id for f in following)
    if is_following:
        db.unfollow_user(follower_id, followee_id)
    else:
        db.follow_user(follower_id, followee_id)
    return redirect(url_for('user_profile', user_id=followee_id))

@app.route('/templates/<template_name>')
def serve_template(template_name):
    return render_template(template_name)

app.jinja_env.globals.update(
    render_index=lambda: render_template('index.html', users=db.get_all_users()),
    render_profile=lambda user_id: render_template(
        'profile.html',
        user=db.get_user(user_id),
        posts=db.get_posts_by_user(user_id),
        followers=db.get_followers(user_id),
        following=db.get_following(user_id)
    )
)

if __name__ == '__main__':
    app.run(debug=True, port=5050)