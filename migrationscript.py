from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import sqlite3
from neo4j import GraphDatabase
from dataclasses import dataclass
from typing import List, Optional

# Migration Script
def migrate(sqlite_path, neo4j_uri, neo4j_user, neo4j_pass):
    # Connect SQLite
    sq = sqlite3.connect(sqlite_path)
    cur = sq.cursor()

    # Connect Neo4j
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
    with driver.session() as session:
        # Create constraints
        session.run("CREATE CONSTRAINT unique_user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE;")
        session.run("CREATE CONSTRAINT unique_post_id IF NOT EXISTS FOR (p:Post) REQUIRE p.id IS UNIQUE;")

        # Migrate users
        for user in cur.execute("SELECT id, username, name FROM users"):
            session.run(
                "CREATE (u:User {id: $id, username: $username, name: $name})",
                id=user[0], username=user[1], name=user[2]
            )

        # Migrate posts
        for post in cur.execute("SELECT id, user_id, content, timestamp FROM posts"):
            session.run(
                "MATCH (u:User {id: $user_id}) CREATE (p:Post {id: $id, content: $content, timestamp: datetime($timestamp)}) CREATE (u)-[:AUTHORED]->(p)",
                id=post[0], user_id=post[1], content=post[2], timestamp=post[3]
            )

        # Migrate follows
        for f in cur.execute("SELECT follower_id, followee_id FROM follows"):
            session.run(
                "MATCH (a:User {id: $follower}), (b:User {id: $followee}) MERGE (a)-[:FOLLOWS]->(b)",
                follower=f[0], followee=f[1]
            )
            
    driver.close()