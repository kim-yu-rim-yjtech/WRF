from flask import Flask, jsonify, send_from_directory
import psycopg2


def get_db_connection():
    try:
        conn = psycopg2.connect(
            host="172.27.80.1",
            database="calpuff",
            user="postgres",
            password="1201"
        )
        print("데이터베이스에 연결되었습니다.")
        return conn
    except Exception as e:
        print("데이터베이스 연결에 실패했습니다:", e)
        return None